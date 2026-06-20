# Kinderkaart Plan 5 — Front-end Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A mobile-first static web app (MapLibre + Vite + TS) that loads the Plan 4 artifacts and
lets users browse, filter, search, favorite, and open detail for kid-friendly NL activities —
clustered client-side, with geolocation auto-center, deep-links, and a desktop overview panel.

**Architecture (spikes resolved → fully client-side):** Fetch `data/manifest.json` → `points.json`;
build a Supercluster index over the **filtered** point set and render clusters on a PDOK BRT-A
basemap; build a FlexSearch index in-browser from point names; lazy-fetch detail shards
(`fnv1a(poi_id) % shard_count`, matching Python). Pure-logic lives in small unit-tested TS modules
(`src/lib/*`); the app shell wires them to MapLibre and is verified end-to-end with Playwright,
including the deferred spike-2 cluster-correctness oracle and a perf measurement.

**Tech Stack:** Vite, TypeScript, maplibre-gl, supercluster, flexsearch; vitest (unit),
@playwright/test (e2e). Node 24 / npm available.

## Global Constraints

- `web/` is the app root; `npm` from there. Do NOT add a server — the app is 100% static.
- **`fnv1a` in TS MUST match `data_pipeline/hashing.py`** (same FNV-1a 32-bit) — shard lookup
  depends on it. The unit test uses the same canonical vectors.
- **"Unknown is not negative":** a `null` facet (indoor/free/age) must NOT be filtered out by a
  facet filter unless the user explicitly excludes unknowns. Default filters keep unknowns.
- **Cats bitmask** decoded via `manifest.categories` order (same as Plan 4 build).
- **Privacy:** geolocation stays client-side; nothing is sent to a server; no analytics.
- **Attribution** (PDOK + © OpenStreetMap contributors + CC-BY sources from `license.json`) is
  always visible on the map.
- **Accessibility:** keyboard-operable controls, visible focus, color-contrast AA, respects
  `prefers-reduced-motion`, touch targets ≥ 44px.
- Quality bar before each commit: `npm run lint && npm run typecheck && npm run test` (unit);
  Playwright e2e in the final task.

## Design direction (intentional, not templated)

- **Tone:** friendly and calm, not childish. Generous whitespace, rounded corners (8–14px),
  soft shadows. Map is the hero; chrome is light and gets out of the way.
- **Palette (tokens in `src/styles/tokens.css`):** neutral surface `#FBFAF7` / ink `#1F2421`;
  primary accent `#2F7D6B` (teal-green) for CTAs/active state. **Category colors** (markers,
  legend, chips) — fixed, AA-contrast, color-blind-distinct:
  `playground #F2994A` · `museum #6C5CE7` · `zoo #27AE60` · `petting_zoo #8D6E63` ·
  `pool #2D9CDB` · `play_park #EB5757` · `restaurant_kidfriendly #F2C94C`. Each marker also
  carries a category glyph (emoji or icon) so color is never the only signal.
- **Type:** system sans stack (`ui-rounded, "Segoe UI", system-ui, sans-serif`); headings slightly
  heavier, generous line-height. No external font fetch (reliability/CSP).
- **Layout:** mobile-first — full-bleed map; floating rounded search bar (top); horizontally
  scrollable category filter chips under it; a draggable **bottom-sheet** for results list + detail.
  **Desktop (≥ 960px):** persistent **left side panel** (search + filters + scrollable results list)
  beside the map; selecting a result flies the map and opens detail in the panel.

## File Structure

```
web/
├── package.json  vite.config.ts  tsconfig.json  .eslintrc / eslint.config.js
├── playwright.config.ts
├── index.html
├── public/                      # sample built data for dev/e2e (generated, gitignored except sample)
│   └── data/ …                  # a small sample site from the pipeline (committed for e2e)
├── src/
│   ├── main.ts                  # bootstrap: load manifest+points, build indexes, wire UI
│   ├── map.ts                   # MapLibre init (PDOK basemap), cluster source/layers, interactions
│   ├── cluster.ts               # Supercluster wrapper (load filtered pts, getClusters for bbox/zoom)
│   ├── state.ts                 # app state (filters, selection, ref point) + deep-link sync
│   ├── ui/                      # search box, filter chips, results list, detail panel, fav toggle, geo button
│   ├── styles/tokens.css  styles/app.css
│   └── lib/
│       ├── fnv1a.ts  shard.ts  points.ts  filter.ts  deeplink.ts  favorites.ts  search.ts
└── tests/
    ├── unit/ (vitest)           # one per lib module
    └── e2e/ (playwright)        # app.spec.ts (load, filter, search, detail, geo, fav, deeplink, responsive, perf, oracle)
```

---

### Task 1: Scaffold web app + tooling + sample data

**Files:** `web/package.json`, `vite.config.ts`, `tsconfig.json`, eslint config, `index.html`,
`src/main.ts` (stub), `src/styles/tokens.css`; sample data under `web/public/data/`.

- [ ] **Step 1: Scaffold + deps**

From `web/`:
```bash
npm init -y
npm install maplibre-gl supercluster flexsearch
npm install -D vite typescript @types/node vitest @playwright/test eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin jsdom
npx playwright install chromium
```
`package.json` scripts:
```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview --port 4173",
    "typecheck": "tsc --noEmit",
    "lint": "eslint src",
    "test": "vitest run",
    "e2e": "playwright test"
  }
}
```
`tsconfig.json`: `"strict": true`, `"target": "ES2022"`, `"module": "ESNext"`,
`"moduleResolution": "bundler"`, `"lib": ["ES2022","DOM","DOM.Iterable"]`, `"types": ["vitest/globals"]`.

- [ ] **Step 2: Generate sample data for dev/e2e**

Add `web/scripts/build-sample.sh` that runs the Python pipeline on the repo fixtures into
`web/public/` (so the app fetches `data/manifest.json` locally):
```bash
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
```
Run it; commit the generated `web/public/data/**` (small) so e2e is hermetic. Add a `.gitignore`
entry for `web/node_modules` and `web/dist`.

- [ ] **Step 3:** `src/styles/tokens.css` with the palette/category colors above; minimal
`index.html` mounting `#app` and `#map`; `src/main.ts` stub that logs the loaded manifest.

- [ ] **Step 4: Commit** `chore(web): scaffold Vite+TS app, tooling, sample data`

---

### Task 2: Pure-logic lib modules (vitest)

**Files:** `src/lib/{fnv1a,shard,points,filter,deeplink,favorites}.ts` + `tests/unit/*.test.ts`

- [ ] **Step 1: Write failing unit tests** (vitest) covering the behaviors below, then implement.

**`fnv1a.ts`** — `export function fnv1a(s: string): number` (32-bit, unsigned via `>>> 0`).
Test vectors (MUST match Python): `fnv1a("")===2166136261`, `fnv1a("a")===0xE40C292C`,
`fnv1a("foobar")===0xBF9CF968`.
```ts
export function fnv1a(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    // iterate UTF-8 bytes
  }
  return h >>> 0;
}
```
Implement by encoding to UTF-8 bytes (`new TextEncoder().encode(s)`) and folding:
`h ^= byte; h = Math.imul(h, 16777619)`, return `h >>> 0`.

**`shard.ts`** — `shardOf(poiId, shardCount) = fnv1a(poiId) % shardCount`;
`detailUrl(base, poiId, shardCount) = \`${base}/${shardOf(...)}.json\``. Test parity with a couple
of ids and a known shardCount.

**`points.ts`** — `decodePoints(payload)` → `Point[]` with `{poiId, lat, lon, cats: string[], name,
indoor, free, ageMin, ageMax}` decoding the `cats` bitmask via `payload.categories`. Test that a
mask round-trips to the right category names and unknown facets stay `null`.

**`filter.ts`** — `matches(point, filter, ref?)` where `filter = {categories:Set<string>|null,
indoor:bool|null, free:bool|null, ageForChild:number|null, maxDistanceM:number|null}`.
Rules (test each): no category filter → all; category filter → point must have ≥1 selected category;
`indoor`/`free` filter set to true → keep points with that value true **or null** is EXCLUDED only
when user toggles "known only" (default: a `true` filter keeps `true`; `null` kept unless an
explicit exclude). For MVP: `indoor===true` filter keeps `indoor===true`; **null is kept** (unknown
not treated as negative) — assert `matches({indoor:null}, {indoor:true})===true`. `ageForChild`
keeps points where `ageMin==null || ageMin<=age` and `ageMax==null || age<=ageMax`.
`maxDistanceM` uses haversine from `ref`.

**`deeplink.ts`** — `encode(state)→queryString`, `decode(queryString)→partial state` for
`{lat,lon,z,poi,q,cats}` (cats as comma list). Round-trip test; tolerant of missing params.

**`favorites.ts`** — `Favorites` over `localStorage` key `kinderkaart:favs`: `list():string[]`,
`has(id)`, `toggle(id)`, `add/remove`. Test with a jsdom localStorage that toggle persists and
dedupes. (vitest `environment: jsdom`.)

- [ ] **Step 2:** Implement each module to pass its test. **Step 3:** `npm run lint && npm run typecheck && npm run test` green. **Commit** `feat(web): add unit-tested lib modules (fnv1a, shard, points, filter, deeplink, favorites)`.

---

### Task 3: Search module (FlexSearch) + cluster wrapper (Supercluster)

**Files:** `src/lib/search.ts`, `src/cluster.ts` + `tests/unit/{search,cluster}.test.ts`

- [ ] **`search.ts`** — `buildIndex(points)` returns an object with `query(text, limit=20): string[]`
(poiIds), built with FlexSearch `Index({tokenize:"forward"})` adding `name` per point. Test that a
query returns the expected poiId(s) and respects the limit.
- [ ] **`cluster.ts`** — `makeClusterer(points)` wraps Supercluster (`radius:60,maxZoom:16`),
`update(filterFn)` rebuilds the index from the filtered subset, `getClusters(bbox, zoom)` returns
clusters/points. Test: with two far-apart points, z3 yields fewer features than z16; and the
**oracle** — the total `point_count` across clusters at any zoom equals the number of filtered
points (no points lost). **Commit** `feat(web): add search + cluster wrappers`.

---

### Task 4: Map + UI shell (MapLibre, filters, search, detail, favorites, geo, responsive)

**Files:** `src/map.ts`, `src/state.ts`, `src/ui/*`, `src/main.ts`, `src/styles/app.css`, `index.html`

This task is integration; it is verified by the Playwright suite in Task 5. Build incrementally
against `npm run dev` (data served from `public/data`). Requirements:

- [ ] **Basemap:** MapLibre with **PDOK BRT-A**. Verify and pin the current endpoint/style in this
  task (try the vector style JSON; if unavailable, use the WMTS raster tiles as a raster source).
  Document the exact URL in `src/map.ts`. Always render attribution control with "© OpenStreetMap
  contributors", PDOK, and CC-BY sources read from `license.json`.
- [ ] **Render:** maintain a Supercluster index over the filtered points; on `moveend`/`zoomend`,
  query `getClusters(bounds, zoom)` and render clusters (sized/colored; count label) and individual
  markers (category color + glyph) via a GeoJSON source + layers. Re-cluster on filter change.
- [ ] **Filters:** category chips (multi-select) + toggles (indoor, free) + child-age input +
  distance (needs a ref point). Filter changes update the cluster index and the results list.
  Unknown facets are not excluded by default.
- [ ] **Search:** the search box queries the FlexSearch index; results appear in the list; choosing
  one flies to it and opens detail.
- [ ] **Detail:** clicking a marker (or list item) lazily fetches `detail/<shard>.json` (via
  `shardOf` + `manifest.shard_count`), shows name, categories, address, opening hours, website,
  provenance/sources, last_updated, and a **favorite** toggle. **Missing fields are shown as
  "onbekend", never as a negative.**
- [ ] **Geolocation:** on load, request `navigator.geolocation`; on grant, fly to user + drop a
  "jij hier" marker and set the distance ref to the user; on deny/error/unavailable, fall back to a
  default NL view (`[5.3,52.15], z7`). A button re-requests location.
- [ ] **Favorites:** `localStorage`; a favorites filter/toggle shows only favorited POIs; persists
  across reloads; alias-safe (if a `poi_id` is now an alias, resolve via the detail/poi lookup — for
  MVP, a favorited id that no longer exists is shown as unavailable, not crashing).
- [ ] **Deep-links:** reflect `{lat,lon,z,poi,q,cats}` in the URL (`history.replaceState`) and
  restore them on load (open detail for `poi`, apply `cats`/`q`, set view).
- [ ] **Responsive:** mobile bottom-sheet vs desktop (≥960px) left side panel, per the design
  direction. Keyboard + focus + contrast + `prefers-reduced-motion`.
- [ ] **Commit** `feat(web): MapLibre map + filters/search/detail/favorites/geo/responsive shell`.

---

### Task 5: Playwright e2e — behavior, cluster-correctness oracle, perf

**Files:** `playwright.config.ts`, `tests/e2e/app.spec.ts`

`playwright.config.ts`: `webServer` builds + previews (`npm run build && npm run preview`, url
`http://localhost:4173`), `use: { baseURL }`. Run on chromium; add a mobile project
(`devices['Pixel 7']`) and a desktop project.

- [ ] Write these tests (each is an acceptance gate):
1. **Loads:** map canvas visible; attribution contains "OpenStreetMap"; ≥1 cluster/marker rendered.
2. **Filter changes counts (oracle):** read the app's exposed `window.__kinderkaart` debug handle
   (expose `{clusterer, filteredCount()}` in dev/e2e builds) — after selecting only "museum",
   assert `filteredCount()` equals the manifest `counts.museum`, and that the sum of rendered
   cluster `point_count`s + lone markers equals `filteredCount()` (no points lost/duplicated).
3. **Search:** type a known name → a result appears → click → detail panel shows that name.
4. **Detail lazy-load:** click a marker → a `data/**/detail/<n>.json` network request fires → panel
   shows fields; a missing field renders "onbekend".
5. **Geolocation fallback:** with geolocation denied (context permissions), app still loads at the
   NL fallback view; with a mocked position, the map centers near it.
6. **Favorites persist:** toggle favorite → reload → still favorited (localStorage).
7. **Deep-link round-trip:** open `/?cats=museum&poi=<id>` → detail for `<id>` open and only museums
   shown; the URL keeps `poi` after interaction.
8. **Responsive:** mobile project shows the bottom-sheet; desktop project shows the side panel.
9. **Perf (deferred spike-2 browser check):** with CPU throttling (CDP `Emulation.setCPUThrottlingRate` 4×)
   measure time from navigation to first clusters rendered; assert < 4000 ms on the sample data, and
   log the number for the real-data revisit. Record the measurement in the test output.

- [ ] **Run:** `npm run e2e` — all green. **Commit** `test(web): Playwright e2e incl. cluster oracle + perf`.

---

## Self-Review

**Spec coverage (Plan 5 = spec §10 + spike-2 deferred browser check):**
- Client point index + Supercluster over filtered set → Tasks 3,4; oracle → Task 5(2) ✓
- Client FlexSearch search → Tasks 3,4; e2e → Task 5(3) ✓
- Lazy sharded detail, fnv1a parity with Python → Tasks 2,4; e2e → Task 5(4) ✓
- Geolocation auto-center + fallback → Task 4; e2e → Task 5(5) ✓
- Favorites localStorage, alias-safe → Tasks 2,4; e2e → Task 5(6) ✓
- Deep-links (view+poi+query+filters) → Tasks 2,4; e2e → Task 5(7) ✓
- Mobile-first + desktop side panel, a11y → Task 4; e2e → Task 5(8) ✓
- "Unknown not negative" → Task 2 filter + Task 4 detail ✓
- PDOK basemap pinned + attribution + license.json → Task 4 ✓
- Real in-browser perf (deferred spike-2) → Task 5(9) ✓

**Placeholders:** the app shell (Task 4) is spec+acceptance-driven (frontend integration is verified
by running, not by transcription); the pure-logic modules (Tasks 2–3) have complete code/behavior
and unit tests. **Type/parity:** `fnv1a` TS matches `data_pipeline/hashing.py` vectors; `shardOf`
matches Plan 4 `shard_of`; cats decode matches `manifest.categories` order.

## Notes
- If the PDOK vector style endpoint proves unstable, ship the WMTS raster source as documented
  fallback (spec §10) — record the chosen URL in `src/map.ts`.
- Plan 6 (CI) builds `web/` and the real data, then deploys `web/dist` + `data/**` to GitHub Pages.
