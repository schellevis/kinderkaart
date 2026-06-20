import { beforeEach, describe, expect, it } from "vitest";
import { renderDetail } from "../../src/ui/detail.js";

describe("restaurant evidence detail", () => {
  beforeEach(() => localStorage.clear());

  it("shows auditable direct evidence with a safe source link", () => {
    const container = document.createElement("div");
    renderDetail(container, {
      poiId: "restaurants-agent/r1",
      onClose: () => undefined,
      record: {
        name: "De Speelhoek",
        lat: 52,
        lon: 5,
        categories: ["restaurant_kidfriendly"],
        address: null,
        opening_hours: null,
        website: null,
        sources: [],
        last_updated: null,
        tags: {
          evidence: [{
            signal: "speelhoek",
            direct: true,
            source_record_id: "page:kids",
            source_url: "https://example.com/kids",
            evidence_date: "2026-06-19",
          }],
        },
      },
    });

    expect(container.textContent).toContain("Waarom kindvriendelijk?");
    expect(container.textContent).toContain("speelhoek (direct bewijs)");
    expect(container.querySelector("a[href='https://example.com/kids']")).not.toBeNull();
  });
});
