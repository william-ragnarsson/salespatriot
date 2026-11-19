import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")
KEY = ("solicitation_number", "pr_number", "nsn")
COLS = ["solicitation_number", "nsn", "fsc", "nomenclature", "pr_number", "quantity",
        "issue_date", "return_by", "status", "dibbs_url", "scraped_at"]


def connect(path="dibbs.db"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA.read_text())
    return conn


def upsert_many(conn, rows):
    """Insert or update by (solicitation, PR, NSN) line item. Returns (inserted, updated)."""
    key = lambda r: (r["solicitation_number"], r["pr_number"], r["nsn"])
    existing = {tuple(r) for r in conn.execute("SELECT solicitation_number, pr_number, nsn FROM rfq")}
    inserted = len({key(r) for r in rows} - existing)
    updates = ", ".join(f"{c}=excluded.{c}" for c in COLS if c not in KEY)
    conn.executemany(
        f"INSERT INTO rfq ({', '.join(COLS)}) VALUES ({', '.join(':' + c for c in COLS)}) "
        f"ON CONFLICT(solicitation_number, pr_number, nsn) DO UPDATE SET {updates}",
        rows,
    )
    conn.commit()
    return inserted, len(rows) - inserted
