"""Scrape DIBBS RFQs for one issue date into SQLite.

Usage:
  python scraper.py                      # today
  python scraper.py --date 11-18-2026    # a specific issue date (MM-DD-YYYY)
  python scraper.py --from-file samples/page1.html   # offline, parse saved HTML
  python scraper.py --date 11-19-2026 --save-dir samples/11-19-2026   # also save raw pages
  python scraper.py --from-dir samples/11-19-2026    # offline, replay a saved day
"""
import argparse
import re
import time
from pathlib import Path
from datetime import date, datetime, timezone

import requests
from bs4 import BeautifulSoup

import db

BASE = "https://www.dibbs.bsm.dla.mil"
RECS_URL = BASE + "/RFQ/RfqRecs.aspx?category=issue&TypeSrch=dt&Value={date}"
GRID_ID = "ctl00_cph1_grdRfqSearch"
GRID_TARGET = "ctl00$cph1$grdRfqSearch"
HEADERS = {  # DIBBS' firewall rejects requests without browser-like headers
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def hidden_fields(soup):
    return {i["name"]: i.get("value", "") for i in soup.select("input[type=hidden]") if i.get("name")}


def session():
    """Session that has clicked through the DoD consent banner."""
    s = requests.Session()
    s.headers.update(HEADERS)
    r = s.get(BASE + "/", timeout=30)
    if "dodwarning" in r.url.lower():
        data = hidden_fields(BeautifulSoup(r.text, "html.parser"))
        data["butAgree"] = "OK"
        r = s.post(r.url, data=data, timeout=30)
        if "dodwarning" in r.url.lower():
            raise RuntimeError("Could not accept DoD consent banner")
    return s


def iso(d):
    try:
        return datetime.strptime(d.strip(), "%m-%d-%Y").date().isoformat()
    except ValueError:
        return None


def parse_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    grid = soup.find(id=GRID_ID)
    if grid is None:
        return []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for tr in grid.find_all("tr", recursive=False):
        if not (tr.get("class") and tr["class"][0] in ("BgWhite", "BgSilver")):
            continue  # skip header + pager rows
        get = lambda name: tr.find(id=re.compile(name + "$"))  # cells by span id suffix
        sol = get("lblSolicitation")
        pr_text = get("lblPRNumber") or tr.find_all("td", recursive=False)[6]
        pr_text = pr_text.get_text(" ", strip=True)
        qty = re.search(r"QTY:\s*([\d,]+)", pr_text)
        tds = tr.find_all("td", recursive=False)
        nsn_cell = get("lblNsn")  # NSN link, or a plain part number for non-NSN items
        nsn_el = nsn_cell.find("a") or nsn_cell
        nsn = re.sub(r"[^0-9A-Z]", "", next(nsn_el.stripped_strings, "").upper())
        pkg = sol.find("a", href=re.compile("rfqrec.aspx", re.I))
        sol_no = sol.find("a").get_text(strip=True)
        status_el = get("lblStatus")
        rows.append({
            "solicitation_number": sol_no,
            "nsn": nsn,
            "fsc": nsn[:4],
            "nomenclature": get("lblNomenclature").get_text(" ", strip=True),
            "pr_number": pr_text.split()[0] if pr_text else None,
            "quantity": int(qty.group(1).replace(",", "")) if qty else None,
            "issue_date": iso(tds[7].get_text()),
            "return_by": iso(tds[8].get_text()),
            "status": status_el.find("span").get_text(strip=True) if status_el and status_el.find("span") else None,
            "dibbs_url": pkg["href"] if pkg else f"{BASE}/rfq/rfqrec.aspx?sn={sol_no.replace('-', '')}",
            "scraped_at": now,
        })
    return rows


def fetch_date(s, value, delay=0.5, max_pages=500, save_dir=None):
    """Yield (page_no, rows) for every page of RFQs issued on `value` (MM-DD-YYYY).
    With save_dir, each raw page is also written to save_dir/page-N.html."""
    url = RECS_URL.format(date=value)
    if save_dir:
        Path(save_dir).mkdir(parents=True, exist_ok=True)
    r = s.get(url, timeout=60)
    page = 1
    while True:
        if save_dir:
            Path(save_dir, f"page-{page}.html").write_text(r.text)
        rows = parse_rows(r.text)
        yield page, rows
        soup = BeautifulSoup(r.text, "html.parser")
        nxt = f"Page${page + 1}"
        if not rows or page >= max_pages or nxt not in r.text:
            return
        data = hidden_fields(soup)
        data.update({"__EVENTTARGET": GRID_TARGET, "__EVENTARGUMENT": nxt})
        time.sleep(delay)
        r = s.post(url, data=data, timeout=60)
        page += 1


def replay_dir(path):
    """Yield (page_no, rows) from pages saved with --save-dir, in page order."""
    files = sorted(Path(path).glob("page-*.html"), key=lambda f: int(f.stem.split("-")[1]))
    if not files:
        raise FileNotFoundError(f"No page-N.html files in {path}")
    for f in files:
        yield int(f.stem.split("-")[1]), parse_rows(f.read_text())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().strftime("%m-%d-%Y"), help="MM-DD-YYYY")
    ap.add_argument("--from-file", help="parse a saved DIBBS results page instead of fetching")
    ap.add_argument("--from-dir", help="replay a day saved with --save-dir instead of fetching")
    ap.add_argument("--save-dir", help="also save each raw page to DIR/page-N.html")
    ap.add_argument("--db", default="dibbs.db")
    ap.add_argument("--max-pages", type=int, default=500)
    args = ap.parse_args()

    conn = db.connect(args.db)
    if args.from_file:
        rows = parse_rows(open(args.from_file).read())
        ins, upd = db.upsert_many(conn, rows)
        print(f"{len(rows)} rows from file: {ins} new, {upd} updated")
        return

    if args.from_dir:
        pages, label = replay_dir(args.from_dir), args.from_dir
    else:
        pages = fetch_date(session(), args.date, max_pages=args.max_pages, save_dir=args.save_dir)
        label = args.date
    total = ins_total = 0
    for page, rows in pages:
        ins, _ = db.upsert_many(conn, rows)
        total += len(rows)
        ins_total += ins
        print(f"page {page}: {len(rows)} rows ({ins} new)", flush=True)
    print(f"Done {label}: {total} rows scraped, {ins_total} new, "
          f"{conn.execute('SELECT COUNT(*) FROM rfq').fetchone()[0]} total in DB")


if __name__ == "__main__":
    main()
