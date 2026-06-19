# Kinderkaart — subagent-driven execution ledger

Plan: docs/superpowers/plans/2026-06-19-kinderkaart-data-foundation.md
Branch: kinderkaart-data-foundation
Base (branch start): main @ bd028e6

## Plan 1 — Data Foundation
- [x] Task 1: project setup + vocab + tooling
- [x] Task 2: shared facet model + SourcePOI
- [x] Task 3: manifest model + JSON schema export
- [x] Task 4: adapter base (envelope, http, ndjson, cli)
- [x] Task 5: wikidata-museums adapter
- [x] Task 6: _template + manifest guard

Plan 1: complete (commits 64f9c7f..9c5fb9e, review clean after 1 fix round). 42 tests green.
KNOWN: download() single-attempt streaming, no retry — Plan 2 must add retry around .pbf stream.

## Plan 2 — Adapters (docs/superpowers/plans/2026-06-19-kinderkaart-adapters.md)
- [x] Task 1: path-based normalize contract + retrying streamed download
- [x] Task 2: RD->WGS84 reprojection helper (+ osmium/pyproj deps)
- [x] Task 3: RCE musea adapter
- [x] Task 4: Den Haag speeltuinen adapter
- [x] Task 5: Eindhoven adapter + shared geojson helper
- [x] Task 6: OSM adapter (osmium)

Plan 2: complete (commits 23a49a7..57b9c3f, review clean after 1 fix round; C1 address regression + I2 stable ids fixed). 52 tests green.

## Plan 3 — Merge + Identity (docs/superpowers/plans/2026-06-19-kinderkaart-merge-identity.md)
- [x] Task 1: CanonicalPOI/SourceRef + external_ids on SourcePOI
- [x] Task 2: normalization + haversine helpers
- [x] Task 3: matcher (blocking, strong keys, scoring, union-find)
- [x] Task 4: field merge -> CanonicalPOI
- [x] Task 5: identity registry + transition table
- [x] Task 6: merge CLI + overrides

Plan 3: complete (commits 8b77aa6..8a42252, opus review found C1/I1/I2/M1, fixed; 79 tests green, identity logic deterministic).
