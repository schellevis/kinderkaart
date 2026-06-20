/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from "vitest";
import { Favorites } from "../../src/lib/favorites.js";

describe("Favorites", () => {
  let favs: Favorites;

  beforeEach(() => {
    localStorage.clear();
    favs = new Favorites();
  });

  it("starts empty", () => {
    expect(favs.list()).toEqual([]);
    expect(favs.has("a")).toBe(false);
  });

  it("add persists to localStorage", () => {
    favs.add("nl:osm:1");
    expect(favs.has("nl:osm:1")).toBe(true);
    expect(favs.list()).toContain("nl:osm:1");

    // Verify it's in localStorage
    const raw = localStorage.getItem("kinderkaart:favs");
    expect(raw).not.toBeNull();
    expect(JSON.parse(raw!)).toContain("nl:osm:1");
  });

  it("add deduplicates", () => {
    favs.add("nl:osm:1");
    favs.add("nl:osm:1");
    expect(favs.list()).toHaveLength(1);
  });

  it("remove works", () => {
    favs.add("nl:osm:1");
    favs.add("nl:osm:2");
    favs.remove("nl:osm:1");
    expect(favs.has("nl:osm:1")).toBe(false);
    expect(favs.has("nl:osm:2")).toBe(true);
  });

  it("migrates an aliased id without duplicates", () => {
    favs.add("old-id");
    favs.add("new-id");
    favs.replace("old-id", "new-id");
    expect(favs.list()).toEqual(["new-id"]);
  });

  it("toggle adds then removes", () => {
    const result1 = favs.toggle("nl:osm:3");
    expect(result1).toBe(true);
    expect(favs.has("nl:osm:3")).toBe(true);

    const result2 = favs.toggle("nl:osm:3");
    expect(result2).toBe(false);
    expect(favs.has("nl:osm:3")).toBe(false);
  });

  it("toggle persists across new Favorites instances (simulates reload)", () => {
    favs.add("nl:osm:persist");
    const favs2 = new Favorites();
    expect(favs2.has("nl:osm:persist")).toBe(true);
  });

  it("handles corrupted localStorage gracefully", () => {
    localStorage.setItem("kinderkaart:favs", "not-json{{{");
    const f = new Favorites();
    expect(f.list()).toEqual([]);
    expect(f.has("anything")).toBe(false);
  });

  it("clear removes all", () => {
    favs.add("a");
    favs.add("b");
    favs.clear();
    expect(favs.list()).toHaveLength(0);
  });
});
