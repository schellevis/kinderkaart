import { describe, it, expect } from "vitest";
import { encode, decode } from "../../src/lib/deeplink.js";
import type { DeepLinkState } from "../../src/lib/deeplink.js";

describe("encode + decode round-trip", () => {
  it("round-trips full state", () => {
    const state: DeepLinkState = {
      lat: 52.3702,
      lon: 4.8952,
      z: 12,
      poi: "nl:osm:node:123",
      q: "museum",
      cats: ["museum", "zoo"],
    };
    const qs = encode(state);
    const decoded = decode(qs);
    expect(decoded.lat).toBeCloseTo(52.3702, 4);
    expect(decoded.lon).toBeCloseTo(4.8952, 4);
    expect(decoded.z).toBe(12);
    expect(decoded.poi).toBe("nl:osm:node:123");
    expect(decoded.q).toBe("museum");
    expect(decoded.cats).toEqual(["museum", "zoo"]);
  });

  it("round-trips partial state (cats only)", () => {
    const state: DeepLinkState = { cats: ["museum"] };
    const qs = encode(state);
    const decoded = decode(qs);
    expect(decoded.cats).toEqual(["museum"]);
    expect(decoded.poi).toBeUndefined();
    expect(decoded.lat).toBeUndefined();
  });

  it("decode is tolerant of missing params", () => {
    const decoded = decode("");
    expect(decoded).toEqual({});
  });

  it("decode ignores invalid numeric values", () => {
    const decoded = decode("lat=notanumber&lon=5.0");
    expect(decoded.lat).toBeUndefined();
    expect(decoded.lon).toBeCloseTo(5.0);
  });

  it("cats are comma-separated in the query string", () => {
    const state: DeepLinkState = { cats: ["museum", "zoo", "playground"] };
    const qs = encode(state);
    expect(qs).toContain("cats=museum%2Czoo%2Cplayground");
  });

  it("empty cats list is not serialized", () => {
    const qs = encode({ cats: [] });
    expect(qs).toBe("");
  });

  it("poi with colons survives round-trip", () => {
    const state: DeepLinkState = { poi: "nl:wikidata:Q12345" };
    const decoded = decode(encode(state));
    expect(decoded.poi).toBe("nl:wikidata:Q12345");
  });
});
