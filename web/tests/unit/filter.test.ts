import { describe, it, expect } from "vitest";
import { matches, haversineM } from "../../src/lib/filter.js";
import type { Filter } from "../../src/lib/filter.js";
import type { Point } from "../../src/lib/points.js";

function makePoint(overrides: Partial<Point> = {}): Point {
  return {
    poiId: "nl:test:1",
    lat: 52.3,
    lon: 4.9,
    cats: ["museum"],
    name: "Test",
    indoor: null,
    free: null,
    ageMin: null,
    ageMax: null,
    ...overrides,
  };
}

const noFilter: Filter = {
  categories: null,
  indoor: null,
  free: null,
  ageForChild: null,
  maxDistanceM: null,
};

describe("matches — category filter", () => {
  it("no category filter → all pass", () => {
    const pt = makePoint({ cats: ["museum"] });
    expect(matches(pt, noFilter)).toBe(true);
  });

  it("matching category → passes", () => {
    const pt = makePoint({ cats: ["museum"] });
    expect(matches(pt, { ...noFilter, categories: new Set(["museum"]) })).toBe(true);
  });

  it("non-matching category → rejected", () => {
    const pt = makePoint({ cats: ["museum"] });
    expect(matches(pt, { ...noFilter, categories: new Set(["zoo"]) })).toBe(false);
  });

  it("point with multiple cats — at least one matches → passes", () => {
    const pt = makePoint({ cats: ["museum", "zoo"] });
    expect(matches(pt, { ...noFilter, categories: new Set(["zoo"]) })).toBe(true);
  });

  it("empty category set → all pass", () => {
    const pt = makePoint({ cats: ["museum"] });
    expect(matches(pt, { ...noFilter, categories: new Set() })).toBe(true);
  });
});

describe("matches — indoor filter ('unknown is not negative')", () => {
  it("indoor:true filter → point with indoor:true passes", () => {
    const pt = makePoint({ indoor: true });
    expect(matches(pt, { ...noFilter, indoor: true })).toBe(true);
  });

  it("indoor:true filter → point with indoor:null passes (unknown kept)", () => {
    const pt = makePoint({ indoor: null });
    expect(matches(pt, { ...noFilter, indoor: true })).toBe(true);
  });

  it("indoor:true filter → point with indoor:false excluded", () => {
    const pt = makePoint({ indoor: false });
    expect(matches(pt, { ...noFilter, indoor: true })).toBe(false);
  });

  it("indoor:false filter → point with indoor:null passes", () => {
    const pt = makePoint({ indoor: null });
    expect(matches(pt, { ...noFilter, indoor: false })).toBe(true);
  });

  it("indoor:null filter → all indoor values pass", () => {
    expect(matches(makePoint({ indoor: true }), noFilter)).toBe(true);
    expect(matches(makePoint({ indoor: false }), noFilter)).toBe(true);
    expect(matches(makePoint({ indoor: null }), noFilter)).toBe(true);
  });
});

describe("matches — free filter", () => {
  it("free:true filter → point with free:null passes", () => {
    expect(matches(makePoint({ free: null }), { ...noFilter, free: true })).toBe(true);
  });

  it("free:true filter → point with free:false excluded", () => {
    expect(matches(makePoint({ free: false }), { ...noFilter, free: true })).toBe(false);
  });
});

describe("matches — age filter", () => {
  it("no age filter → all pass regardless of age_min/max", () => {
    expect(matches(makePoint({ ageMin: 5, ageMax: 12 }), noFilter)).toBe(true);
  });

  it("child age within range → passes", () => {
    const pt = makePoint({ ageMin: 3, ageMax: 10 });
    expect(matches(pt, { ...noFilter, ageForChild: 7 })).toBe(true);
  });

  it("child age below ageMin → rejected", () => {
    const pt = makePoint({ ageMin: 5, ageMax: 12 });
    expect(matches(pt, { ...noFilter, ageForChild: 3 })).toBe(false);
  });

  it("child age above ageMax → rejected", () => {
    const pt = makePoint({ ageMin: 3, ageMax: 10 });
    expect(matches(pt, { ...noFilter, ageForChild: 13 })).toBe(false);
  });

  it("null ageMin → no lower bound", () => {
    const pt = makePoint({ ageMin: null, ageMax: 10 });
    expect(matches(pt, { ...noFilter, ageForChild: 1 })).toBe(true);
  });

  it("null ageMax → no upper bound", () => {
    const pt = makePoint({ ageMin: 5, ageMax: null });
    expect(matches(pt, { ...noFilter, ageForChild: 99 })).toBe(true);
  });

  it("both null → all ages pass", () => {
    const pt = makePoint({ ageMin: null, ageMax: null });
    expect(matches(pt, { ...noFilter, ageForChild: 7 })).toBe(true);
  });
});

describe("matches — distance filter", () => {
  it("point within distance → passes", () => {
    // Amsterdam: 52.3, 4.9; ref same location → 0m
    const pt = makePoint({ lat: 52.3, lon: 4.9 });
    const ref = { lat: 52.3, lon: 4.9 };
    expect(matches(pt, { ...noFilter, maxDistanceM: 1000 }, ref)).toBe(true);
  });

  it("point beyond distance → rejected", () => {
    // Amsterdam vs Rotterdam ~57km apart
    const pt = makePoint({ lat: 51.924, lon: 4.478 }); // Rotterdam
    const ref = { lat: 52.373, lon: 4.891 };           // Amsterdam
    expect(matches(pt, { ...noFilter, maxDistanceM: 10000 }, ref)).toBe(false);
  });

  it("no distance filter → passes regardless", () => {
    const pt = makePoint({ lat: 51.924, lon: 4.478 });
    const ref = { lat: 52.373, lon: 4.891 };
    expect(matches(pt, noFilter, ref)).toBe(true);
  });
});

describe("haversineM", () => {
  it("same point → 0", () => {
    expect(haversineM({ lat: 52.0, lon: 5.0 }, { lat: 52.0, lon: 5.0 })).toBe(0);
  });

  it("Amsterdam to Rotterdam ≈ 57km", () => {
    const d = haversineM({ lat: 52.373, lon: 4.891 }, { lat: 51.924, lon: 4.478 });
    expect(d).toBeGreaterThan(55000);
    expect(d).toBeLessThan(60000);
  });
});
