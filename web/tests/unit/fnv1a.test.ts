import { describe, it, expect } from "vitest";
import { fnv1a } from "../../src/lib/fnv1a.js";

describe("fnv1a", () => {
  it('fnv1a("") === 2166136261 (offset basis)', () => {
    expect(fnv1a("")).toBe(2166136261);
  });

  it('fnv1a("a") === 0xE40C292C', () => {
    expect(fnv1a("a")).toBe(0xe40c292c);
  });

  it('fnv1a("foobar") === 0xBF9CF968', () => {
    expect(fnv1a("foobar")).toBe(0xbf9cf968);
  });

  it("returns unsigned 32-bit (no negative values)", () => {
    // Exhaustive spot-check: no result should be negative
    const samples = ["hello", "world", "kinderkaart", "nl:wikidata:Q12345", "museum"];
    for (const s of samples) {
      expect(fnv1a(s)).toBeGreaterThanOrEqual(0);
      expect(fnv1a(s)).toBeLessThanOrEqual(0xffffffff);
    }
  });

  it("handles multi-byte UTF-8 (emoji)", () => {
    // Just verify it runs and returns a valid unsigned 32-bit int
    const result = fnv1a("🧒");
    expect(result).toBeGreaterThanOrEqual(0);
    expect(result).toBeLessThanOrEqual(0xffffffff);
  });
});
