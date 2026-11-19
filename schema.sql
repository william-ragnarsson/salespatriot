-- One row per line item: a solicitation can contain several purchase requests (PRs).
CREATE TABLE IF NOT EXISTS rfq (
  solicitation_number TEXT NOT NULL,      -- e.g. SPE1C1-27-Q-0056
  nsn                 TEXT NOT NULL,      -- 13 digits, dashes stripped (or part number if no NSN)
  fsc                 TEXT NOT NULL,      -- first 4 digits of nsn (Federal Supply Class)
  nomenclature        TEXT,
  pr_number           TEXT,
  quantity            INTEGER,
  issue_date          TEXT,               -- ISO yyyy-mm-dd
  return_by           TEXT,               -- ISO yyyy-mm-dd
  status              TEXT,               -- Open / Removed / ...
  dibbs_url           TEXT NOT NULL,      -- link back to DIBBS package view
  scraped_at          TEXT NOT NULL,      -- last time this row was seen
  first_seen_at       TEXT,               -- first time this row was seen; never updated
  PRIMARY KEY (solicitation_number, pr_number, nsn)
);
CREATE INDEX IF NOT EXISTS idx_rfq_fsc   ON rfq(fsc);
CREATE INDEX IF NOT EXISTS idx_rfq_nsn   ON rfq(nsn);
CREATE INDEX IF NOT EXISTS idx_rfq_issue ON rfq(issue_date);
