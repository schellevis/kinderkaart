import { describe, it, expect } from "vitest";
import { buildIndex } from "../../src/lib/search.js";
import type { Point } from "../../src/lib/points.js";

function makePoint(poiId: string, name: string): Point {
  return {
    poiId,
    lat: 52.0,
    lon: 5.0,
    cats: ["museum"],
    name,
    indoor: null,
    free: null,
    ageMin: null,
    ageMax: null,
  };
}

const POINTS: Point[] = [
  makePoint("id:1", "Rijksmuseum Amsterdam"),
  makePoint("id:2", "Artis Zoo"),
  makePoint("id:3", "Museum van Loon"),
  makePoint("id:4", "Madurodam Den Haag"),
  makePoint("id:5", "Speeltuinen Rotterdam"),
  makePoint("id:6", "Café de Parel"),
  makePoint("id:7", "Münster Kinderspielplatz"),
];

describe("buildIndex / query", () => {
  it("returns matching poiId for exact word", () => {
    const idx = buildIndex(POINTS);
    const results = idx.query("Artis");
    expect(results).toContain("id:2");
  });

  it("forward tokenizes — prefix query works", () => {
    const idx = buildIndex(POINTS);
    const results = idx.query("Rijks");
    expect(results).toContain("id:1");
  });

  it("case-insensitive", () => {
    const idx = buildIndex(POINTS);
    expect(idx.query("rijksmuseum")).toContain("id:1");
    expect(idx.query("RIJKSMUSEUM")).toContain("id:1");
  });

  it("multi-word query narrows results", () => {
    const idx = buildIndex(POINTS);
    // "Rijksmuseum Amsterdam" → words: rijksmuseum, amsterdam
    // query "rijksmuseum amsterdam" should match id:1 but not id:3 (museum van loon)
    const results = idx.query("rijksmuseum amsterdam");
    expect(results).toContain("id:1");
    expect(results).not.toContain("id:3");
  });

  it("respects limit parameter", () => {
    // Build an index with 5 items, query with limit=2
    const idx = buildIndex(POINTS);
    const results = idx.query("museum", 2);
    expect(results.length).toBeLessThanOrEqual(2);
  });

  it("empty query returns empty array", () => {
    const idx = buildIndex(POINTS);
    expect(idx.query("")).toEqual([]);
    expect(idx.query("   ")).toEqual([]);
  });

  it("no match returns empty array", () => {
    const idx = buildIndex(POINTS);
    expect(idx.query("xyznotexist")).toEqual([]);
  });

  it("returns poiIds not point objects", () => {
    const idx = buildIndex(POINTS);
    const results = idx.query("zoo");
    expect(typeof results[0]).toBe("string");
  });

  it("diacritic normalization — accented name matches un-accented query", () => {
    const idx = buildIndex(POINTS);
    // "Café de Parel" in index; query without accent should still match
    expect(idx.query("cafe")).toContain("id:6");
    expect(idx.query("Cafe")).toContain("id:6");
  });

  it("diacritic normalization — un-accented name matches accented query", () => {
    const idx = buildIndex(POINTS);
    // Accented query normalizes to plain; "Münster" → "munster"
    expect(idx.query("Münster")).toContain("id:7");
    expect(idx.query("munster")).toContain("id:7");
  });
});
