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

## Spikes (BESLIST via metingen — docs/superpowers/specs/2026-06-19-kinderkaart-spike-outcomes.md)
- [x] Spike 1 (search): client-side FlexSearch (~0.2MB gz, ~3.8ms query). NO Vercel.
- [x] Spike 2 (tile/cluster): client point index 0.54MB gz + Supercluster (idx 280ms, getClusters 0.04-0.13ms). NO PMTiles. Correctness oracle passes by construction. Detail = sharded JSON.
- Architecture simplified: fully static on GitHub Pages (no Vercel/PMTiles/Releases). Real browser render-latency deferred to Plan 5 (Playwright).

## Plan 4 — Build + Publish (docs/superpowers/plans/2026-06-19-kinderkaart-build-publish.md)
- [x] Task 1: shared fnv1a hash
- [x] Task 2: points-index builder
- [x] Task 3: detail-shard builder + lookup
- [x] Task 4: publish-gate
- [x] Task 5: build CLI (artifacts + manifest + last-known-good)

Plan 4: complete (commits 032258b..83cb076, 91 tests green). END-TO-END SMOKE PASSED: 5 fixtures -> 9 SourcePOI -> merge -> 9 CanonicalPOI -> artifacts (points/detail/license/manifest) with correct category counts.
