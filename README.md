# DIBBS Solicitation Browser

Pulls the daily RFQs (Requests for Quotation) that the Defense Logistics Agency posts on
[DIBBS](https://www.dibbs.bsm.dla.mil/), stores them in SQLite, and shows a vendor only the ones
they can actually supply, so they don't have to click through thousands of rows by hand.

```
DIBBS website ──scraper.py──▶ dibbs.db (SQLite) ◀──api.py (FastAPI :8000)──▶ frontend (React + Vite :5173)
```

**Status:** all four phases work: scraper + database, API, browse UI, capability profile with
"My matches", and Interested/Dismissed triage.

---

## Run the demo (first time)

You need Python 3 and Node 18+. Run each block from the project root.

```bash
# 1. Backend dependencies (one time)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Frontend dependencies (one time)
cd frontend && npm install && cd ..

# 3. Load data into SQLite (pick one)
.venv/bin/python scraper.py                                  # live: today's RFQs from DIBBS (~45s, ~750 rows)
.venv/bin/python scraper.py --from-file samples/page1.html   # offline: 50 rows from the saved sample page
```

Then start the app in **two terminals**:

```bash
# Terminal 1: API on http://localhost:8000
.venv/bin/uvicorn api:app --reload --port 8000

# Terminal 2: UI on http://localhost:5173
cd frontend && npm run dev
```

Open **http://localhost:5173**. Step 3 is optional: the **↻ Refresh from DIBBS** button in the
header runs the same scrape from the UI. If DIBBS is down, the button offers
**"Load saved sample page instead"**.

### Demo walkthrough
1. **All RFQs** tab: search and filter today's RFQs. Every row links back to DIBBS.
2. **Profile** tab: enter the NSNs, FSCs and keywords you can supply. Distributors can add one group per supplier.
3. **My matches** tab: only the RFQs that match, with the reason (exact NSN > FSC > keyword), sorted by match strength and then the soonest return-by date.
4. Mark each one **Interested** or **Dismissed** to work the list down to zero.

---

## Command cheat sheet

### Setup
| Command | What it does |
|---|---|
| `python3 -m venv .venv` | Creates the Python virtualenv |
| `.venv/bin/pip install -r requirements.txt` | Installs requests, beautifulsoup4, fastapi, uvicorn |
| `cd frontend && npm install` | Installs React + Vite |

### Scraper (data in)
| Command | What it does |
|---|---|
| `.venv/bin/python scraper.py` | Scrapes all of **today's** RFQs from DIBBS into `dibbs.db` |
| `.venv/bin/python scraper.py --date 11-18-2026` | Scrapes a specific issue date (`MM-DD-YYYY`) |
| `.venv/bin/python scraper.py --max-pages 2` | Quick test: only the first 2 pages (100 rows) |
| `.venv/bin/python scraper.py --from-file samples/page1.html` | **Offline**: parses one saved page, no network |
| `.venv/bin/python scraper.py --save-dir samples/11-19-2026` | Live scrape that also saves each raw page as `page-N.html` |
| `.venv/bin/python scraper.py --from-dir samples/11-19-2026` | **Offline**: replays a whole day saved with `--save-dir` |
| `.venv/bin/python scraper.py --db other.db` | Writes to a different database file |

Re-running is safe: rows are upserted, never duplicated. Tip: run one live scrape with `--save-dir`
before the demo, so you can replay the full day offline with `--from-dir` if DIBBS is down.

### Backend (API)
| Command | What it does |
|---|---|
| `.venv/bin/uvicorn api:app --reload --port 8000` | Starts the API with auto-reload |
| `DIBBS_DB=other.db .venv/bin/uvicorn api:app --port 8000` | Points the API at a different database |
| open http://localhost:8000/docs | Interactive Swagger docs, where you can try every endpoint |
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
| `sqlite3 -header -column dibbs.db "select * from rfq limit 10"` | Peek at the data |
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
| `api.py` | FastAPI backend: browse/search, profile, matching, triage, and refresh (creates the `profile` and `triage` tables) |
| `frontend/` | React + Vite single-page app |
| `frontend/src/App.jsx` | Header (stats + refresh button) and tabs |
| `frontend/src/Matches.jsx` | "My matches" view |
| `frontend/src/Browse.jsx` | "All RFQs" table with search and filters |
| `frontend/src/Profile.jsx` | Capability profile editor |
| `frontend/src/api.js` | Thin fetch client for the API |
| `samples/page1.html` | A saved DIBBS results page, for offline demos and testing |
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
| `POST /api/matches/seen` | "I've gone through my list": everything in the DB now stops counting as new |
| `PUT /api/triage/{solicitation}` | Body `{"state": "interested" \| "dismissed"}` |
| `DELETE /api/triage/{solicitation}` | Clears triage |
| `POST /api/refresh` | Starts a background scrape. Body `{}` (today), `{"date": "MM-DD-YYYY"}`, `{"from_file": "samples/page1.html"}` or `{"from_dir": "samples/11-19-2026"}` (offline replay of a saved day) |
| `GET /api/refresh` | Progress of the current or last refresh (pages, rows, inserted, updated, `new_matches`, error). `new_matches` = profile matches whose rows this refresh inserted |

Example: set up a profile and get matches from the command line:
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

## Scraper

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

DIBBS keeps about the last month of issue dates (see `RfqDates.aspx?category=issue`), so you can
backfill by running `--date` once per day:
```bash
for d in 11-17-2026 11-18-2026; do .venv/bin/python scraper.py --date $d; done
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

# Biggest FSCs today
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
  blocked the request. Try again, or use the sample page (`--from-file`, or the "Load saved sample page
  instead" link in the UI). To save a fresh page, open the results page in your browser and use
  Save Page As… → HTML only.
- **0 rows for a date**: DIBBS only lists issue dates on `RfqDates.aspx?category=issue`. Weekends
  and dates older than about a month return nothing.
- **Parser broke after a DIBBS change**: refresh `samples/page1.html` from a live run and check
  the span ids that `parse_rows()` in `scraper.py` looks for.
- **Port already in use**: `lsof -i :8000` (or `:5173`) to find the old process and kill it.

---

## Deliberately left out
- **Auth / multi-tenant**: one hardcoded profile.
- **Scheduled daily scrape**: manual refresh (button or CLI) instead.
- **Solicitation PDFs, tech docs, set-aside type, detail pages**: only the list-table fields are stored.
- **Price / award history, email digests, fuzzy or semantic matching.**

## Roadmap
- Scheduled daily scrape
- Email digest of new matches
- Set-aside and tech-doc fields, so vendors can filter on small-business set-asides
- Award history per NSN, to show what it last sold for
