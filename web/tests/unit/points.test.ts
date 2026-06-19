import { describe, it, expect } from "vitest";
import { decodePoints } from "../../src/lib/points.js";
import type { PointsPayload } from "../../src/lib/points.js";

const CATEGORIES = ["museum", "playground", "play_park", "petting_zoo", "pool", "restaurant_kidfriendly", "zoo"];

function makePayload(overrides: Partial<(string | number | boolean | null)[]>[] = []): PointsPayload {
  const fields = ["poi_id", "lat", "lon", "cats", "name", "indoor", "free", "age_min", "age_max"];
  const baseRows: (string | number | boolean | null)[][] = [
    ["nl:test:1", 52.3, 4.9, 0b0000001, "Museum Amsterdam", true, false, 4, 12],  // museum (bit 0)
    ["nl:test:2", 52.1, 5.1, 0b0000010, "Playground Centrum", null, null, null, null], // playground (bit 1)
    ["nl:test:3", 51.9, 4.5, 0b0000100, "Play Park Zuid", false, true, null, 10],   // play_park (bit 2)
  ];
  const rows = baseRows.map((row, i) => {
    if (overrides[i]) return [...row.slice(0, row.length)].map((v, j) => overrides[i][j] !== undefined ? overrides[i][j] : v);
    return row;
  });
  return { fields, categories: CATEGORIES, points: rows };
}

describe("decodePoints", () => {
  it("decodes category bitmask to names", () => {
    const payload = makePayload();
    const pts = decodePoints(payload);
    expect(pts[0].cats).toEqual(["museum"]);
    expect(pts[1].cats).toEqual(["playground"]);
    expect(pts[2].cats).toEqual(["play_park"]);
  });

  it("handles multi-category bitmask", () => {
    const payload: PointsPayload = {
      fields: ["poi_id", "lat", "lon", "cats", "name", "indoor", "free", "age_min", "age_max"],
      categories: CATEGORIES,
      // museum=bit0, zoo=bit6 → mask = 0b1000001 = 65
      points: [["nl:test:multi", 52.0, 5.0, 65, "Zoo+Museum", null, null, null, null]],
    };
    const pts = decodePoints(payload);
    expect(pts[0].cats).toContain("museum");
    expect(pts[0].cats).toContain("zoo");
    expect(pts[0].cats).toHaveLength(2);
  });

  it("preserves null facets as null (not false)", () => {
    const payload = makePayload();
    const pts = decodePoints(payload);
    expect(pts[1].indoor).toBeNull();
    expect(pts[1].free).toBeNull();
    expect(pts[1].ageMin).toBeNull();
    expect(pts[1].ageMax).toBeNull();
  });

  it("maps all fields correctly", () => {
    const payload = makePayload();
    const pts = decodePoints(payload);
    expect(pts[0].poiId).toBe("nl:test:1");
    expect(pts[0].lat).toBe(52.3);
    expect(pts[0].lon).toBe(4.9);
    expect(pts[0].name).toBe("Museum Amsterdam");
    expect(pts[0].indoor).toBe(true);
    expect(pts[0].free).toBe(false);
    expect(pts[0].ageMin).toBe(4);
    expect(pts[0].ageMax).toBe(12);
  });

  it("returns empty array for empty points", () => {
    const payload: PointsPayload = {
      fields: ["poi_id", "lat", "lon", "cats", "name", "indoor", "free", "age_min", "age_max"],
      categories: CATEGORIES,
      points: [],
    };
    expect(decodePoints(payload)).toHaveLength(0);
  });
});
