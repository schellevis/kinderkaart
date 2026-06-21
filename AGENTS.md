# Kinderkaart — project guide for Claude / agents

> **CLAUDE.md ⇄ AGENTS.md:** these two files MUST stay **byte-for-byte identical**. After any
> relevant change, edit one and `cp CLAUDE.md AGENTS.md` (or vice versa). Do not let them diverge.

## What this is

A **static** web app with a map interface showing fun things to do with children in the
Netherlands (playgrounds, museums, zoos/petting zoos, pools, play parks, kid-friendly
restaurants), with search + filtering. Netherlands first; architecture is multi-country-ready.
Everything runs from **GitHub Pages** — no server, no Vercel.

Operational procedures (codespace-only sources, deploy, rollback) live in `docs/RUNBOOK.md`.

## Architecture (resolved by measurement)

```
sources/<id>/ (manifest.yaml + adapter)         Python pipeline (uv)
   snapshot -> raw + envelope                    data_pipeline/
   normalize -> SourcePOI (NDJSON)                  merge.py  -> CanonicalPOI + identity registry
        \__________________________________________/   |
                                                        build.py -> static artifacts:
   data/<country>/<data_version>/                          points.json (client point index)
       points.json · detail/<shard>.json · license.json    detail shards · license report
   data/manifest.json (country -> version + paths)       + manifest.json (atomic switch, last)
                                                        |
   web/ (Vite + TS + MapLibre)  <— fetches manifest -> points.json; builds a Supercluster index
       over the FILTERED set (clusters always correct), client-side FlexSearch-style search,
       lazy detail shards (fnv1a(poi_id) % shard_count). 100% static on GitHub Pages.
```

- **No PMTiles, no Vercel, no GitHub Releases.** At NL scale (~40–60k POIs) the whole point set is
  ~0.5 MB gz; loading it fully and clustering client-side over the filtered set makes cluster
  counts correct under any filter combination. Measured: search query ~4 ms, getClusters
  ~0.1 ms, total payload ~1 MB.

## Repo layout

- `data_pipeline/` — shared Python pipeline: `schema.py` (SourcePOI/CanonicalPOI/SourceRef/Manifest
  fields), `manifest.py`, `adapter_base.py` (HTTP + envelope + file/stream CLI), `textnorm.py`,
  `geodist.py`, `geo.py` (RD→WGS84), `matcher.py` (+ `merge_config.py`), `merge_fields.py`,
  `identity.py` (registry + transitions), `merge.py` (CLI), `hashing.py` (fnv1a), `build_points.py`,
  `build_detail.py`, `publish_gate.py`, `build_manifest.py`, `build.py` (CLI).
- `sources/<id>/` — one folder per data source: `manifest.yaml` + `adapter.py`. `_template/` is the
  copyable starting point. Implemented: `osm`, `wikidata_museums`, `rce_musea`,
  `den_haag_speeltuinen`, `eindhoven_speeltuinen` (all `github-action`); `restaurants_agent`,
  `museum_nl` (both `codespace-only`). `sources/manifest.schema.json` is the exported manifest JSON schema.
- `scripts/build_pipeline.py` — orchestrator: snapshot+normalize all included sources → merge →
  build. `--smoke` uses fixtures (no live fetch / no OSM download).
- `web/` — the front-end (`src/lib/*` pure logic with vitest; `src/map.ts`/`ui/*` MapLibre shell;
  `tests/e2e` Playwright). `web/public/data/` holds a small sample build for dev/e2e.
- `.github/workflows/` — **decoupled** so web changes don't rebuild data: `data-refresh.yml`
  (weekly cron + dispatch) runs the pipeline (the slow OSM build) and publishes built artifacts to
  the **`data` branch**; `deploy-pages.yml` (**push to `main` + manual dispatch**) builds the web app +
  publishes the `data` branch — **no pipeline run**, so a deploy takes ~2 min. First deploy
  requires `data-refresh` to have populated the `data` branch. `docs/RUNBOOK.md` covers ops.
  **TODO (perf):** the OSM normalize in `data-refresh` is ~30–45 min — a per-object Python loop over
  the full NL extract. Add an `osmium tags-filter` pre-pass in `sources/osm/` (reduce the pbf to
  relevant tags in C++ first) to cut it to ~1–2 min before leaning on the weekly cron.
- `tests/` — Python tests + `tests/fixtures/`.

## How to run

Python (uv at `/usr/local/py-utils/bin`; provisions Python 3.13):
- Install/lock: `uv sync`
- **Quality bar (run before every commit):**
  `uv run ruff check . && uv run mypy data_pipeline sources scripts && uv run pytest`
- End-to-end smoke (fixtures): `uv run pytest tests/test_build_pipeline.py` — or manually run an
  adapter `normalize`, then `python -m data_pipeline.merge`, then `python -m data_pipeline.build`.

Web (Node available; run from `web/`):
- `npm ci` · `npm run dev` · `npm run build` · `npm run preview`
- **Quality bar:** `npm run lint && npm run typecheck && npm run test`; e2e: `npm run e2e`
- Regenerate sample data: `web/scripts/build-sample.sh`.

## Adding a new data source (the core extensibility goal — an LLM should do this fast)

1. `cp -r sources/_template sources/<package_dir>` where `package_dir = manifest.id.replace("-", "_")`.
2. Edit `manifest.yaml`: `id` (kebab-case), `country`, `endpoint`, `license` + `license_url` +
   `license_evidence_date` + `republication_terms` (required), `runtime` (`github-action` or
   `codespace-only`), `category_map` (source key → our categories), `expected_count`.
3. Implement `adapter.py`:
   - `snapshot(output, *, client) -> SnapshotMetadata` — chunked download via `download(...)`.
   - `normalize(path, *, fetched_at) -> Iterator[SourcePOI]` — map records; set
     `field_provenance` for every field you populate; derive `categories` from `MANIFEST.category_map`
     (never hard-code); use a **stable** `source_record_id` (a source key, or a coord/content hash —
     never an enumeration index).
4. Add `tests/test_<package_dir>.py` with a small fixture asserting the normalized output.
5. Run the quality bar. The manifest guard test validates your manifest automatically.

## Invariants you must preserve

- **Two-phase model:** adapters emit `SourcePOI` (own `source_id`+`source_record_id`, no public id);
  the merge emits `CanonicalPOI` (stable `poi_id`, `aliases`, `contributing`, `build_version`).
- **Identity registry** (`data/<country>/identity.json`) is the single authoritative store of
  `poi_id` stability (mint/match/merge/split/tombstone). Never recompute `poi_id` from volatile
  state; never reuse an id for a different object. Deterministic + idempotent.
- **`fnv1a` parity:** `data_pipeline/hashing.py` and `web/src/lib/fnv1a.ts` MUST stay identical
  (same canonical vectors are asserted in both test suites). Shard lookup depends on it.
- **`cats` bitmask** order = `sorted(CATEGORIES)`, emitted in the manifest; the client decodes via
  that array (don't hard-code order on either side).
- **"Unknown is not negative":** a `null` facet must not be filtered out by a `true` filter.
- **URL allowlist:** any source-derived URL reaching `a.href` (web) or stored (Python) is http(s)
  only (`web/src/lib/url.ts` `safeHttpUrl`; `schema.py` validators). No `innerHTML` of untrusted data.
- **Deterministic builds:** sorted iteration, `sort_keys=True` JSON, artifacts sorted by `poi_id`.
- **`extra="forbid"`** on all contract models.

## Licensing & attribution (do not bypass)

- Published data layer is **ODbL** (share-alike) + visible "© OpenStreetMap contributors";
  CC-BY sources (PDOK, Den Haag, Eindhoven) get attribution from `license.json`; Wikidata/RCE are CC0.
- `museum-nl` — `codespace-only`, attribute "© Museumvereniging / museum.nl".
- `deploy-pages.yml` auto-deploys on push to `main` (+ manual dispatch). It only republishes the web
  app + the existing `data` branch (no data rebuild). Data changes go through `data-refresh` →
  `data` branch and do NOT auto-deploy.
- `restaurants-agent` is `codespace-only`, agent-curated, requires ≥1 **direct** kid-friendliness
  signal per record (evidence is auditable); excluded from CI.

## Status

All 7 plans + both spikes are implemented, tested, and reviewed (the `kinderkaart-data-foundation`
work is in `main`). The **museum-nl** source is implemented end-to-end and **merged to `main`**
(merge `0571ad3`; full suite green, ruff/mypy clean, opus whole-branch review = go).

### Go-live checklist (remaining before a public deploy)

Everything below is operational/decision work — no code blockers remain.

**DECIDED 2026-06-21:** v1 ships the **5 `github-action` sources** (osm, wikidata-museums,
rce-musea, den-haag-speeltuinen, eindhoven-speeltuinen) **+ `museum-nl`** (codespace-only, via the
committed-NDJSON route below). Only `restaurants-agent` is deferred (it has no real curated data
yet). So steps 1–3 are now **v1 work**.

1. ~~Merge `museum-nl-source` → `main`~~ — **done** (merge `0571ad3`).
2. **Get `museum-nl` data into the build: route DECIDED 2026-06-21 = commit NDJSON in
   `data/prebuilt/`.** The pipeline skips codespace-only sources in CI (they can't fetch). For v1:
   generate the NDJSON in a codespace and commit it as `data/prebuilt/museum-nl.ndjson` — the
   `data-refresh` job **auto-includes every `data/prebuilt/*.ndjson`** via `--prebuilt`, so no
   workflow edit is needed. See `docs/RUNBOOK.md` ("Committed-NDJSON route for codespace-only data").
3. **museum.nl specifics (ships in v1):** run `snapshot` once live and verify the envelope + that
   `expected_count: [300, 500]` holds. (Tracked in memory `museum-nl-open-items`.)
4. **Run `data-refresh` to build the data layer onto the `data` branch** (this also validates the
   pipeline against real source data). The Codespaces `GITHUB_TOKEN` lacks `actions: write`, so it
   cannot be dispatched from here — run it from the GitHub UI (Actions → Data Refresh → Run
   workflow), or run the live pipeline locally (`uv run python -m scripts.build_pipeline … --exclude ""`).
   Inspect per-category POI counts, `license.json`, and attribution. A `data` branch must exist
   before the first deploy.
5. **Verify required attribution renders on the real build:** "© OpenStreetMap
   contributors" + ODbL share-alike, CC-BY sources (from `license.json`), and "© Museumvereniging /
   museum.nl" (museum-nl ships in v1).
6. **GitHub Pages:** live at https://schellevis.github.io/kinderkaart/ (source = GitHub Actions).
   Because it's a project-pages subpath, the web build uses Vite `base: "./"` (relative asset paths).
7. **Deploy:** `deploy-pages.yml` auto-deploys on push to `main` (+ manual dispatch); ~2 min, web +
   `data` branch only. After a `data-refresh` (which updates the `data` branch, not `main`), dispatch
   a deploy to publish the new data.
