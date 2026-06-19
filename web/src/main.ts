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
import { matches } from "./lib/filter.js";
import { detailUrl } from "./lib/shard.js";
import { Favorites } from "./lib/favorites.js";
import { StateStore, parseUrlState } from "./state.js";
import { initMap, addClusterLayers, updateClusterData, LAYERS } from "./map.js";
import { createSearchBar } from "./ui/search.js";
import { createFilterChips, createToggleBar } from "./ui/filters.js";
import { renderResults } from "./ui/results.js";
import { renderDetail } from "./ui/detail.js";
import type { DetailRecord } from "./ui/detail.js";
import type { Point } from "./lib/points.js";
import type maplibregl from "maplibre-gl";
import MapLibre from "maplibre-gl";

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

    // 3. Load license info
    let licenseText = "© Contribuanten";
    try {
      const licRes = await fetch(cm.paths.license);
      if (licRes.ok) {
        const lic = await licRes.json();
        if (Array.isArray(lic)) {
          licenseText = lic
            .map((s: { name?: string; license?: string }) =>
              s.name ? `${s.name} (${s.license ?? "CC-BY"})` : ""
            )
            .filter(Boolean)
            .join(", ");
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

  clusterer.update((pt) => {
    if (state.favoritesOnly && !favs.has(pt.poiId)) return false;
    return matches(pt, state.filter, state.userLocation ?? undefined);
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

  // ── Helper: apply filters + render everything ──
  function applyAndRender(): void {
    const state = store.get();

    // Compute filtered points for the list
    let listPoints: Point[];

    if (state.searchQuery) {
      const ids = new Set(searchIdx.query(state.searchQuery, 200));
      listPoints = allPoints.filter((pt) => {
        if (state.favoritesOnly && !favs.has(pt.poiId)) return false;
        if (!ids.has(pt.poiId)) return false;
        return matches(pt, state.filter, state.userLocation ?? undefined);
      });
    } else if (state.favoritesOnly) {
      listPoints = allPoints.filter(
        (pt) => favs.has(pt.poiId) && matches(pt, state.filter, state.userLocation ?? undefined)
      );
    } else {
      listPoints = allPoints.filter((pt) =>
        matches(pt, state.filter, state.userLocation ?? undefined)
      );
    }

    currentDisplayPoints = listPoints;

    // Update clusterer with full filter (map shows all matching points)
    clusterer.update((pt) => {
      if (state.favoritesOnly && !favs.has(pt.poiId)) return false;
      return matches(pt, state.filter, state.userLocation ?? undefined);
    });

    updateClusterData(map, clusterer);
    updateResultCount(clusterer.filteredCount());

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
    const pt = allPoints.find((p) => p.poiId === poiId);
    if (pt) {
      map.flyTo({ center: [pt.lon, pt.lat], zoom: Math.max(map.getZoom(), 14) });
    }

    // Lazily fetch detail shard
    const shardUrl = detailUrl(cm.paths.detail, poiId, cm.shard_count);
    let record: DetailRecord | null = null;

    try {
      const res = await fetch(shardUrl);
      if (res.ok) {
        const shard: Record<string, DetailRecord> = await res.json();
        record = shard[poiId] ?? null;
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
      const sheet = document.getElementById("bottom-sheet");
      if (sheet) sheet.classList.add("collapsed");
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
      const sheet = document.getElementById("bottom-sheet");
      if (sheet) sheet.classList.remove("collapsed");
    }

    applyAndRender();
  }

  // ── Build search bars ──
  const searchBar1 = createSearchBar({
    placeholder: "Zoek activiteiten…",
    initialValue: store.get().searchQuery,
    onInput: (q) => {
      store.update({ searchQuery: q });
      applyAndRender();
    },
  });
  const searchBar2 = createSearchBar({
    placeholder: "Zoek activiteiten…",
    initialValue: store.get().searchQuery,
    onInput: (q) => {
      store.update({ searchQuery: q });
      applyAndRender();
    },
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

  const chips1 = createFilterChips(filterOpts);
  const toggles1 = createToggleBar(filterOpts);
  const chips2 = createFilterChips(filterOpts);
  const toggles2 = createToggleBar(filterOpts);

  const panelFilters = document.getElementById("panel-filters");
  if (panelFilters) {
    panelFilters.appendChild(chips1);
    panelFilters.appendChild(toggles1);
  }

  const mobileFilters = document.getElementById("mobile-filters");
  if (mobileFilters) {
    mobileFilters.appendChild(chips2);
    mobileFilters.appendChild(toggles2);
  }

  // ── Map move → re-cluster ──
  const onMapMove = () => updateClusterData(map, clusterer);
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

  // ── Bottom sheet drag ──
  const sheet = document.getElementById("bottom-sheet");
  if (sheet) {
    let startY = 0;
    let startTransform = 0;
    const handle = sheet.querySelector(".sheet-handle") as HTMLElement | null;

    const onStart = (y: number) => {
      startY = y;
      const t = new DOMMatrix(getComputedStyle(sheet).transform);
      startTransform = t.m42 ?? 0;
    };
    const onMove = (y: number) => {
      const dy = y - startY;
      const next = Math.max(0, startTransform + dy);
      sheet.style.transform = `translateY(${next}px)`;
    };
    const onEnd = (y: number) => {
      const dy = y - startY;
      sheet.style.transform = "";
      if (dy > 80) sheet.classList.add("collapsed");
      else sheet.classList.remove("collapsed");
    };

    handle?.addEventListener("touchstart", (e) => onStart(e.touches[0].clientY), { passive: true });
    handle?.addEventListener("touchmove", (e) => onMove(e.touches[0].clientY), { passive: true });
    handle?.addEventListener("touchend", (e) => onEnd(e.changedTouches[0].clientY), { passive: true });

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
  const urlPoi = parseUrlState().selectedPoiId;
  if (urlPoi) {
    // Open detail after a short delay (map needs to settle)
    setTimeout(() => selectPoi(urlPoi), 500);
  }

  // ── Initial render ──
  applyAndRender();

  // Suppress unused variable warning
  void currentDisplayPoints;
}

bootstrap();
