to objectify what's being sold

Any 10mm screw, it get's an NSN Part Number : Nomenclature is for extra info,

Then if the part has technical document -> drawing
Solicitation, the idea of the contract, can be removed, will show in RFQ Status


First four digits of the NSN: more general identifier for group of parts



antek@salespatriot.com



No right or wrong

There's two entities:
- Manufacturers
- Distributors: don't make anything specifically but have a network of suppliers that




## approach

Functional Requirements:
- 

Entities:
- RFQ(Date, Solicitation Number, NSN number, Nomenclature[], purchase request, Issued, Return By)

SQL database:
- each record is an RFQ row, with the columns being (Date, Solicitation Number, NSN number, Nomenclature[], purchase request, Issued, Return By)


---

## Suggested plan (Claude)

### Core idea
The DIBBS page makes the vendor scan everything. Flip it: the vendor says once **what they can supply** (NSNs, FSCs, keywords), and every day the app shows **only the RFQs that match**, ranked, with a quick triage flow. Same thing works for manufacturers (what I make) and distributors (what my suppliers make).

### Functional requirements
1. **Ingest**: scrape today's RFQs from DIBBS (RFQs by issue date → today, all pages) and upsert into the DB by solicitation number. Can be re-run without duplicates.
2. **Browse**: fast table of today's RFQs with search, sort and filters (FSC, open/removed status, tech docs yes/no, quantity, return-by date).
3. **Capability profile**: user enters what they can supply: a list of NSNs, FSCs, and keywords. Distributors can group these per supplier.
4. **My matches view** (the main screen): only RFQs matching the profile, with *why* it matched (exact NSN > FSC > keyword) and sorted by match strength and then soonest deadline.
5. **Triage**: mark each RFQ as Interested / Dismissed so the daily list gets worked down to zero.
6. **Open on DIBBS**: every row links back to its original DIBBS page.

### Data (additions to my entity)
- RFQ: add `fsc` (first 4 digits of NSN, derived), `quantity`, `status`, `has_tech_docs`, `dibbs_url`, `scraped_at`
- Profile: `nsns[]`, `fscs[]`, `keywords[]` (+ optional supplier name)
- Triage: `solicitation_number` → `interested | dismissed`

### Build order (50 min)
1. Scraper → SQLite with real data (~15 min). Fallback: save one page of HTML locally and parse it, so the demo never depends on DIBBS being up.
2. API + browse table with search/filters and DIBBS links (~15 min)
3. Profile + "My matches" + match reason (~15 min)
4. Triage buttons, then polish if time is left (~5 min)

### Deliberately left out (talk about in the demo)
- Auth / multi-tenant, so one hardcoded profile
- Scheduled daily cron, so a "Refresh" button / manual script instead
- Parsing solicitation PDFs, price history, award data, email digests of new matches
- Smarter matching (fuzzy/semantic on nomenclature) instead of exact NSN/FSC/keyword
