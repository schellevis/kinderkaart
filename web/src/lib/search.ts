import type { Point } from "./points.js";

/**
 * Simple forward-tokenizing search index over point names.
 * Uses a manual prefix map for broad compatibility, matching
 * the FlexSearch "forward" tokenize behaviour.
 */

interface SearchIndex {
  query(text: string, limit?: number): string[];
}

/**
 * Build a search index from the given points.
 * Returns an object with a query() method.
 */
export function buildIndex(points: Point[]): SearchIndex {
  // Map from normalized prefix → set of poiIds
  const prefixMap = new Map<string, Set<string>>();

  for (const pt of points) {
    const normalized = pt.name.toLowerCase();
    const words = normalized.split(/\s+/).filter(Boolean);
    for (const word of words) {
      // Add all prefixes of each word (forward tokenize)
      for (let len = 1; len <= word.length; len++) {
        const prefix = word.slice(0, len);
        if (!prefixMap.has(prefix)) prefixMap.set(prefix, new Set());
        prefixMap.get(prefix)!.add(pt.poiId);
      }
    }
  }

  return {
    query(text: string, limit = 20): string[] {
      if (!text.trim()) return [];
      const words = text.toLowerCase().trim().split(/\s+/).filter(Boolean);
      if (words.length === 0) return [];

      // Intersect results across all query words
      let result: Set<string> | null = null;
      for (const word of words) {
        const matches = prefixMap.get(word) ?? new Set<string>();
        if (result === null) {
          result = new Set(matches);
        } else {
          for (const id of result) {
            if (!matches.has(id)) result.delete(id);
          }
        }
      }

      const ids = result ? Array.from(result) : [];
      return ids.slice(0, limit);
    },
  };
}
