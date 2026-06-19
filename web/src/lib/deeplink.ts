/**
 * Deep-link encoding/decoding for app state.
 * Params: lat, lon, z (zoom), poi (selected poi_id), q (search query), cats (comma-separated categories)
 */

export interface DeepLinkState {
  lat?: number;
  lon?: number;
  z?: number;
  poi?: string;
  q?: string;
  cats?: string[];
}

export function encode(state: DeepLinkState): string {
  const params = new URLSearchParams();
  if (state.lat != null) params.set("lat", String(state.lat));
  if (state.lon != null) params.set("lon", String(state.lon));
  if (state.z != null) params.set("z", String(state.z));
  if (state.poi) params.set("poi", state.poi);
  if (state.q) params.set("q", state.q);
  if (state.cats && state.cats.length > 0) params.set("cats", state.cats.join(","));
  return params.toString();
}

export function decode(queryString: string): DeepLinkState {
  const params = new URLSearchParams(queryString);
  const state: DeepLinkState = {};

  const lat = params.get("lat");
  if (lat != null) {
    const n = parseFloat(lat);
    if (!isNaN(n)) state.lat = n;
  }

  const lon = params.get("lon");
  if (lon != null) {
    const n = parseFloat(lon);
    if (!isNaN(n)) state.lon = n;
  }

  const z = params.get("z");
  if (z != null) {
    const n = parseFloat(z);
    if (!isNaN(n)) state.z = n;
  }

  const poi = params.get("poi");
  if (poi) state.poi = poi;

  const q = params.get("q");
  if (q) state.q = q;

  const cats = params.get("cats");
  if (cats) {
    const list = cats.split(",").map((s) => s.trim()).filter(Boolean);
    if (list.length > 0) state.cats = list;
  }

  return state;
}
