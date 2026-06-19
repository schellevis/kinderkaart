import type { Point } from "./points.js";

/**
 * Filter criteria for POI matching.
 *
 * "Unknown is not negative": a null facet (indoor/free/age) must NOT be filtered
 * out by a facet filter unless the user explicitly excludes unknowns.
 * Default filter behaviour:
 *   - indoor: true  → keeps true AND null (unknown kept)
 *   - indoor: false → keeps false AND null
 *   - indoor: null  → no filter on this facet (keep all)
 */
export interface Filter {
  categories: Set<string> | null; // null = no category filter
  indoor: boolean | null;         // null = no filter
  free: boolean | null;           // null = no filter
  ageForChild: number | null;     // null = no age filter
  maxDistanceM: number | null;    // null = no distance filter; needs ref
}

export interface LatLon {
  lat: number;
  lon: number;
}

/** Haversine distance in metres */
export function haversineM(a: LatLon, b: LatLon): number {
  const R = 6371000;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLon = ((b.lon - a.lon) * Math.PI) / 180;
  const sinDLat = Math.sin(dLat / 2);
  const sinDLon = Math.sin(dLon / 2);
  const h =
    sinDLat * sinDLat +
    Math.cos((a.lat * Math.PI) / 180) *
      Math.cos((b.lat * Math.PI) / 180) *
      sinDLon *
      sinDLon;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/**
 * Returns true if the point matches the given filter.
 * ref is required only when filter.maxDistanceM is set.
 */
export function matches(point: Point, filter: Filter, ref?: LatLon): boolean {
  // Category filter: point must share ≥1 category with the selected set
  if (filter.categories !== null && filter.categories.size > 0) {
    if (!point.cats.some((c) => filter.categories!.has(c))) {
      return false;
    }
  }

  // Facet: indoor
  // true filter → keep true AND null; false filter → keep false AND null
  if (filter.indoor !== null) {
    if (point.indoor !== null && point.indoor !== filter.indoor) {
      return false;
    }
  }

  // Facet: free
  if (filter.free !== null) {
    if (point.free !== null && point.free !== filter.free) {
      return false;
    }
  }

  // Age filter
  if (filter.ageForChild !== null) {
    const age = filter.ageForChild;
    if (point.ageMin !== null && age < point.ageMin) return false;
    if (point.ageMax !== null && age > point.ageMax) return false;
  }

  // Distance filter
  if (filter.maxDistanceM !== null && ref != null) {
    const dist = haversineM(ref, { lat: point.lat, lon: point.lon });
    if (dist > filter.maxDistanceM) return false;
  }

  return true;
}
