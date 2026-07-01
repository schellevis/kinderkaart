/**
 * Kinderkaart — main bootstrap.
 * Loads manifest + points, builds indexes, wires UI.
 */

import "./styles/app.css";
import "maplibre-gl/dist/maplibre-gl.css";

import { decodePoints } from "./lib/points.js";
import type { PointsPayload } from "./lib/points.js";
import { buildIndex } from "./lib/search.js";
import { makeClusterer } from "./cluster.js";
import { matches, haversineM } from "./lib/filter.js";
import { detailUrl } from "./lib/shard.js";
import { Favorites } from "./lib/favorites.js";
import { StateStore, parseUrlState } from "./state.js";
import { initMap, addClusterLayers, updateClusterData, LAYERS } from "./map.js";
import { createSearchBar, getSearchInput } from "./ui/search.js";
import { createFilterChips, createToggleBar } from "./ui/filters.js";
import { renderResults } from "./ui/results.js";
import { renderDetail } from "./ui/detail.js";
import type { DetailRecord } from "./ui/detail.js";
import type { Point } from "./lib/points.js";
import type maplibregl from "maplibre-gl";
import MapLibre from "maplibre-gl";
import { PIN_ICON, iconSpan } from "./lib/icons.js";

// ── Types ─────────────────────────────────────────────────

interface CountryManifest {
  data_version: string;
  shard_count: number;
  categories: string[];
  paths: {
    points: string;
    detail: string;
    license: string;
  };
  counts: Record<string, number>;
}

interface Manifest {
  [country: string]: CountryManifest;
}

// ── Bootstrap ─────────────────────────────────────────────

async function bootstrap(): Promise<void> {
  const loadingEl = document.getElementById("loading")!;

  try {
    // 1. Load manifest
    const manifestRes = await fetch("data/manifest.json");
    if (!manifestRes.ok) throw new Error(`manifest.json: ${manifestRes.status}`);
    const manifest: Manifest = await manifestRes.json();

    const country = Object.keys(manifest)[0] ?? "nl";
    const cm: CountryManifest = manifest[country];
    console.log("[kinderkaart] manifest loaded:", cm);

    // 2. Load points
    const pointsRes = await fetch(cm.paths.points);
    if (!pointsRes.ok) throw new Error(`points.json: ${pointsRes.status}`);
    const payload: PointsPayload = await pointsRes.json();
    const allPoints = decodePoints(payload);
    console.log(`[kinderkaart] ${allPoints.length} points decoded`);

    // Migrate persisted favorites that now resolve through an identity alias.
    const favorites = new Favorites();
    const currentIds = new Set(allPoints.map((point) => point.poiId));
    for (const oldId of favorites.list().filter((id) => !currentIds.has(id))) {
      try {
        const response = await fetch(detailUrl(cm.paths.detail, oldId, cm.shard_count));
        if (!response.ok) continue;
        const shard: Record<string, { redirect_to?: string }> = await response.json();
        const redirect = shard[oldId]?.redirect_to;
        if (redirect && currentIds.has(redirect)) favorites.replace(oldId, redirect);
      } catch {
        // Keep unavailable favorites: they may reappear in a later data version.
      }
    }

    // 3. Load license info
    let licenseText = "© Contribuanten";
    try {
      const licRes = await fetch(cm.paths.license);
      if (licRes.ok) {
        const lic = await licRes.json();
        if (lic && typeof lic === "object" && !Array.isArray(lic)) {
          // license.json is an object keyed by source_id
          const attributions = Array.from(
            new Set(
              Object.values(lic as Record<string, { attribution?: string | null }>)
                .map((s) => s.attribution ?? null)
                .filter((a): a is string => a !== null)
            )
          );
          if (attributions.length > 0) {
            licenseText = attributions.join(" · ");
          }
        }
      }
    } catch {
      // license is best-effort
    }

    // 4. Build search index
    const searchIdx = buildIndex(allPoints);

    // 5. Build clusterer
    const clusterer = makeClusterer(allPoints);

    // 6. Init state (with URL deep-link)
    const urlState = parseUrlState();
    const store = new StateStore(urlState);

    // 7. Init map
    const mapEl = document.getElementById("map")!;
    const map = initMap(mapEl, store.get(), licenseText);

    // 8. Wire up geolocation
    setupGeolocation(map, store);

    // 9. Wait for map to load before adding layers
    await new Promise<void>((resolve) => {
      if (map.loaded()) { resolve(); return; }
      map.once("load", () => resolve());
    });

    addClusterLayers(map);

    // 10. Build UI
    buildUI(map, allPoints, cm, clusterer, searchIdx, store);

    // 11. Initial render
    renderClusters(map, clusterer, store, allPoints);

    // 12. Expose debug handle for e2e tests
    (window as Window & typeof globalThis & {
      __kinderkaart?: {
        clusterer: typeof clusterer;
        filteredCount: () => number;
        manifest: Manifest;
      }
    }).__kinderkaart = {
      clusterer,
      filteredCount: () => clusterer.filteredCount(),
      manifest,
    };

    loadingEl.classList.add("hidden");
    console.log("[kinderkaart] ready");

  } catch (err) {
    console.error("[kinderkaart] failed to load:", err);
    loadingEl.textContent = "Kaart kon niet worden geladen. Vernieuw de pagina.";
  }
}

// ── Geolocation ───────────────────────────────────────────

function setupGeolocation(map: maplibregl.Map, store: StateStore): void {
  let userMarker: MapLibre.Marker | null = null;

  function onPosition(pos: GeolocationPosition): void {
    const { latitude, longitude } = pos.coords;
    store.update({
      userLocation: { lat: latitude, lon: longitude },
      viewLat: latitude,
      viewLon: longitude,
      viewZoom: 13,
    });
    map.flyTo({ center: [longitude, latitude], zoom: 13 });

    // Drop user marker
    if (userMarker) userMarker.remove();
    const el = document.createElement("div");
    el.className = "user-marker";
    el.setAttribute("aria-label", "Jouw locatie");
    userMarker = new MapLibre.Marker({ element: el })
      .setLngLat([longitude, latitude])
      .addTo(map);
  }

  function onError(): void {
    console.log("[kinderkaart] geolocation denied/unavailable, using default NL view");
  }

  // Request on load
  if ("geolocation" in navigator) {
    navigator.geolocation.getCurrentPosition(onPosition, onError, { timeout: 5000 });
  }

  // Geo button
  const geoBtn = document.getElementById("geo-btn");
  if (geoBtn) {
    geoBtn.addEventListener("click", () => {
      if ("geolocation" in navigator) {
        navigator.geolocation.getCurrentPosition(onPosition, onError, { timeout: 5000 });
      }
    });
  }
}

// ── Cluster render ────────────────────────────────────────

function renderClusters(
  map: maplibregl.Map,
  clusterer: ReturnType<typeof makeClusterer>,
  store: StateStore,
  _allPoints: Point[]
): void {
  const state = store.get();
  const favs = new Favorites();
  const center = map.getCenter();
  const reference = state.userLocation ?? { lat: center.lat, lon: center.lng };

  clusterer.update((pt) => {
    if (state.favoritesOnly && !favs.has(pt.poiId)) return false;
    return matches(pt, state.filter, reference);
  });

  updateClusterData(map, clusterer);
  updateResultCount(clusterer.filteredCount());
}

function updateResultCount(count: number): void {
  const countEl = document.getElementById("result-count");
  const sheetCount = document.getElementById("sheet-count");
  const text = `${count} ${count === 1 ? "resultaat" : "resultaten"}`;
  if (countEl) countEl.textContent = text;
  if (sheetCount) sheetCount.textContent = text;
}

/** Fix 6b: show sort basis below result count when not searching. */
function updateSortBasis(state: ReturnType<StateStore["get"]>): void {
  for (const id of ["sort-basis", "sheet-sort-basis"]) {
    const el = document.getElementById(id);
    if (!el) continue;
    if (state.searchQuery) {
      el.textContent = "";
    } else if (state.userLocation) {
      el.textContent = "Gesorteerd op afstand tot je locatie";
    } else {
      el.textContent = "Gesorteerd op afstand tot kaartmidden";
    }
  }
}

// ── UI wiring ─────────────────────────────────────────────

function buildUI(
  map: maplibregl.Map,
  allPoints: Point[],
  cm: CountryManifest,
  clusterer: ReturnType<typeof makeClusterer>,
  searchIdx: ReturnType<typeof buildIndex>,
  store: StateStore
): void {
  const favs = new Favorites();
  let currentDisplayPoints: Point[] = allPoints;

  // Chip/toggle container references (assigned after DOM injection below)
  let chips1: HTMLElement;
  let chips2: HTMLElement;
  let toggles1: HTMLElement;
  let toggles2: HTMLElement;
  let searchBar1: HTMLElement;
  let searchBar2: HTMLElement;

  // ── Fix 5: sync all controls to the current store state ──
  function syncControls(): void {
    const state = store.get();

    // Sync chips (both sets)
    for (const container of [chips1, chips2]) {
      if (!container) continue;
      for (const chip of container.querySelectorAll<HTMLElement>("[data-cat]")) {
        const cat = chip.dataset.cat ?? "";
        const active = state.filter.categories?.has(cat) ?? false;
        chip.classList.toggle("active", active);
        chip.setAttribute("aria-pressed", String(active));
      }
    }

    // Sync toggle buttons (both sets)
    for (const bar of [toggles1, toggles2]) {
      if (!bar) continue;
      for (const btn of bar.querySelectorAll<HTMLElement>("[data-toggle]")) {
        const key = btn.dataset.toggle as "indoor" | "free";
        const active = state.filter[key] === true;
        btn.classList.toggle("active", active);
        btn.setAttribute("aria-pressed", String(active));
      }
      // Age input
      const ageInput = bar.querySelector<HTMLInputElement>("[data-filter-input='age']");
      if (ageInput) {
        ageInput.value = state.filter.ageForChild == null ? "" : String(state.filter.ageForChild);
      }
      // Distance select
      const distanceSelect = bar.querySelector<HTMLSelectElement>("[data-filter-input='distance']");
      if (distanceSelect) {
        distanceSelect.value = state.filter.maxDistanceM == null ? "" : String(state.filter.maxDistanceM);
      }
    }

    // Sync search inputs
    for (const bar of [searchBar1, searchBar2]) {
      if (!bar) continue;
      const input = getSearchInput(bar);
      if (input && input !== document.activeElement) {
        input.value = state.searchQuery;
      }
    }

    // Sync clear-filter button visibility
    const hasActiveFilters = isFilterActive(state);
    for (const id of ["clear-filters-btn", "sheet-clear-filters-btn"]) {
      const btn = document.getElementById(id);
      if (btn) btn.style.display = hasActiveFilters ? "" : "none";
    }

    // Fix 6c: show distance-filter hint when filter is active but no user location
    const showDistHint = state.filter.maxDistanceM !== null && state.userLocation === null;
    for (const id of ["dist-hint", "sheet-dist-hint"]) {
      const el = document.getElementById(id);
      if (el) el.style.display = showDistHint ? "" : "none";
    }
  }

  /** Returns true when any filter or search query is active. */
  function isFilterActive(state: ReturnType<StateStore["get"]>): boolean {
    return (
      (state.filter.categories !== null && state.filter.categories.size > 0) ||
      state.filter.indoor !== null ||
      state.filter.free !== null ||
      state.filter.ageForChild !== null ||
      state.filter.maxDistanceM !== null ||
      state.searchQuery !== "" ||
      state.favoritesOnly
    );
  }

  // ── Helper: apply filters + render everything ──
  function applyAndRender(): void {
    const state = store.get();
    const center = map.getCenter();
    const reference = state.userLocation ?? { lat: center.lat, lon: center.lng };

    // Compute filtered points for the list
    let listPoints: Point[];

    if (state.searchQuery) {
      const ids = new Set(searchIdx.query(state.searchQuery, 200));
      listPoints = allPoints.filter((pt) => {
        if (state.favoritesOnly && !favs.has(pt.poiId)) return false;
        if (!ids.has(pt.poiId)) return false;
        return matches(pt, state.filter, reference);
      });
    } else if (state.favoritesOnly) {
      listPoints = allPoints.filter(
        (pt) => favs.has(pt.poiId) && matches(pt, state.filter, reference)
      );
    } else {
      listPoints = allPoints.filter((pt) =>
        matches(pt, state.filter, reference)
      );
    }

    // Browse (non-search) lists can be the full ~40k set; sort by distance to the reference so
    // the capped list shows the nearest results first. Search keeps its relevance order (≤200).
    if (!state.searchQuery) {
      listPoints = listPoints
        .map((pt) => ({ pt, d: haversineM(reference, { lat: pt.lat, lon: pt.lon }) }))
        .sort((a, b) => a.d - b.d)
        .map((x) => x.pt);
    }

    currentDisplayPoints = listPoints;

    // Update clusterer with full filter (map shows all matching points)
    clusterer.update((pt) => {
      if (state.favoritesOnly && !favs.has(pt.poiId)) return false;
      return matches(pt, state.filter, reference);
    });

    updateClusterData(map, clusterer);

    // Fix 2: count reflects search results when a query is active
    if (state.searchQuery) {
      updateResultCount(listPoints.length);
    } else {
      updateResultCount(clusterer.filteredCount());
    }

    // Fix 6b: sort-basis line below result count
    updateSortBasis(state);

    // Fix 5: sync all controls to match store state
    syncControls();

    // Re-render results list
    const desktopList = document.getElementById("results-list");
    const mobileList = document.getElementById("mobile-results");
    const renderOpts = {
      points: listPoints,
      selectedId: state.selectedPoiId,
      onSelect: (id: string) => selectPoi(id),
    };
    if (desktopList) renderResults(desktopList, renderOpts);
    if (mobileList) renderResults(mobileList, renderOpts);
  }

  // ── Helper: open detail for a POI ──
  async function selectPoi(poiId: string): Promise<void> {
    store.update({ selectedPoiId: poiId });

    // Fly to POI location
    let pt = allPoints.find((p) => p.poiId === poiId);
    if (pt) {
      map.flyTo({ center: [pt.lon, pt.lat], zoom: Math.max(map.getZoom(), 14) });
    }

    // Lazily fetch detail shard
    let record: DetailRecord | null = null;

    try {
      for (let redirects = 0; redirects < 5; redirects++) {
        const shardUrl = detailUrl(cm.paths.detail, poiId, cm.shard_count);
        const res = await fetch(shardUrl);
        if (!res.ok) break;
        const shard: Record<string, DetailRecord | { redirect_to: string }> = await res.json();
        const found = shard[poiId];
        if (found && "redirect_to" in found) {
          const oldId = poiId;
          poiId = found.redirect_to;
          favs.replace(oldId, poiId);
          store.update({ selectedPoiId: poiId });
          pt = allPoints.find((p) => p.poiId === poiId);
          if (pt) {
            map.flyTo({ center: [pt.lon, pt.lat], zoom: Math.max(map.getZoom(), 14) });
          }
          continue;
        }
        record = found ?? null;
        break;
      }
    } catch (err) {
      console.warn("[kinderkaart] detail fetch failed:", err);
    }

    if (!record) {
      // Fallback: construct minimal record from points data
      if (pt) {
        record = {
          name: pt.name,
          lat: pt.lat,
          lon: pt.lon,
          categories: pt.cats,
          address: null,
          opening_hours: null,
          website: null,
          sources: [],
          last_updated: null,
        };
      } else {
        return;
      }
    }

    // Show detail
    const closeDetail = () => {
      store.update({ selectedPoiId: null });
      const dp = document.getElementById("detail-panel");
      if (dp) dp.classList.remove("visible");
      const md = document.getElementById("mobile-detail");
      if (md) {
        while (md.firstChild) md.removeChild(md.firstChild);
      }
      // Expand bottom sheet back to results
      const bottomSheet = document.getElementById("bottom-sheet");
      if (bottomSheet) bottomSheet.classList.add("collapsed");
      applyAndRender();
    };

    const detailOpts = {
      poiId,
      record,
      onClose: closeDetail,
      onFavToggle: () => applyAndRender(),
    };

    const dp = document.getElementById("detail-panel");
    if (dp) {
      renderDetail(dp, detailOpts);
      dp.classList.add("visible");
    }

    const md = document.getElementById("mobile-detail");
    if (md) {
      renderDetail(md, detailOpts);
      // Expand bottom sheet
      const bottomSheet = document.getElementById("bottom-sheet");
      if (bottomSheet) bottomSheet.classList.remove("collapsed");
    }

    applyAndRender();
  }

  // ── Fix 4: clear filters helper ──
  function clearAllFilters(): void {
    store.update({
      filter: {
        categories: null,
        indoor: null,
        free: null,
        ageForChild: null,
        maxDistanceM: null,
      },
      searchQuery: "",
      favoritesOnly: false,
    });
    applyAndRender();
  }

  // ── Build search bars ──
  // Shared handler: update state, re-render, then fit the map to the matches
  // and reveal the mobile results sheet (a collapsed sheet hides them entirely).
  function handleSearchInput(q: string): void {
    store.update({ searchQuery: q });
    applyAndRender();
    if (q && currentDisplayPoints.length > 0) {
      const sample = currentDisplayPoints.slice(0, 50);
      const lons = sample.map((p) => p.lon);
      const lats = sample.map((p) => p.lat);
      const bounds: [number, number, number, number] = [
        Math.min(...lons), Math.min(...lats),
        Math.max(...lons), Math.max(...lats),
      ];
      map.fitBounds(bounds, { padding: 60, maxZoom: 13, duration: 600 });
      // Reveal results on mobile; harmless on desktop (sheet is display:none ≥960px).
      document.getElementById("bottom-sheet")?.classList.remove("collapsed");
    }
  }

  searchBar1 = createSearchBar({
    placeholder: "Zoek activiteiten…",
    initialValue: store.get().searchQuery,
    onInput: handleSearchInput,
  });
  searchBar2 = createSearchBar({
    placeholder: "Zoek activiteiten…",
    initialValue: store.get().searchQuery,
    onInput: handleSearchInput,
  });

  const panelSearch = document.getElementById("panel-search-wrapper");
  if (panelSearch) panelSearch.appendChild(searchBar1);

  const mobileSearch = document.getElementById("mobile-search-wrapper");
  if (mobileSearch) mobileSearch.appendChild(searchBar2);

  // ── Build filter chips ──
  const filterState = store.get().filter;
  const filterOpts = {
    categories: cm.categories,
    filter: filterState,
    onFilterChange: (f: typeof filterState) => {
      store.update({ filter: f });
      applyAndRender();
    },
  };

  chips1 = createFilterChips(filterOpts);
  toggles1 = createToggleBar(filterOpts);
  chips2 = createFilterChips(filterOpts);
  toggles2 = createToggleBar(filterOpts);

  // ── Fix 6c: distance-filter hint ──
  const distHint = document.createElement("p");
  distHint.id = "dist-hint";
  distHint.className = "filter-hint";
  distHint.appendChild(iconSpan(PIN_ICON));
  distHint.appendChild(document.createTextNode(" Zet je locatie aan voor afstand vanaf jou."));
  distHint.style.display = "none";

  const sheetDistHint = document.createElement("p");
  sheetDistHint.id = "sheet-dist-hint";
  sheetDistHint.className = "filter-hint";
  sheetDistHint.appendChild(iconSpan(PIN_ICON));
  sheetDistHint.appendChild(document.createTextNode(" Zet je locatie aan voor afstand vanaf jou."));
  sheetDistHint.style.display = "none";

  const panelFilters = document.getElementById("panel-filters");
  if (panelFilters) {
    panelFilters.appendChild(chips1);
    panelFilters.appendChild(toggles1);
    panelFilters.appendChild(distHint);
  }

  const mobileFilters = document.getElementById("mobile-filters");
  if (mobileFilters) {
    mobileFilters.appendChild(chips2);
    mobileFilters.appendChild(toggles2);
    mobileFilters.appendChild(sheetDistHint);
  }

  // ── Fix 4: "Wis filters" button — desktop panel ──
  const clearBtn = document.createElement("button");
  clearBtn.id = "clear-filters-btn";
  clearBtn.type = "button";
  clearBtn.className = "clear-filters-btn";
  clearBtn.textContent = "Wis filters";
  clearBtn.style.display = "none";
  clearBtn.addEventListener("click", clearAllFilters);

  // Fix 4: sheet header clear button
  const sheetClearBtn = document.createElement("button");
  sheetClearBtn.id = "sheet-clear-filters-btn";
  sheetClearBtn.type = "button";
  sheetClearBtn.className = "clear-filters-btn";
  sheetClearBtn.textContent = "Wis filters";
  sheetClearBtn.style.display = "none";
  sheetClearBtn.addEventListener("click", clearAllFilters);

  // Fix 6b: sort-basis elements
  const sortBasisEl = document.createElement("p");
  sortBasisEl.id = "sort-basis";
  sortBasisEl.className = "sort-basis-hint";

  const sheetSortBasisEl = document.createElement("p");
  sheetSortBasisEl.id = "sheet-sort-basis";
  sheetSortBasisEl.className = "sort-basis-hint";

  // Insert clear button + sort basis near result count in side panel
  const resultCountEl = document.getElementById("result-count");
  if (resultCountEl?.parentNode) {
    resultCountEl.parentNode.insertBefore(clearBtn, resultCountEl.nextSibling);
    resultCountEl.parentNode.insertBefore(sortBasisEl, clearBtn.nextSibling);
  }

  // Insert in sheet header
  const sheetHeader = document.querySelector(".sheet-header");
  if (sheetHeader) {
    sheetHeader.appendChild(sheetClearBtn);
    sheetHeader.appendChild(sheetSortBasisEl);
  }

  // ── Map move → re-cluster ──
  const onMapMove = () => {
    const center = map.getCenter();
    store.update({ viewLat: center.lat, viewLon: center.lng, viewZoom: map.getZoom() });
    if (store.get().filter.maxDistanceM !== null && store.get().userLocation === null) {
      applyAndRender();
    } else {
      updateClusterData(map, clusterer);
    }
  };
  map.on("moveend", onMapMove);
  map.on("zoomend", onMapMove);

  // ── Map click → open detail ──
  map.on("click", LAYERS.POINTS_LAYER, (e) => {
    const f = e.features?.[0];
    if (!f?.properties) return;
    const poiId = f.properties["poiId"] as string | undefined;
    if (poiId) selectPoi(poiId);
  });

  // Change cursor on hover over markers
  map.on("mouseenter", LAYERS.POINTS_LAYER, () => {
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", LAYERS.POINTS_LAYER, () => {
    map.getCanvas().style.cursor = "";
  });

  // ── Fix 8: Bottom sheet drag with Pointer Events ──
  const sheet = document.getElementById("bottom-sheet");
  if (sheet) {
    let startY = 0;
    let startTransform = 0;
    let dragging = false;
    const handle = sheet.querySelector(".sheet-handle") as HTMLElement | null;

    const onPointerStart = (e: PointerEvent) => {
      handle?.setPointerCapture(e.pointerId);
      dragging = true;
      startY = e.clientY;
      const t = new DOMMatrix(getComputedStyle(sheet).transform);
      startTransform = t.m42 ?? 0;
    };
    const onPointerMove = (e: PointerEvent) => {
      if (!dragging) return;
      const dy = e.clientY - startY;
      const next = Math.max(0, startTransform + dy);
      sheet.style.transform = `translateY(${next}px)`;
    };
    const onPointerEnd = (e: PointerEvent) => {
      if (!dragging) return;
      dragging = false;
      const dy = e.clientY - startY;
      sheet.style.transform = "";
      if (dy > 80) sheet.classList.add("collapsed");
      else sheet.classList.remove("collapsed");
    };

    handle?.addEventListener("pointerdown", onPointerStart);
    handle?.addEventListener("pointermove", onPointerMove);
    handle?.addEventListener("pointerup", onPointerEnd);
    handle?.addEventListener("pointercancel", onPointerEnd);

    // Also keyboard: Enter/Space on handle
    handle?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        sheet.classList.toggle("collapsed");
      }
    });

    // Show sheet initially collapsed on mobile
    sheet.classList.add("collapsed");
  }

  // ── Handle URL deep-link for poi ──
  const urlPoi = store.get().selectedPoiId;
  if (urlPoi) {
    // Wait for the map to finish its initial tile-load before flying to the POI
    map.once("idle", () => selectPoi(urlPoi));
  }

  // ── Initial render ──
  applyAndRender();

  // Suppress unused variable warning
  void currentDisplayPoints;
}

bootstrap();
