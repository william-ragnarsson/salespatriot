"""DIBBS Solicitation Browser API.

Run:  .venv/bin/uvicorn api:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
import json
import os
import re
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

import db

ROOT = Path(__file__).resolve().parent
DB_PATH = os.environ.get("DIBBS_DB", str(ROOT / "dibbs.db"))
DIBBS = "https://www.dibbs.bsm.dla.mil"

# Tables owned by the API (the rfq table is owned by schema.sql / the scraper).
API_SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
  id   INTEGER PRIMARY KEY CHECK (id = 1),   -- single hardcoded profile (no auth)
  data TEXT NOT NULL                          -- JSON: {"groups": [...]}
);
CREATE TABLE IF NOT EXISTS triage (
  solicitation_number TEXT PRIMARY KEY,
  state               TEXT NOT NULL CHECK (state IN ('interested', 'dismissed')),
  updated_at          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_state (     -- small key/value store, e.g. matches_seen_at
  key   TEXT PRIMARY KEY,
  value TEXT
);
"""

TriageState = Literal["interested", "dismissed"]
SORTABLE = Literal["return_by", "issue_date", "quantity", "nsn", "fsc", "nomenclature", "solicitation_number"]
SCORES = {"nsn": 3, "fsc": 2, "keyword": 1}


@contextmanager
def get_db():
    conn = db.connect(DB_PATH)
    conn.executescript(API_SCHEMA)
    try:
        yield conn
    finally:
        conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def alnum(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", s or "").upper()


def dedupe(items):
    return list(dict.fromkeys(items))


# ---------------------------------------------------------------- models

class Rfq(BaseModel):
    """One RFQ line item. Extra columns added by the scraper later pass through."""
    model_config = ConfigDict(extra="allow")
    solicitation_number: str
    nsn: str
    fsc: str
    nomenclature: Optional[str] = None
    pr_number: Optional[str] = None
    quantity: Optional[int] = None
    issue_date: Optional[str] = None
    return_by: Optional[str] = None
    status: Optional[str] = None
    dibbs_url: str
    scraped_at: str
    first_seen_at: Optional[str] = None
    nsn_display: str
    nsn_url: Optional[str] = None
    triage: Optional[TriageState] = None


class RfqPage(BaseModel):
    total: int
    items: list[Rfq]


class FscCount(BaseModel):
    fsc: str
    count: int


class DateCount(BaseModel):
    issue_date: Optional[str]
    count: int


class Stats(BaseModel):
    total: int
    open: int
    by_status: dict[str, int]
    issue_dates: list[DateCount]
    last_scraped_at: Optional[str]
    triage: dict[str, int]


class CapabilityGroup(BaseModel):
    """What one source can supply. Manufacturers: one group. Distributors: one group per supplier."""
    supplier: Optional[str] = None
    nsns: list[str] = []
    fscs: list[str] = []
    keywords: list[str] = []

    @field_validator("supplier")
    @classmethod
    def _supplier(cls, v):
        return (v or "").strip() or None

    @field_validator("nsns")
    @classmethod
    def _nsns(cls, v):
        return dedupe(n for n in (alnum(x) for x in v) if n)

    @field_validator("fscs")
    @classmethod
    def _fscs(cls, v):
        out = []
        for x in v:
            d = re.sub(r"\D", "", x)
            if len(d) != 4:
                raise ValueError(f"FSC must be 4 digits: {x!r}")
            out.append(d)
        return dedupe(out)

    @field_validator("keywords")
    @classmethod
    def _keywords(cls, v):
        return dedupe(k for k in (x.strip().lower() for x in v) if k)


class Profile(BaseModel):
    groups: list[CapabilityGroup] = []


class MatchReason(BaseModel):
    kind: Literal["nsn", "fsc", "keyword"]
    value: str
    supplier: Optional[str] = None


class Match(Rfq):
    score: int = Field(description="3 = exact NSN, 2 = FSC, 1 = keyword (strongest reason)")
    reasons: list[MatchReason]
    is_new: bool = Field(False, description="First seen after the last POST /api/matches/seen")


class MatchPage(BaseModel):
    total: int
    new_count: int = 0
    seen_at: Optional[str] = None
    profile_empty: bool
    items: list[Match]


class SeenOut(BaseModel):
    seen_at: str


class TriageIn(BaseModel):
    state: TriageState


class TriageOut(BaseModel):
    solicitation_number: str
    state: TriageState
    updated_at: str


class RefreshIn(BaseModel):
    date: Optional[str] = Field(None, description="Issue date MM-DD-YYYY (default today)", pattern=r"^\d{2}-\d{2}-\d{4}$")
    from_file: Optional[str] = Field(None, description="Parse a saved DIBBS page under samples/ instead of fetching")
    from_dir: Optional[str] = Field(None, description="Replay a day saved with scraper.py --save-dir (under samples/)")


class RefreshStatus(BaseModel):
    running: bool = False
    source: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    pages: int = 0
    rows: int = 0
    inserted: int = 0
    updated: int = 0
    new_matches: int = 0
    error: Optional[str] = None


# ---------------------------------------------------------------- helpers

RFQ_SELECT = """
SELECT r.*, t.state AS triage
FROM rfq r LEFT JOIN triage t ON t.solicitation_number = r.solicitation_number
"""


def to_rfq(row) -> dict:
    d = dict(row)
    nsn = d.get("nsn") or ""
    is_nsn = len(nsn) == 13 and nsn.isdigit()
    d["nsn_display"] = f"{nsn[:4]}-{nsn[4:6]}-{nsn[6:9]}-{nsn[9:]}" if is_nsn else nsn
    d["nsn_url"] = f"{DIBBS}/RFQ/RFQNsn.aspx?value={nsn}&category=issue&Scope=" if is_nsn else None
    return d


def resolve_solicitation(conn, sol: str) -> str:
    """Accept dashed or undashed solicitation numbers; return the stored form or 404."""
    row = conn.execute(
        "SELECT solicitation_number FROM rfq WHERE REPLACE(solicitation_number, '-', '') = ? LIMIT 1",
        (alnum(sol),),
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Solicitation {sol} not found")
    return row[0]


def load_profile(conn) -> Profile:
    row = conn.execute("SELECT data FROM profile WHERE id = 1").fetchone()
    return Profile.model_validate_json(row[0]) if row else Profile()


# ---------------------------------------------------------------- app

app = FastAPI(title="DIBBS Solicitation Browser API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health():
    with get_db() as conn:
        return {"ok": True, "db_rows": conn.execute("SELECT COUNT(*) FROM rfq").fetchone()[0]}


@app.get("/api/stats", response_model=Stats)
def stats():
    with get_db() as conn:
        by_status = {s or "Unknown": n for s, n in conn.execute(
            "SELECT status, COUNT(*) FROM rfq GROUP BY status ORDER BY COUNT(*) DESC")}
        dates = [DateCount(issue_date=d, count=n) for d, n in conn.execute(
            "SELECT issue_date, COUNT(*) FROM rfq GROUP BY issue_date ORDER BY issue_date DESC")]
        triage = {"interested": 0, "dismissed": 0}
        triage.update({s: n for s, n in conn.execute("SELECT state, COUNT(*) FROM triage GROUP BY state")})
        return Stats(
            total=sum(by_status.values()),
            open=by_status.get("Open", 0),
            by_status=by_status,
            issue_dates=dates,
            last_scraped_at=conn.execute("SELECT MAX(scraped_at) FROM rfq").fetchone()[0],
            triage=triage,
        )


@app.get("/api/rfqs", response_model=RfqPage)
def list_rfqs(
    q: Optional[str] = Query(None, description="Search nomenclature, NSN, solicitation # or PR # (dashes optional)"),
    fsc: Optional[str] = Query(None, description="One or more FSCs, comma-separated"),
    nsn: Optional[str] = None,
    status: Optional[str] = Query(None, description="e.g. Open"),
    issue_date: Optional[date] = None,
    return_by_before: Optional[date] = Query(None, description="Return-by on or before this date"),
    min_quantity: Optional[int] = Query(None, ge=0),
    triage: Optional[Literal["interested", "dismissed", "untriaged"]] = None,
    sort: SORTABLE = "return_by",
    order: Literal["asc", "desc"] = "asc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    where, params = [], []
    if q and q.strip():
        clauses = ["LOWER(r.nomenclature) LIKE ?"]
        params.append(f"%{q.strip().lower()}%")
        if qa := alnum(q):
            clauses += ["r.nsn LIKE ?", "REPLACE(r.solicitation_number, '-', '') LIKE ?", "r.pr_number LIKE ?"]
            params += [f"%{qa}%"] * 3
        where.append("(" + " OR ".join(clauses) + ")")
    if fsc:
        fscs = [f.strip() for f in fsc.split(",") if f.strip()]
        where.append(f"r.fsc IN ({','.join('?' * len(fscs))})")
        params += fscs
    if nsn:
        where.append("r.nsn = ?")
        params.append(alnum(nsn))
    if status:
        where.append("LOWER(r.status) = ?")
        params.append(status.lower())
    if issue_date:
        where.append("r.issue_date = ?")
        params.append(issue_date.isoformat())
    if return_by_before:
        where.append("r.return_by <= ?")
        params.append(return_by_before.isoformat())
    if min_quantity is not None:
        where.append("r.quantity >= ?")
        params.append(min_quantity)
    if triage == "untriaged":
        where.append("t.state IS NULL")
    elif triage:
        where.append("t.state = ?")
        params.append(triage)

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    order_sql = f" ORDER BY r.{sort} IS NULL, r.{sort} {order.upper()}, r.solicitation_number, r.pr_number"
    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM rfq r LEFT JOIN triage t ON t.solicitation_number = r.solicitation_number"
            + where_sql, params).fetchone()[0]
        rows = conn.execute(RFQ_SELECT + where_sql + order_sql + " LIMIT ? OFFSET ?",
                            params + [limit, offset]).fetchall()
    return RfqPage(total=total, items=[to_rfq(r) for r in rows])


@app.get("/api/rfqs/{solicitation_number}", response_model=list[Rfq])
def get_rfq(solicitation_number: str):
    """All line items (PRs) for one solicitation. Dashes optional."""
    with get_db() as conn:
        sol = resolve_solicitation(conn, solicitation_number)
        rows = conn.execute(RFQ_SELECT + " WHERE r.solicitation_number = ? ORDER BY r.pr_number", (sol,)).fetchall()
    return [to_rfq(r) for r in rows]


@app.get("/api/fscs", response_model=list[FscCount])
def list_fscs():
    with get_db() as conn:
        return [FscCount(fsc=f, count=n) for f, n in conn.execute(
            "SELECT fsc, COUNT(*) FROM rfq GROUP BY fsc ORDER BY COUNT(*) DESC, fsc")]


@app.get("/api/profile", response_model=Profile)
def get_profile():
    with get_db() as conn:
        return load_profile(conn)


@app.put("/api/profile", response_model=Profile)
def put_profile(profile: Profile):
    with get_db() as conn:
        conn.execute("INSERT INTO profile (id, data) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET data = excluded.data",
                     (profile.model_dump_json(),))
        conn.commit()
    return profile


def get_state(conn, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_state(conn, key: str, value: str):
    conn.execute("INSERT INTO app_state (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.commit()


def compute_matches(conn, *, open_only=True, include_dismissed=False) -> Optional[list[Match]]:
    """All RFQs matching the profile, scored and explained. None if the profile is empty.
    Order: new since last 'mark seen' first, then strongest match (NSN > FSC > keyword), then soonest return-by."""
    profile = load_profile(conn)
    nsn_map, fsc_map, kw_map = {}, {}, {}
    for g in profile.groups:
        for n in g.nsns:
            nsn_map.setdefault(n, []).append(g.supplier)
        for f in g.fscs:
            fsc_map.setdefault(f, []).append(g.supplier)
        for k in g.keywords:
            kw_map.setdefault(k, []).append(g.supplier)
    if not (nsn_map or fsc_map or kw_map):
        return None

    # SQL narrows the candidates; Python scores them and explains why.
    any_of, params = [], []
    if nsn_map:
        any_of.append(f"r.nsn IN ({','.join('?' * len(nsn_map))})")
        params += list(nsn_map)
    if fsc_map:
        any_of.append(f"r.fsc IN ({','.join('?' * len(fsc_map))})")
        params += list(fsc_map)
    for k in kw_map:
        any_of.append("LOWER(r.nomenclature) LIKE ?")
        params.append(f"%{k}%")
    where = ["(" + " OR ".join(any_of) + ")"]
    if open_only:
        where.append("r.status = 'Open'")
    if not include_dismissed:
        where.append("(t.state IS NULL OR t.state != 'dismissed')")
    rows = conn.execute(RFQ_SELECT + " WHERE " + " AND ".join(where), params).fetchall()
    seen_at = get_state(conn, "matches_seen_at")

    results = []
    for row in rows:
        d = to_rfq(row)
        nomen = (d.get("nomenclature") or "").lower()
        reasons = [MatchReason(kind="nsn", value=d["nsn_display"], supplier=s) for s in nsn_map.get(d["nsn"], [])]
        reasons += [MatchReason(kind="fsc", value=d["fsc"], supplier=s) for s in fsc_map.get(d["fsc"], [])]
        reasons += [MatchReason(kind="keyword", value=k, supplier=s)
                    for k, sups in kw_map.items() if k in nomen for s in sups]
        if reasons:
            is_new = seen_at is None or (d.get("first_seen_at") or "") > seen_at
            results.append(Match(**d, score=max(SCORES[r.kind] for r in reasons), reasons=reasons, is_new=is_new))

    results.sort(key=lambda m: (not m.is_new, -m.score, m.return_by is None, m.return_by or "", m.solicitation_number))
    return results


@app.get("/api/matches", response_model=MatchPage)
def matches(
    include_dismissed: bool = False,
    open_only: bool = Query(True, description="Only RFQs with status Open"),
    new_only: bool = Query(False, description="Only matches that arrived since the last POST /api/matches/seen"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """RFQs matching the capability profile: new first, then strongest match (NSN > FSC > keyword), then soonest return-by."""
    with get_db() as conn:
        results = compute_matches(conn, open_only=open_only, include_dismissed=include_dismissed)
        seen_at = get_state(conn, "matches_seen_at")
    if results is None:
        return MatchPage(total=0, new_count=0, seen_at=seen_at, profile_empty=True, items=[])
    new_count = sum(m.is_new for m in results)
    if new_only:
        results = [m for m in results if m.is_new]
    return MatchPage(total=len(results), new_count=new_count, seen_at=seen_at, profile_empty=False,
                     items=results[offset:offset + limit])


@app.post("/api/matches/seen", response_model=SeenOut)
def mark_matches_seen():
    """'I've gone through my list': everything currently in the DB stops counting as new."""
    with get_db() as conn:
        ts = now_iso()
        set_state(conn, "matches_seen_at", ts)
    return SeenOut(seen_at=ts)


@app.put("/api/triage/{solicitation_number}", response_model=TriageOut)
def set_triage(solicitation_number: str, body: TriageIn):
    with get_db() as conn:
        sol = resolve_solicitation(conn, solicitation_number)
        ts = now_iso()
        conn.execute(
            "INSERT INTO triage (solicitation_number, state, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(solicitation_number) DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at",
            (sol, body.state, ts))
        conn.commit()
    return TriageOut(solicitation_number=sol, state=body.state, updated_at=ts)


@app.delete("/api/triage/{solicitation_number}", status_code=204)
def clear_triage(solicitation_number: str):
    with get_db() as conn:
        conn.execute("DELETE FROM triage WHERE REPLACE(solicitation_number, '-', '') = ?", (alnum(solicitation_number),))
        conn.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- refresh (scrape in a background thread)

_job = RefreshStatus()
_job_lock = threading.Lock()


def _run_refresh(day: str, from_file: Optional[Path], from_dir: Optional[Path] = None):
    import scraper  # imported lazily so the API still starts if the scraper is mid-edit
    conn = db.connect(DB_PATH)
    conn.executescript(API_SCHEMA)
    try:
        if from_file:
            pages = [(1, scraper.parse_rows(from_file.read_text()))]
        elif from_dir:
            pages = scraper.replay_dir(from_dir)
        else:
            pages = scraper.fetch_date(scraper.session(), day)
        for _page, rows in pages:  # upsert page by page so a failure keeps what was ingested
            ins, upd = db.upsert_many(conn, rows)
            with _job_lock:
                _job.pages += 1
                _job.rows += len(rows)
                _job.inserted += ins
                _job.updated += upd
        # "N new matches for you": profile matches whose rows were first inserted by this refresh
        found = compute_matches(conn) or []
        with _job_lock:
            _job.new_matches = sum((m.first_seen_at or "") >= _job.started_at for m in found)
    except Exception as e:  # noqa: BLE001 - surface any scrape failure to the client
        with _job_lock:
            _job.error = f"{type(e).__name__}: {e}"
    finally:
        conn.close()
        with _job_lock:
            _job.running = False
            _job.finished_at = now_iso()


@app.get("/api/refresh", response_model=RefreshStatus)
def refresh_status():
    with _job_lock:
        return _job.model_copy()


@app.post("/api/refresh", response_model=RefreshStatus, status_code=202)
def refresh(body: RefreshIn = RefreshIn()):
    global _job
    path = None
    if body.from_file:
        path = (ROOT / body.from_file).resolve()
        if not path.is_relative_to(ROOT / "samples") or not path.is_file():
            raise HTTPException(400, "from_file must be an existing file under samples/")
    if body.from_dir:
        path = (ROOT / body.from_dir).resolve()
        if not path.is_relative_to(ROOT / "samples") or not path.is_dir():
            raise HTTPException(400, "from_dir must be an existing directory under samples/")
    day = body.date or date.today().strftime("%m-%d-%Y")
    with _job_lock:
        if _job.running:
            raise HTTPException(409, "A refresh is already running")
        _job = RefreshStatus(running=True, source=str(path.relative_to(ROOT)) if path else f"dibbs:{day}",
                             started_at=now_iso())
        snapshot = _job.model_copy()
    threading.Thread(target=_run_refresh, args=(day, None if body.from_dir else path,
                                                path if body.from_dir else None), daemon=True).start()
    return snapshot
