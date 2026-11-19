# Sales Patriot: DIBBS Solicitation Browser

A **50-minute** on-site take-home for Sales Patriot. Build a full-stack web app that pulls the day's RFQs from DIBBS (https://www.dibbs.bsm.dla.mil/) and helps a vendor find the ones worth quoting on. This is rapid prototyping: a working MVP that shows clear thinking beats polished-but-incomplete. **Never get stuck on perfection; keep moving.**

Source docs: `SP_opportunities_page_task (3) (1).pdf` (the assignment), `Briefing.md` (interview transcript with domain context), `Notes.md` (my notes + plan).

## Hard requirements (from the assignment)
1. **Pull data from DIBBS**: at minimum solicitation number + NSN per RFQ. More fields welcome.
2. **Browse** the solicitations.
3. **Find the opportunities they care about**: approach is up to us.
4. **Open each row** back on its original DIBBS page.

Graded on: how users find opportunities (and why), problem-solving, judgment/tradeoffs (incl. what we left out), and product sense.

## Domain in 30 seconds
- **DIBBS** posts 700 to 5,000 new RFQs every weekday. Path: RFQs → RFQs by issue date → today.
- **NSN** (e.g. `8455-01-469-8015`): normalized government part number. **FSC** = first 4 digits (`8455`), a broader part class. Vendors mentally filter by NSN they know, then FSC, then by eyeballing the nomenclature.
- **Users**: *manufacturers* (know what they make) and *distributors* (make nothing; supply via a network of manufacturer suppliers).
- Today they click through every page by hand. We flip it: the vendor says once what they can supply, and the app shows only the matches.

## Product plan
**Core idea**: a capability profile (NSNs, FSCs, keywords; distributors can group these per supplier) → a "My matches" view showing only matching RFQs, with *why* each matched (exact NSN > FSC > keyword), sorted by match strength and then soonest return-by date, plus Interested / Dismissed triage so the daily list gets worked down to zero.

**Build order**
1. **Scraper → SQLite with real data** (~15 min) ← *current focus*
2. API + browse table with search/filters and DIBBS links (~15 min)
3. Profile + "My matches" + match reason (~15 min)
4. Triage buttons, then polish (~5 min)

**Deliberately left out** (for the demo talk): auth/multi-tenant (one hardcoded profile), daily cron (manual refresh instead), parsing solicitation PDFs, price/award history, email digests, fuzzy/semantic matching.

## Stack
- Python 3, `requests` + `beautifulsoup4` (see `requirements.txt`), venv at `.venv/`.
- SQLite (`*.db` is gitignored).
- Backend/frontend for steps 2-4: keep it simple (e.g. FastAPI or Flask + a single-page frontend). Choose whatever ships fastest.

## Current task: the scraper

### Goal
`python scraper.py` scrapes today's RFQs (all pages) and **upserts** them into SQLite keyed on solicitation number. Re-running must not create duplicates. Also support parsing a local HTML file (`samples/page1.html`) so the demo never depends on DIBBS being up.

### Schema (`rfqs` table)
| column | notes |
|---|---|
| `solicitation_number` | PK, normalized without dashes, e.g. `SPE1C127Q0056` (keep the display form `SPE1C1-27-Q-0056` too) |
| `nsn` | digits only, e.g. `8455014698015` (keep the display form too) |
| `fsc` | derived: first 4 digits of the NSN |
| `nomenclature` | e.g. `GROUP-RATE MARK` |
| `has_tech_docs` | bool |
| `status` | e.g. `Open`; others can be removed/not biddable |
| `purchase_request` | PR number |
| `quantity` | int, parsed from `QTY: 5000` |
| `issued` | ISO date (source is `MM-DD-YYYY`) |
| `return_by` | ISO date |
| `set_aside` | optional, from the icon alt text (e.g. `Unrestricted/Not Set Aside`) |
| `dibbs_url` | link back to DIBBS (see below) |
| `rfq_pdf_url` | solicitation PDF link |
| `scraped_at` | timestamp |

Later steps will add `profile` (nsns[], fscs[], keywords[], optional supplier name) and `triage` (solicitation_number → interested | dismissed) tables. Don't build those yet.

### What we know about the page (from `samples/page1.html`)
- Saved results page title: "DIBBS RFQ Search Results". **741 records** on the sample day (`#ctl00_cph1_lblRecCount` → "Records Found: 741"), **50 rows per page** (so about 15 pages).
- It's an ASP.NET WebForms GridView: table `#ctl00_cph1_grdRfqSearch`. Each data row is a `<tr>` whose cells contain spans with IDs `ctl00_cph1_grdRfqSearch_ctlNN_<field>`:
  - `lblRowNum`, `lblNsn` (contains `<a>` with NSN text, e.g. `8455-01-469-8015`; may carry an extra tag like "Mil-Spec"), `lblNomenclature`, `lblTechnicalDocuments` (has a "Tech Docs" link when present), `lblSolicitation` (`<a>` to the PDF `https://dibbs2.bsm.dla.mil/Downloads/RFQ/<n>/<SOL>.PDF`, a "Package View" link `https://www.dibbs.bsm.dla.mil/rfq/rfqrec.aspx?sn=<SOL>`, and a set-aside icon `<img alt=...>`), `lblStatus` (text like `Open`), `lblPr` (`7018285296<br />QTY: 5000`), `lblIssued`, `lblReturnBy`.
  - Easiest robust approach: select `span[id$="_lblSolicitation"]` and so on, or iterate rows and look up spans by ID suffix.
- **Pagination is ASP.NET postback**: links are `javascript:__doPostBack('ctl00$cph1$grdRfqSearch','Page$2')` … `Page$Last`. To fetch page N, POST the same URL with all hidden form fields from the previous response (`__VIEWSTATE` (it may be split into `__VIEWSTATE1..N` with `__VIEWSTATEFIELDCOUNT`), `__VIEWSTATEGENERATOR`, `__EVENTVALIDATION`, `__VIEWSTATEENCRYPTED`, etc.) plus `__EVENTTARGET=ctl00$cph1$grdRfqSearch` and `__EVENTARGUMENT=Page$N`. Use one `requests.Session()` throughout. The pager only shows ~10 page numbers at a time, so just keep requesting `Page$N+1` until a page returns no new solicitations (or you reach the record count).
- **DoD consent banner**: DIBBS shows a "DoD warning / I agree" page first and sets a cookie on accept. If the first GET redirects to a warning page, submit its accept form (or set the consent cookie) in the session, then retry. Inspect what actually comes back. Don't guess.
- Find the "RFQs by issue date → today" URL by navigating from https://www.dibbs.bsm.dla.mil/RFQ/ (look for the "by issue date" link). Hard-code it once found.

### "Open on DIBBS" link
Use the Package View URL `https://www.dibbs.bsm.dla.mil/rfq/rfqrec.aspx?sn=<SOLICITATION_NO_DASHES>` as `dibbs_url`. The NSN view `https://www.dibbs.bsm.dla.mil/RFQ/RFQNsn.aspx?value=<NSN_DIGITS>&category=issue&Scope=` is also available if useful.

### Done when
- `python scraper.py --file samples/page1.html` parses the sample page into the DB (offline fallback works).
- `python scraper.py` (live) pulls all of today's pages, or degrades gracefully: log the failure and keep whatever was ingested.
- Re-running is idempotent (upsert on `solicitation_number`).
- It prints a short summary: pages fetched, rows parsed, rows inserted/updated, and a few sample rows.
- If a live scrape works, save one or two more raw pages into `samples/` for offline dev.

## Working conventions
- Speed over completeness. Small, readable files. No heavy frameworks or abstractions.
- Be polite to DIBBS: one session, sequential requests, a small delay between pages, a normal browser User-Agent.
- Don't commit `.venv/` or `*.db`.
