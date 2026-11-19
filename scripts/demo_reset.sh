#!/usr/bin/env bash
# Reset to a known demo state: 11-17 + 11-18 are "history", the profile is set,
# and everything is marked seen. Then refresh with 11-19 on camera to show new matches.
# Needs the API running: .venv/bin/uvicorn api:app --reload
set -euo pipefail
cd "$(dirname "$0")/.."
API=${API:-http://localhost:8000}
DB=${DIBBS_DB:-dibbs.db}   # must be the same DB the API uses

rm -f "$DB"
.venv/bin/python scraper.py --from-dir samples/11-17-2026 --db "$DB" | tail -1
.venv/bin/python scraper.py --from-dir samples/11-18-2026 --db "$DB" | tail -1
curl -sf -X PUT "$API/api/profile" -H 'content-type: application/json' -d @demo_profile.json > /dev/null
curl -sf -X POST "$API/api/matches/seen"; echo
echo "Ready. Now: curl -X POST $API/api/refresh -H 'content-type: application/json' -d '{\"from_dir\":\"samples/11-19-2026\"}'"
