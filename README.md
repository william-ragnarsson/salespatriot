# DIBBS Solicitation Browser

Pulls the daily RFQs (Requests for Quotation) that the Defense Logistics Agency posts on
[DIBBS](https://www.dibbs.bsm.dla.mil/) and stores them in SQLite, so vendors can find the ones
worth quoting on without clicking through thousands of rows by hand.

**Status:** phase 1 (scraper + database) is done. The API and UI for browsing and matching are next.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scraper.py          # scrape today's RFQs into dibbs.db (~45s for ~750 rows)
sqlite3 -header -column dibbs.db "select * from rfq limit 10"
```

Requires Python 3 and the `sqlite3` CLI (preinstalled on macOS) for viewing the data.

## Project layout

| File | Purpose |
|------|---------|
| `scraper.py` | Fetches RFQs from DIBBS for one issue date, parses them and upserts them into SQLite |
| `db.py` | `connect()` (creates the schema if missing) and `upsert_many()` |
| `schema.sql` | The `rfq` table and indexes |
| `samples/page1.html` | A saved DIBBS results page, for offline parsing and testing |
| `dibbs.db` | The SQLite database (gitignored, created on first run) |

---

## Scraper

### What it does
For a given **issue date** (today by default), the scraper:
1. Accepts the DoD consent banner to get a session cookie
2. Opens the RFQ list for that date
3. Pages through every result page (50 rows per page)
4. Parses each row and **upserts** it into `dibbs.db`

Re-running it is safe: existing rows are updated (e.g. a status change to `Removed`) and nothing is duplicated.

### Usage

```bash
.venv/bin/python scraper.py                                  # today
.venv/bin/python scraper.py --date 11-18-2026                # a specific issue date (MM-DD-YYYY)
.venv/bin/python scraper.py --max-pages 2                    # quick test: only the first 2 pages
.venv/bin/python scraper.py --from-file samples/page1.html   # offline: parse a saved page, no network
.venv/bin/python scraper.py --db other.db                    # write to a different database file
```

Sample output:
```
page 1: 50 rows (50 new)
...
page 15: 41 rows (41 new)
Done 11-19-2026: 741 rows scraped, 741 new, 741 total in DB
```

DIBBS keeps about the last month of issue dates (see `RfqDates.aspx?category=issue`), so you can
backfill by running `--date` once per day, e.g.:
```bash
for d in 11-17-2026 11-18-2026; do .venv/bin/python scraper.py --date $d; done
```

### How it moves through DIBBS

| Step | Request | Notes |
|------|---------|-------|
| 1 | `GET https://www.dibbs.bsm.dla.mil/` | Redirects to `dodwarning.aspx?goto=/` (DoD consent banner) |
| 2 | `POST dodwarning.aspx?goto=%2f` with all hidden inputs + `butAgree=OK` | Sets the session cookies |
| 3 | `GET /RFQ/RfqRecs.aspx?category=issue&TypeSrch=dt&Value=MM-DD-YYYY` | Page 1 of the RFQs issued that day |
| 4 | `POST` to the same URL with the page's hidden fields + `__EVENTTARGET=ctl00$cph1$grdRfqSearch`, `__EVENTARGUMENT=Page$N` | ASP.NET GridView paging; repeated until there's no `Page$N+1` link |

There's a 0.5s delay between pages to be polite to the server.

### Things to know about DIBBS
- **A firewall blocks non-browser clients.** Requests without a browser-like `User-Agent`/`Accept`
  header get an F5 "Request Rejected" page. `HEADERS` in `scraper.py` handles this.
- **One row is one line item, not one solicitation.** A solicitation can contain several purchase
  requests (PRs). On 11-19-2026 there were 741 rows but only 638 unique solicitations, which is why the
  primary key is `(solicitation_number, pr_number, nsn)`.
- **Not every item has an NSN.** Some rows show a part number such as `0001S00000052` instead.
  These are stored as-is in `nsn`, which makes their `fsc` (`0001`) meaningless.
- **Quantity is parsed from the PR cell** (`7018285296 QTY: 5000`). A few rows have no `QTY:` and get `NULL`.
- **Rows are parsed by element id suffix** (`lblNsn`, `lblNomenclature`, `lblSolicitation`, `lblStatus`),
  not by column position, so small layout changes are less likely to break the parser.
  Issued and Return By have no ids and are read by position (columns 8 and 9).

### Data model

Table `rfq`, one row per line item:

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

Indexes on `fsc`, `nsn` and `issue_date`.

**Deliberately left out for now:** technical documents and solicitation PDFs, set-aside type,
award/price history and the detail pages. Only the list-table fields are stored.

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

# Export to CSV
sqlite3 -header -csv dibbs.db "select * from rfq" > rfq.csv
```

For a GUI, open `dibbs.db` in [DB Browser for SQLite](https://sqlitebrowser.org/) or the
VS Code "SQLite Viewer" extension.

From Python:
```python
import db
conn = db.connect()
rows = conn.execute("select * from rfq where fsc = ?", ("6515",)).fetchall()
```

### Troubleshooting
- **`Could not accept DoD consent banner`**: the consent form changed or the firewall blocked the
  request. Try again, or use `--from-file` with a page saved from your browser (on the results
  page, use Save Page As… → HTML only).
- **0 rows for a date**: DIBBS only lists issue dates on `RfqDates.aspx?category=issue`. Weekends
  and dates older than about a month return nothing.
- **Parser broke after a DIBBS change**: refresh `samples/page1.html` from a live run and check
  the span ids that `parse_rows()` in `scraper.py` looks for.

---

## Roadmap
- **API + UI:** a browse table with search and filters, and a link out to DIBBS on every row
- **Supply profile:** the NSNs, FSCs and keywords a vendor can supply (or that their suppliers can)
- **My matches:** RFQs ranked by match strength (exact NSN > FSC > keyword), then by deadline
- **Triage:** mark RFQs Interested or Dismissed so the daily list gets worked down to zero
- **Later:** a scheduled daily scrape, "new since yesterday", email digests
