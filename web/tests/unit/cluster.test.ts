import { describe, it, expect } from "vitest";
import { makeClusterer } from "../../src/cluster.js";
import type { Point } from "../../src/lib/points.js";
import type { ClusterFeature, PointFeature } from "../../src/cluster.js";

function makePoint(poiId: string, lat: number, lon: number): Point {
  return {
    poiId,
    lat,
    lon,
    cats: ["museum"],
    name: "Test " + poiId,
    indoor: null,
    free: null,
    ageMin: null,
    ageMax: null,
  };
}

// Two far-apart points: Amsterdam and Maastricht (~200 km apart)
const FAR_POINTS: Point[] = [
  makePoint("nl:amsterdam", 52.3702, 4.8952),
  makePoint("nl:maastricht", 50.8503, 5.6880),
];

// Many clusterable points near Amsterdam
const CLUSTER_POINTS: Point[] = Array.from({ length: 10 }, (_, i) =>
  makePoint(`nl:ams:${i}`, 52.37 + i * 0.001, 4.895 + i * 0.001)
);

const WORLD_BBOX: [number, number, number, number] = [-180, -85, 180, 85];

describe("makeClusterer / getClusters", () => {
  it("returns features for given bbox+zoom", () => {
    const c = makeClusterer(FAR_POINTS);
    const features = c.getClusters(WORLD_BBOX, 3);
    expect(features.length).toBeGreaterThan(0);
  });

  it("far-apart points at low zoom are fewer features than at high zoom", () => {
    const c = makeClusterer(CLUSTER_POINTS);
    const low = c.getClusters(WORLD_BBOX, 3);
    const high = c.getClusters(WORLD_BBOX, 16);
    // At zoom 16, clustered points should be expanded into individual markers
    expect(high.length).toBeGreaterThanOrEqual(low.length);
  });

  it("oracle: total point_count across all clusters + lone markers == filteredCount at any zoom", () => {
    const c = makeClusterer(CLUSTER_POINTS);
    for (const zoom of [3, 7, 10, 13, 16]) {
      const features = c.getClusters(WORLD_BBOX, zoom);
      let total = 0;
      for (const f of features) {
        if (f.properties.cluster) {
          total += (f as ClusterFeature).properties.point_count;
        } else {
          total += 1; // lone marker counts as 1
        }
      }
      expect(total).toBe(c.filteredCount());
    }
  });

  it("oracle holds after update() with filter", () => {
    // Use separate far points at very different lats to avoid ambiguity
    const southPt = makePoint("nl:south", 51.5, 5.0); // south of NL
    const northPts = Array.from({ length: 5 }, (_, i) =>
      makePoint(`nl:north:${i}`, 53.0 + i * 0.01, 5.0)
    );
    const allPoints = [southPt, ...northPts];
    const c = makeClusterer(allPoints);

    // Filter to only northern points (lat > 52)
    c.update((pt) => pt.lat > 52);
    expect(c.filteredCount()).toBe(northPts.length); // 5 points

    const features = c.getClusters(WORLD_BBOX, 7);
    let total = 0;
    for (const f of features) {
      if (f.properties.cluster) {
        total += (f as ClusterFeature).properties.point_count;
      } else {
        total += 1;
      }
    }
    expect(total).toBe(c.filteredCount());
  });

  it("individual (unclustered) markers have cluster:false", () => {
    const c = makeClusterer(FAR_POINTS);
    const features = c.getClusters(WORLD_BBOX, 16);
    const markers = features.filter((f) => !f.properties.cluster) as PointFeature[];
    expect(markers.length).toBe(2);
    for (const m of markers) {
      expect(m.properties.poiId).toBeDefined();
    }
  });

  it("filteredCount() returns 0 after filtering everything out", () => {
    const c = makeClusterer(FAR_POINTS);
    c.update(() => false);
    expect(c.filteredCount()).toBe(0);
    const features = c.getClusters(WORLD_BBOX, 7);
    expect(features).toHaveLength(0);
  });
});
