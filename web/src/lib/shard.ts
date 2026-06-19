import { fnv1a } from "./fnv1a.js";

/**
 * Returns the shard index for a given poi_id and shard count.
 * Matches data_pipeline/build_detail.py shard_of().
 */
export function shardOf(poiId: string, shardCount: number): number {
  return fnv1a(poiId) % shardCount;
}

/**
 * Returns the URL path to the detail JSON shard for a given poi_id.
 */
export function detailUrl(base: string, poiId: string, shardCount: number): string {
  return `${base}/${shardOf(poiId, shardCount)}.json`;
}
