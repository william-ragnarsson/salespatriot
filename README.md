# DIBBS Solicitation Browser

A web application that collects the daily RFQs (Requests for Quotation) the Defense Logistics Agency
publishes on [DIBBS](https://www.dibbs.bsm.dla.mil/), stores them in SQLite, and shows each vendor
only the solicitations they can supply.

```
DIBBS website ──scraper.py──▶ dibbs.db (SQLite) ◀──api.py (FastAPI :8000)──▶ frontend (React + Vite :5173)
```

## Features
- **Ingestion**: scrapes every RFQ for a given issue date from DIBBS and upserts it into SQLite.
  Re-running a date is safe and never creates duplicates.
- **Browse**: search and filter all RFQs by keyword, NSN, FSC, status, dates and quantity. Every row
  links back to its page on DIBBS.
- **Capability profile**: the NSNs, FSCs and keywords a vendor can supply. Distributors can keep one
  group per supplier.
- **Matches**: only the RFQs that match the profile, with the reason for each match (exact NSN >
  FSC > keyword), sorted by match strength and then by the soonest return-by date. RFQs that arrived
  since the list was last reviewed are flagged as new.
- **Triage**: mark solicitations Interested or Dismissed so the daily list can be worked down to zero.

---

## Requirements
- Python 3
- Node.js 18 or later
- The `sqlite3` CLI (optional, for inspecting the database; preinstalled on macOS)

## Installation

Run from the project root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # requests, beautifulsoup4, fastapi, uvicorn
cd frontend && npm install && cd ..             # React + Vite
```

## Fetching data

`scraper.py` fetches all RFQs for one **issue date** and writes them to `dibbs.db`. Dates use the
DIBBS format `MM-DD-YYYY`. A full day is about 750 rows over 15 pages and takes around 45 seconds.

```bash
# Today
.venv/bin/python scraper.py

# Yesterday (macOS; on Linux use: date -d yesterday +%m-%d-%Y)
.venv/bin/python scraper.py --date "$(date -v-1d +%m-%d-%Y)"

# A specific date
.venv/bin/python scraper.py --date 11-18-2026

# A range of dates
for d in 11-16-2026 11-17-2026 11-18-2026; do .venv/bin/python scraper.py --date "$d"; done
```

Notes:
- Rows are upserted on `(solicitation_number, pr_number, nsn)`, so a date can be fetched again at any
  time to pick up status changes.
- DIBBS only keeps about the last month of issue dates (listed on `RfqDates.aspx?category=issue`).
  Weekends, holidays and older dates return 0 rows.
- Rows are committed page by page. If DIBBS fails partway through, the pages already fetched are kept.

### Other scraper options

| Option | Purpose |
|---|---|
| `--date MM-DD-YYYY` | Issue date to fetch (default: today) |
| `--save-dir DIR` | Also save each raw results page to `DIR/page-N.html` |
| `--from-dir DIR` | Load a day saved with `--save-dir` instead of contacting DIBBS |
| `--from-file FILE` | Parse a single saved results page instead of contacting DIBBS |
| `--max-pages N` | Stop after `N` pages (useful for quick tests) |
| `--db PATH` | Write to a different database file (default: `dibbs.db`) |

### Working offline

Raw pages can be saved once and loaded later without network access:

```bash
.venv/bin/python scraper.py --date 11-19-2026 --save-dir samples/11-19-2026   # fetch and save
.venv/bin/python scraper.py --from-dir samples/11-19-2026                     # load from disk
.venv/bin/python scraper.py --from-file samples/page1.html                    # single page, 50 rows
```

`samples/` contains saved days for `11-17-2026`, `11-18-2026` and `11-19-2026`, plus a single page
in `samples/page1.html`.

## Running the application

Start the API and the UI in two terminals:

```bash
# API on http://localhost:8000 (interactive docs at /docs)
.venv/bin/uvicorn api:app --reload --port 8000

# UI on http://localhost:5173 (proxies /api to :8000)
cd frontend && npm run dev
```

Open http://localhost:5173. Data can also be fetched from the UI: **↻ Refresh from DIBBS** in the
header runs the same scrape as `scraper.py` for today. If DIBBS is unreachable, it offers to load
the saved sample page instead.

The UI has three views:
- **All RFQs**: the full list with search and filters.
- **Profile**: the capability profile editor.
- **My matches**: RFQs matching the profile, with match reasons and Interested/Dismissed triage.

### Reproducible state

`scripts/demo_reset.sh` rebuilds the database into a fixed state from the saved samples, which is
useful for testing the "new matches" flow. With the API running, it:
1. deletes `dibbs.db` and loads `samples/11-17-2026` and `samples/11-18-2026`,
2. sets the profile from `demo_profile.json` (a distributor with three suppliers),
3. marks all current matches as seen.

Loading the next day then reports only the matches it added:

```bash
scripts/demo_reset.sh
curl -X POST localhost:8000/api/refresh -H 'content-type: application/json' \
  -d '{"from_dir":"samples/11-19-2026"}'
curl 'localhost:8000/api/matches?new_only=true'
```

---

## Command reference

### Backend (API)
| Command | What it does |
|---|---|
| `.venv/bin/uvicorn api:app --reload --port 8000` | Starts the API with auto-reload |
| `DIBBS_DB=other.db .venv/bin/uvicorn api:app --port 8000` | Points the API at a different database |
| open http://localhost:8000/docs | Interactive Swagger docs for every endpoint |
| `curl localhost:8000/api/health` | Checks the API is up and how many rows are in the DB |

### Frontend (UI)
| Command | What it does |
|---|---|
| `cd frontend && npm run dev` | Dev server at http://localhost:5173 (proxies `/api` to `:8000`) |
| `cd frontend && npm run build` | Production build into `frontend/dist/` |
| `cd frontend && npm run preview` | Serves the production build locally |

### Database (SQLite)
| Command | What it does |
|---|---|
| `sqlite3 dibbs.db ".tables"` | Lists tables: `rfq`, `profile`, `triage`, `app_state` |
| `sqlite3 -header -column dibbs.db "select * from rfq limit 10"` | Shows the first rows |
| `sqlite3 -header -csv dibbs.db "select * from rfq" > rfq.csv` | Exports to CSV |
| `rm dibbs.db` | Starts fresh (recreated on the next scrape or API call) |

More queries are in [Viewing the data](#viewing-the-data).

---

## Project layout

| Path | Purpose |
|------|---------|
| `scraper.py` | Fetches RFQs from DIBBS for one issue date, parses them and upserts them into SQLite |
| `db.py` | `connect()` (creates the schema if missing) and `upsert_many()` |
| `schema.sql` | The `rfq` table and indexes |
| `api.py` | FastAPI backend: browse/search, profile, matching, triage, and refresh (creates the `profile`, `triage` and `app_state` tables) |
| `frontend/` | React + Vite single-page app |
| `frontend/src/App.jsx` | Header (stats + refresh button) and tabs |
| `frontend/src/Matches.jsx` | "My matches" view |
| `frontend/src/Browse.jsx` | "All RFQs" table with search and filters |
| `frontend/src/Profile.jsx` | Capability profile editor |
| `frontend/src/api.js` | Thin fetch client for the API |
| `samples/` | Saved DIBBS results pages: `page1.html` and full days under `MM-DD-YYYY/` |
| `demo_profile.json` | Example distributor profile used by `scripts/demo_reset.sh` |
| `scripts/demo_reset.sh` | Rebuilds the database into a fixed state from the saved samples |
| `dibbs.db` | The SQLite database (gitignored, created on first run) |

---

## Backend API

Base URL `http://localhost:8000`. Full schema at `/docs`.

| Method & path | What it does |
|---|---|
| `GET /api/health` | Liveness check + row count |
| `GET /api/stats` | Totals, open count, counts by status and issue date, last scrape time, triage counts |
| `GET /api/rfqs` | Browse/search. Params: `q` (nomenclature, NSN, solicitation # or PR #; dashes optional), `fsc` (comma-separated), `nsn`, `status`, `issue_date`, `return_by_before`, `min_quantity`, `triage` (`interested`/`dismissed`/`untriaged`), `sort`, `order`, `limit`, `offset` |
| `GET /api/rfqs/{solicitation}` | All line items for one solicitation (dashes optional) |
| `GET /api/fscs` | FSCs with RFQ counts, biggest first |
| `GET /api/profile` / `PUT /api/profile` | Read or replace the capability profile |
| `GET /api/matches` | RFQs matching the profile, with reasons and an `is_new` flag. Params: `include_dismissed`, `open_only` (default true), `new_only`, `limit`, `offset` |
| `POST /api/matches/seen` | Marks the current list as reviewed: everything in the DB stops counting as new |
| `PUT /api/triage/{solicitation}` | Body `{"state": "interested" \| "dismissed"}` |
| `DELETE /api/triage/{solicitation}` | Clears triage |
| `POST /api/refresh` | Starts a background scrape. Body `{}` (today), `{"date": "MM-DD-YYYY"}`, `{"from_file": "samples/page1.html"}` or `{"from_dir": "samples/11-19-2026"}` (load a saved day) |
| `GET /api/refresh` | Progress of the current or last refresh (pages, rows, inserted, updated, `new_matches`, error). `new_matches` = profile matches whose rows this refresh inserted |

Example: set a profile and fetch matches from the command line:
```bash
curl -X PUT localhost:8000/api/profile -H 'Content-Type: application/json' \
  -d '{"groups":[{"supplier":"Acme Cable","nsns":["8455-01-469-8015"],"fscs":["6145"],"keywords":["cable"]}]}'
curl 'localhost:8000/api/matches?limit=5'
```

### How matching works
- The **profile** is a list of capability groups: `{supplier?, nsns[], fscs[], keywords[]}`. A manufacturer
  uses one group. A distributor uses one group per supplier, so each match shows *who* can fill it.
- An RFQ matches if its NSN is listed (**score 3**), its FSC is listed (**score 2**) or its nomenclature
  contains a keyword (**score 1**). It gets the score of its strongest reason, and every reason is returned.
- An RFQ is **new** if it was first scraped after the last `POST /api/matches/seen`, based on `rfq.first_seen_at`.
- Results are sorted new first, then by score, then soonest `return_by`. Only `Open` RFQs are shown by
  default, and dismissed ones are hidden.
- Triage is stored per **solicitation**, so marking one line item marks the whole solicitation.

---

## Scraper internals

### What it does
For a given **issue date** (today by default), the scraper:
1. Accepts the DoD consent banner to get a session cookie
2. Opens the RFQ list for that date
3. Pages through every result page (50 rows per page)
4. Parses each row and **upserts** it into `dibbs.db`, page by page, so a failure keeps whatever was already ingested

Sample output:
```
page 1: 50 rows (50 new)
...
page 15: 41 rows (41 new)
Done 11-19-2026: 741 rows scraped, 741 new, 741 total in DB
```

### How it moves through DIBBS

| Step | Request | Notes |
|------|---------|-------|
| 1 | `GET https://www.dibbs.bsm.dla.mil/` | Redirects to `dodwarning.aspx?goto=/` (DoD consent banner) |
| 2 | `POST dodwarning.aspx?goto=%2f` with all hidden inputs + `butAgree=OK` | Sets the session cookies |
| 3 | `GET /RFQ/RfqRecs.aspx?category=issue&TypeSrch=dt&Value=MM-DD-YYYY` | Page 1 of the RFQs issued that day |
| 4 | `POST` to the same URL with the page's hidden fields + `__EVENTTARGET=ctl00$cph1$grdRfqSearch`, `__EVENTARGUMENT=Page$N` | ASP.NET GridView paging, repeated until there's no `Page$N+1` link |

There's a 0.5s delay between pages to be polite to the server.

### Things to know about DIBBS
- **A firewall blocks non-browser clients.** Requests without a browser-like `User-Agent`/`Accept`
  header get an F5 "Request Rejected" page. `HEADERS` in `scraper.py` handles this.
- **One row is one line item, not one solicitation.** A solicitation can contain several purchase
  requests (PRs). On 11-19-2026 there were 741 rows but only 638 unique solicitations, which is why the
  primary key is `(solicitation_number, pr_number, nsn)`.
- **Not every item has an NSN.** Some rows show a part number such as `0001S00000052` instead.
  These are stored as-is in `nsn`, so their `fsc` (`0001`) is meaningless.
- **Quantity is parsed from the PR cell** (`7018285296 QTY: 5000`). A few rows have no `QTY:` and get `NULL`.
- **Rows are parsed by element id suffix** (`lblNsn`, `lblNomenclature`, `lblSolicitation`, `lblStatus`),
  not by column position, so small layout changes are less likely to break the parser.
  Issued and Return By have no ids and are read by position (columns 8 and 9).

---

## Data model (SQLite, `dibbs.db`)

### `rfq`: one row per line item (owned by `schema.sql` / the scraper)

| Column | Example | Notes |
|--------|---------|-------|
| `solicitation_number` | `SPE1C1-27-Q-0056` | Part of the PK |
| `pr_number` | `7018285296` | Purchase request, part of the PK |
| `nsn` | `8455014698015` | 13 digits without dashes (or a part number), part of the PK |
| `fsc` | `8455` | Federal Supply Class = first 4 digits of the NSN |
| `nomenclature` | `GROUP-RATE MARK` | Short item description |
| `quantity` | `5000` | May be `NULL` |
| `issue_date` | `2026-11-19` | ISO date |
| `return_by` | `2026-11-26` | ISO date, the quote deadline |
| `status` | `Open` / `Removed` | |
| `dibbs_url` | `https://www.dibbs.bsm.dla.mil/rfq/rfqrec.aspx?sn=SPE1C127Q0056` | Package View on DIBBS |
| `scraped_at` | `2026-11-19T17:35:32+00:00` | UTC, last time this row was seen |
| `first_seen_at` | `2026-11-19T17:35:32+00:00` | UTC, first time this row was seen. Never updated, so it drives "new" matches |

Indexes on `fsc`, `nsn` and `issue_date`. The API also returns `nsn_display` (`8455-01-469-8015`) and
`nsn_url` (the DIBBS NSN view) on every row.

### `profile`, `triage` and `app_state` (created by `api.py`)

| Table | Columns | Notes |
|---|---|---|
| `profile` | `id` (always 1), `data` (JSON `{"groups": [...]}`) | One hardcoded profile, no auth |
| `triage` | `solicitation_number` (PK), `state` (`interested`/`dismissed`), `updated_at` | Survives re-scrapes |
| `app_state` | `key` (PK), `value` | Small key-value store, e.g. `matches_seen_at` |

### Viewing the data

```bash
# Everything, readable
sqlite3 -header -column dibbs.db "select solicitation_number, nsn, nomenclature, quantity, return_by, status from rfq limit 20"

# Overview
sqlite3 dibbs.db "select count(*) rows, count(distinct solicitation_number) sols, count(distinct fsc) fscs from rfq"

# Biggest FSCs
sqlite3 -header -column dibbs.db "select fsc, count(*) n from rfq group by fsc order by n desc limit 10"

# Keyword search on the description
sqlite3 -header -column dibbs.db "select solicitation_number, nomenclature, dibbs_url from rfq where nomenclature like '%CABLE%'"

# Closing soonest
sqlite3 -header -column dibbs.db "select solicitation_number, nomenclature, return_by from rfq where status='Open' order by return_by limit 10"

# Current profile and triage
sqlite3 dibbs.db "select data from profile"
sqlite3 -header -column dibbs.db "select * from triage"
```

For a GUI, open `dibbs.db` in [DB Browser for SQLite](https://sqlitebrowser.org/) or the
VS Code "SQLite Viewer" extension.

---

## Troubleshooting
- **UI says "Can't reach the API"**: start the backend (`.venv/bin/uvicorn api:app --reload --port 8000`).
  The Vite dev server proxies `/api` to port 8000.
- **UI is empty**: there's no data yet. Click **↻ Refresh from DIBBS**, or run
  `.venv/bin/python scraper.py --from-file samples/page1.html`.
- **`Could not accept DoD consent banner`** / refresh failed: the consent form changed or the firewall
  blocked the request. Try again, or load saved data (`--from-dir`, `--from-file`, or the "Load saved
  sample page instead" link in the UI). To save a fresh page, open the results page in your browser and
  use Save Page As… → HTML only.
- **0 rows for a date**: DIBBS only lists issue dates on `RfqDates.aspx?category=issue`. Weekends
  and dates older than about a month return nothing.
- **Parser broke after a DIBBS change**: refresh `samples/page1.html` from a live run and check
  the span ids that `parse_rows()` in `scraper.py` looks for.
- **Port already in use**: `lsof -i :8000` (or `:5173`) to find the old process and kill it.

---

## Scope and limitations
- **Single user**: one profile, no authentication or multi-tenancy.
- **Manual refresh**: data is fetched with the CLI or the refresh button; there is no scheduled job.
- **List fields only**: solicitation PDFs, tech docs, set-aside type and detail pages are not stored.
- **Not included**: price/award history, email digests, fuzzy or semantic matching.

## Roadmap
- Scheduled daily scrape
- Email digest of new matches
- Set-aside and tech-doc fields, so vendors can filter on small-business set-asides
- Award history per NSN, to show what it last sold for
