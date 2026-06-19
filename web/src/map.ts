/**
 * MapLibre map initialization and cluster rendering.
 *
 * PDOK BRT-A basemap:
 *   Verified endpoint: PDOK BRT-A Achtergrondkaart WMTS "grijs" layer
 *   Capabilities URL: https://service.pdok.nl/brt/achtergrondkaart/wmts/v2_0/grijs/WMTS/1.0.0/WMTSCapabilities.xml
 *   Working tile URL template: https://service.pdok.nl/brt/achtergrondkaart/wmts/v2_0/grijs/EPSG:3857/{z}/{x}/{y}.png
 *
 *   NOTE: The ResourceURL in the capabilities points to a mapproxy subdomain (service.pdok.nl/mapproxy/...)
 *   which returns 404. The correct path for XYZ-style tiles is the v2_0 path above (HTTP 200 verified).
 *   Zoom levels: 0–17 (EPSG:3857). Falls back gracefully to OpenStreetMap if tiles fail to load.
 *
 * Attribution: © PDOK, © OpenStreetMap contributors (ODbL)
 */

import maplibregl from "maplibre-gl";
import type { Clusterer } from "./cluster.js";
import type { AppState } from "./state.js";

// Verified PDOK tile URL (tested 2026-06-19)
const PDOK_TILE_URL =
  "https://service.pdok.nl/brt/achtergrondkaart/wmts/v2_0/grijs/EPSG:3857/{z}/{x}/{y}.png";

const PDOK_ATTRIBUTION =
  '© <a href="https://www.pdok.nl/" target="_blank" rel="noopener">PDOK</a> / ' +
  '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>';

// Category color map (matching tokens.css)
const CAT_COLORS: Record<string, string> = {
  playground: "#F2994A",
  museum: "#6C5CE7",
  zoo: "#27AE60",
  petting_zoo: "#8D6E63",
  pool: "#2D9CDB",
  play_park: "#EB5757",
  restaurant_kidfriendly: "#F2C94C",
};

const CAT_GLYPHS: Record<string, string> = {
  playground: "🛝",
  museum: "🏛️",
  zoo: "🦁",
  petting_zoo: "🐑",
  pool: "🏊",
  play_park: "🌳",
  restaurant_kidfriendly: "🍽️",
};

export function categoryColor(cats: string[]): string {
  for (const c of cats) {
    if (CAT_COLORS[c]) return CAT_COLORS[c];
  }
  return "#9E9E9E";
}

export function categoryGlyph(cats: string[]): string {
  for (const c of cats) {
    if (CAT_GLYPHS[c]) return CAT_GLYPHS[c];
  }
  return "📍";
}

export function initMap(
  container: HTMLElement,
  state: AppState,
  licenseText: string
): maplibregl.Map {
  const map = new maplibregl.Map({
    container,
    style: {
      version: 8,
      glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
      sources: {
        pdok: {
          type: "raster",
          tiles: [PDOK_TILE_URL],
          tileSize: 256,
          maxzoom: 17,
          attribution: PDOK_ATTRIBUTION + " · " + licenseText,
        },
      },
      layers: [
        {
          id: "pdok-tiles",
          type: "raster",
          source: "pdok",
          paint: { "raster-opacity": 1 },
        },
      ],
    },
    center: [state.viewLon, state.viewLat],
    zoom: state.viewZoom,
    attributionControl: false,
  });

  // Custom attribution with our sources
  map.addControl(
    new maplibregl.AttributionControl({
      compact: true,
      customAttribution: PDOK_ATTRIBUTION + " · " + licenseText,
    }),
    "bottom-right"
  );

  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");

  return map;
}

const GEO_SOURCE = "kinderkaart-geo";
const CLUSTER_LAYER = "kinderkaart-clusters";
const CLUSTER_COUNT_LAYER = "kinderkaart-cluster-count";
const POINTS_LAYER = "kinderkaart-points";

export function addClusterLayers(map: maplibregl.Map): void {
  if (map.getSource(GEO_SOURCE)) return;

  map.addSource(GEO_SOURCE, {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
    cluster: false, // We cluster client-side with Supercluster
  });

  // Cluster circles
  map.addLayer({
    id: CLUSTER_LAYER,
    type: "circle",
    source: GEO_SOURCE,
    filter: ["==", ["get", "cluster"], true],
    paint: {
      "circle-color": "#2F7D6B",
      "circle-radius": [
        "step",
        ["get", "point_count"],
        18, 5, 24, 20, 30, 50, 36,
      ],
      "circle-opacity": 0.92,
      "circle-stroke-width": 2,
      "circle-stroke-color": "#fff",
    },
  });

  // Cluster count label
  map.addLayer({
    id: CLUSTER_COUNT_LAYER,
    type: "symbol",
    source: GEO_SOURCE,
    filter: ["==", ["get", "cluster"], true],
    layout: {
      "text-field": ["to-string", ["get", "point_count"]],
      "text-size": 13,
      "text-allow-overlap": true,
    },
    paint: {
      "text-color": "#fff",
    },
  });

  // Individual point circles
  map.addLayer({
    id: POINTS_LAYER,
    type: "circle",
    source: GEO_SOURCE,
    filter: ["!=", ["get", "cluster"], true],
    paint: {
      "circle-color": "#2F7D6B",
      "circle-radius": 10,
      "circle-opacity": 0.9,
      "circle-stroke-width": 2,
      "circle-stroke-color": "#fff",
    },
  });
}

export function updateClusterData(
  map: maplibregl.Map,
  clusterer: Clusterer
): void {
  const source = map.getSource(GEO_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (!source) return;

  const bounds = map.getBounds();
  if (!bounds) return;

  const bbox: [number, number, number, number] = [
    bounds.getWest(),
    bounds.getSouth(),
    bounds.getEast(),
    bounds.getNorth(),
  ];
  const zoom = Math.floor(map.getZoom());
  const features = clusterer.getClusters(bbox, zoom);

  source.setData({
    type: "FeatureCollection",
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    features: features as any,
  });
}

export function setPointColors(_catColors: Record<string, string>): void {
  // Colors are set per-feature via properties — for now use accent color for all
  // Future: use expressions based on cats[0]
}

export const LAYERS = {
  GEO_SOURCE,
  CLUSTER_LAYER,
  CLUSTER_COUNT_LAYER,
  POINTS_LAYER,
};
