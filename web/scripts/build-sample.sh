#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
W=$(mktemp -d)
for s in wikidata_museums:wikidata_museums_response.json rce_musea:rce_musea_response.json \
         den_haag_speeltuinen:den_haag_response.json eindhoven_speeltuinen:eindhoven_response.json; do
  pkg="${s%%:*}"; fix="${s##*:}"
  uv run python -m "sources.${pkg}.adapter" normalize "tests/fixtures/${fix}" \
    --fetched-at 2026-06-19T00:00:00+00:00 > "$W/${pkg}.ndjson"
done
uv run python -m sources.osm.adapter normalize tests/fixtures/osm_sample.osm \
  --fetched-at 2026-06-19T00:00:00+00:00 > "$W/osm.ndjson"
uv run python -m data_pipeline.merge --identity "$W/id.json" --out "$W/canon.ndjson" \
  --build-version sample "$W"/*.ndjson
uv run python -m data_pipeline.build --canon "$W/canon.ndjson" --sources sources \
  --out web/public --country nl --data-version sample \
  --require osm,rce-musea,wikidata-museums,den-haag-speeltuinen,eindhoven-speeltuinen
rm -rf "$W"
echo "Sample data built → web/public/data/"
