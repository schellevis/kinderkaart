# Kinderkaart — Spike Outcomes (§9 search, §9b tile/cluster/detail)

**Datum:** 2026-06-19
**Status:** RESOLVED — both gating spikes decided by measurement. Front-end (Plan 5) and
build (Plan 4) are unblocked and simplified.

## Meetdataset (gepind)

Representative synthetic NL dataset, **42.080 POIs**, category mix proportional to the verified
OSM/research counts (playgrounds ~78%, pools ~13%, petting_zoo/museum/zoo/play_park/restaurant the
rest), uniformly distributed over the NL bounding box (50.75–53.55 N, 3.36–7.22 E), ~3% multi-category.
Generated deterministically (`random.seed(42)`). Measurements run on the dev machine
(Python 3.13 gzip level 9; Node v24, flexsearch 0.7.43, supercluster 8.0.1).

## Pre-registered thresholds vs. measured

| Metric | Threshold (spec §9/§9b) | Measured | Verdict |
|---|---|---|---|
| Points-index transfer (browse) | < 2 MB gz | **0.54 MB gz** (JSON w/ names); 0.40 MB gz (binary) | ✅ |
| Search-index transfer | < 1.5 MB gz | **0.20 MB gz** corpus (FlexSearch export comparable) | ✅ |
| Search query latency p | < 150 ms | **~3.8 ms** (1000 queries, 42k docs) | ✅ |
| Supercluster build/index | (one-time / on filter change) | **280 ms** for 42k pts | ✅ acceptable |
| Cluster query (pan/zoom) | < 100 ms | **0.04–0.13 ms** (`getClusters`, city→NL-wide) | ✅ |
| Detail-fetch shard size | ≤ ~50 KB gz | **~4.8 KB gz** (140 shards, 300 POIs each) | ✅ |
| Correctness oracle (§9b) | counts/members match canonical | **passes by construction** (see below) | ✅ |

## Decisions

### Spike 1 — Search architecture: **client-side index (FlexSearch). No Vercel.**
The static client-side index (route A) meets every threshold with large margin (0.2 MB gz,
~3.8 ms queries). It is free, privacy-friendly (no search text leaves the browser), and removes a
whole runtime dependency. The Vercel route (B) is **not adopted** for the MVP. Search runs fully
client-side; no `/api/search`, no Hobby-tier constraints.

### Spike 2 — Tile/cluster/detail model: **full client-side point index + Supercluster. No PMTiles.**
At NL scale the entire point set is a 0.54 MB gz file. Loading it fully and clustering with
Supercluster over the **filtered** set:
- makes the **correctness oracle pass by construction** — cluster counts and members are computed
  over the whole filtered canonical dataset, not over loaded-tile subsets, so the viewport-buffer
  truncation / MVT-scalar-encoding / per-filter-recompute problems that PMTiles raised (§9b) simply
  do not exist;
- is fast: re-index on filter change ≈ 280 ms; `getClusters` ≈ 0.04–0.13 ms per pan/zoom;
- keeps everything static and tiny.
PMTiles is **not adopted** for the point layer (it solved a "don't download all points" problem we
don't have at this scale). **Detail records** are sharded static JSON (`detail/<shard>.json`,
hash-modulo of `poi_id`, ~300 POIs / ~4.8 KB gz per shard), lazy-fetched on marker click; a deep-link
resolves a POI's shard from a small `index.json` lookup **without loading any map tile**.

### Hosting (resolved, simplified): **everything static on GitHub Pages. No Vercel, no GitHub Releases.**
Total payload (points 0.54 MB + search 0.2 MB + per-shard 4.8 KB on demand + basemap tiles from
PDOK) is ~1 MB and fits trivially within the GitHub Pages 1 GB limit. The earlier Releases-asset
hosting (chosen to get Range requests + immutable caching for large PMTiles) is **no longer needed**:
- artifacts are small JSON, no HTTP Range needed;
- versioning: artifacts live under `data/<land>/<data_version>/…` with content in the filenames; a
  small top-level `manifest.json` maps `land → data_version + artifact paths`. Atomic switch =
  publish the new versioned files, then update `manifest.json` last (single Pages deploy; old
  versioned files from the previous deploy are replaced — acceptable because clients fetch
  `manifest.json` first and immediately get matching versioned paths in the same deploy).
- GitHub Pages' default `Cache-Control: max-age=600` is fine: the manifest is re-fetched every 10 min
  at worst; versioned artifact paths change on each build so stale caching is harmless.

## What is explicitly deferred / a remaining doubt-case
- **Real in-browser interaction latency** (MapLibre render of clusters, marker draw, first paint on a
  mid-range mobile over throttled network) was NOT measured here — only the data sizes and the
  Supercluster/FlexSearch compute (which are negligible). This is validated for real in **Plan 5**
  using Playwright against the built front-end (render timing + a correctness-oracle test comparing
  on-screen cluster counts to a direct Supercluster run). If a real-device measurement later fails a
  threshold, revisit (regional sharding of the point index is the first lever).
- The meetdataset is **synthetic** (representative size/distribution), not the real merged pipeline
  output. Sizes scale with count and name length, both realistic here. Re-confirm against the real
  build in Plan 4.
