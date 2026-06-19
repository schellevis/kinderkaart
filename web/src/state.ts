import { decode, encode } from "./lib/deeplink.js";
import type { Filter } from "./lib/filter.js";
import type { LatLon } from "./lib/filter.js";

export interface AppState {
  filter: Filter;
  selectedPoiId: string | null;
  searchQuery: string;
  userLocation: LatLon | null;
  viewLat: number;
  viewLon: number;
  viewZoom: number;
  favoritesOnly: boolean;
}

const DEFAULT_STATE: AppState = {
  filter: {
    categories: null,
    indoor: null,
    free: null,
    ageForChild: null,
    maxDistanceM: null,
  },
  selectedPoiId: null,
  searchQuery: "",
  userLocation: null,
  viewLat: 52.15,
  viewLon: 5.3,
  viewZoom: 7,
  favoritesOnly: false,
};

export type StateListener = (state: AppState, prev: AppState) => void;

export class StateStore {
  private state: AppState;
  private listeners: StateListener[] = [];

  constructor(initial?: Partial<AppState>) {
    this.state = { ...DEFAULT_STATE, ...initial };
  }

  get(): AppState {
    return this.state;
  }

  update(patch: Partial<AppState>): void {
    const prev = this.state;
    this.state = { ...this.state, ...patch };
    for (const fn of this.listeners) {
      fn(this.state, prev);
    }
    this.syncUrl();
  }

  subscribe(fn: StateListener): () => void {
    this.listeners.push(fn);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== fn);
    };
  }

  private syncUrl(): void {
    const s = this.state;
    const cats = s.filter.categories ? Array.from(s.filter.categories) : [];
    const qs = encode({
      lat: Math.round(s.viewLat * 10000) / 10000,
      lon: Math.round(s.viewLon * 10000) / 10000,
      z: Math.round(s.viewZoom * 10) / 10,
      poi: s.selectedPoiId ?? undefined,
      q: s.searchQuery || undefined,
      cats: cats.length > 0 ? cats : undefined,
    });
    const url = qs ? `?${qs}` : window.location.pathname;
    history.replaceState(null, "", url);
  }
}

/** Parse initial state from the URL query string. */
export function parseUrlState(): Partial<AppState> {
  const dl = decode(window.location.search.slice(1));
  const partial: Partial<AppState> = {};

  if (dl.lat != null && dl.lon != null) {
    partial.viewLat = dl.lat;
    partial.viewLon = dl.lon;
  }
  if (dl.z != null) partial.viewZoom = dl.z;
  if (dl.poi) partial.selectedPoiId = dl.poi;
  if (dl.q) partial.searchQuery = dl.q;
  if (dl.cats && dl.cats.length > 0) {
    partial.filter = {
      ...DEFAULT_STATE.filter,
      categories: new Set(dl.cats),
    };
  }

  return partial;
}
