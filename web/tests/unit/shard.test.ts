import { describe, it, expect } from "vitest";
import { shardOf, detailUrl } from "../../src/lib/shard.js";
import { fnv1a } from "../../src/lib/fnv1a.js";

describe("shardOf", () => {
  it("matches fnv1a(id) % shardCount", () => {
    const id = "nl:osm:node:123456789";
    const count = 5;
    expect(shardOf(id, count)).toBe(fnv1a(id) % count);
  });

  it("returns 0 with shardCount=1", () => {
    expect(shardOf("anything", 1)).toBe(0);
  });

  it("returns value in [0, shardCount)", () => {
    const count = 10;
    const ids = ["museum:a", "museum:b", "zoo:c", "playground:d", "nl:wikidata:Q999"];
    for (const id of ids) {
      const s = shardOf(id, count);
      expect(s).toBeGreaterThanOrEqual(0);
      expect(s).toBeLessThan(count);
    }
  });

  it("parity: known id with count=3", () => {
    // fnv1a("nl:osm:node:1") % 3 — compute expected
    const id = "nl:osm:node:1";
    const count = 3;
    const expected = fnv1a(id) % count;
    expect(shardOf(id, count)).toBe(expected);
  });
});

describe("detailUrl", () => {
  it("builds correct URL path", () => {
    const id = "nl:osm:node:123";
    const count = 5;
    const base = "data/nl/sample/detail";
    const url = detailUrl(base, id, count);
    expect(url).toBe(`${base}/${shardOf(id, count)}.json`);
  });

  it("always produces a .json URL", () => {
    expect(detailUrl("data/detail", "some-id", 3)).toMatch(/\.json$/);
  });
});
