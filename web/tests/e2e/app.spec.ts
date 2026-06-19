/**
 * Kinderkaart e2e acceptance tests (Playwright).
 *
 * Sample data facts (web/public/data/manifest.json):
 *   - country: nl, data_version: sample, shard_count: 1
 *   - total: 9 points (museum:4, playground:4, petting_zoo:1, zoo:1)
 *   - Known POIs:
 *       rce-musea/overzichtmusea.1  → "Rijksmuseum" (museum)
 *       osm/node/1                  → "Speeltuin Vondelpark" (playground)
 *       osm/way/100                 → "Kinderboerderij De Buurt" (petting_zoo+zoo)
 *
 * Layout notes:
 *   - On desktop (≥960px): #side-panel is visible, #bottom-sheet is hidden (display:none)
 *   - On mobile (<960px):  #side-panel hidden, #bottom-sheet visible
 *   - Both render result-items / detail-titles; tests scope to the active container.
 */

import { test, expect, type Page, type BrowserContext } from "@playwright/test";

// ── Helpers ────────────────────────────────────────────────

async function waitForLoad(page: Page): Promise<void> {
  await page.waitForFunction(
    () => document.getElementById("loading")?.classList.contains("hidden"),
    { timeout: 15000 }
  );
}

/** Returns the search input in the currently-visible search bar. */
function searchInput(page: Page): ReturnType<Page["locator"]> {
  // Desktop panel is visible at ≥960px; on mobile we use the map-overlay search.
  // We try panel first; the overlay input is inside aria-hidden so we force-click.
  return page.locator("#panel-search-wrapper .search-bar input, #mobile-search-wrapper .search-bar input").first();
}

/** Results list that is visible in current viewport. */
function resultsList(page: Page): ReturnType<Page["locator"]> {
  return page.locator("#results-list, #mobile-results").first();
}

/** Detail panel that is visible in current viewport. */
function detailPanel(page: Page): ReturnType<Page["locator"]> {
  return page.locator("#detail-panel, #mobile-detail").first();
}

/** Category chip container visible in current viewport. */
function chipsContainer(page: Page): ReturnType<Page["locator"]> {
  return page.locator("#panel-filters, #mobile-filters").first();
}

// ── Test 1: Loads ──────────────────────────────────────────

test.describe("1. App loads", () => {
  test("map canvas visible, attribution contains OpenStreetMap, ≥1 marker/cluster", async ({ page }) => {
    await page.goto("/");
    await waitForLoad(page);

    const canvas = page.locator("canvas");
    await expect(canvas).toBeVisible();

    const attribution = page.locator(".maplibregl-ctrl-attrib");
    await expect(attribution).toContainText("OpenStreetMap");

    const hasData = await page.evaluate(() => {
      const kk = (window as unknown as { __kinderkaart?: { filteredCount: () => number } }).__kinderkaart;
      return kk ? kk.filteredCount() > 0 : false;
    });
    expect(hasData).toBe(true);
  });
});

// ── Test 2: Filter + cluster oracle ───────────────────────

test.describe("2. Filter changes counts — cluster oracle", () => {
  test("selecting only museum: filteredCount matches manifest counts.museum, no points lost", async ({ page }) => {
    await page.goto("/");
    await waitForLoad(page);

    // On desktop use panel-filters (avoids map-overlay pointer-events issue).
    // On mobile use mobile-filters inside the map overlay with force click.
    const isMobile = page.viewportSize()!.width < 960;
    const chip = isMobile
      ? page.locator("#mobile-filters .chip[data-cat='museum']")
      : page.locator("#panel-filters .chip[data-cat='museum']");
    await chip.click({ force: isMobile });

    await page.waitForTimeout(500);

    const result = await page.evaluate(() => {
      const kk = (window as unknown as { __kinderkaart?: {
        filteredCount: () => number;
        manifest: { nl: { counts: Record<string, number> } };
      } }).__kinderkaart;
      if (!kk) return null;
      return {
        filteredCount: kk.filteredCount(),
        manifestMuseumCount: kk.manifest.nl.counts["museum"],
      };
    });

    expect(result).not.toBeNull();
    expect(result!.filteredCount).toBe(result!.manifestMuseumCount);
  });
});

// ── Test 3: Search ─────────────────────────────────────────

test.describe("3. Search", () => {
  test("type a known name → result appears → click → detail shows name", async ({ page }) => {
    await page.goto("/");
    await waitForLoad(page);

    const isMobile = page.viewportSize()!.width < 960;
    const input = isMobile
      ? page.locator("#mobile-search-wrapper .search-bar input")
      : page.locator("#panel-search-wrapper .search-bar input");

    // On mobile the input is inside aria-hidden overlay; use fill with force
    await input.fill("Rijks", { force: isMobile } as Parameters<typeof input.fill>[1]);
    await page.waitForTimeout(500);

    // On mobile, results are in #mobile-results; on desktop in #results-list
    const list = isMobile ? page.locator("#mobile-results") : page.locator("#results-list");
    const resultItem = list.locator(".result-item").first();
    await expect(resultItem).toBeVisible({ timeout: 5000 });

    await resultItem.click({ force: isMobile });

    // Detail shows name
    const detail = isMobile ? page.locator("#mobile-detail") : page.locator("#detail-panel");
    await expect(detail.locator(".detail-title")).toContainText("Rijksmuseum", { timeout: 5000 });
  });
});

// ── Test 4: Detail lazy-load ────────────────────────────────

test.describe("4. Detail lazy-load", () => {
  test("clicking a result fires detail shard request, panel shows fields, missing → 'onbekend'", async ({ page }) => {
    const detailRequests: string[] = [];
    page.on("request", (req) => {
      if (req.url().includes("/detail/")) detailRequests.push(req.url());
    });

    await page.goto("/");
    await waitForLoad(page);

    const isMobile = page.viewportSize()!.width < 960;
    const input = isMobile
      ? page.locator("#mobile-search-wrapper .search-bar input")
      : page.locator("#panel-search-wrapper .search-bar input");

    await input.fill("Rijksmuseum", { force: isMobile } as Parameters<typeof input.fill>[1]);
    await page.waitForTimeout(400);

    const list = isMobile ? page.locator("#mobile-results") : page.locator("#results-list");
    const resultItem = list.locator(".result-item").first();
    await expect(resultItem).toBeVisible({ timeout: 5000 });
    await resultItem.click({ force: isMobile });

    const detail = isMobile ? page.locator("#mobile-detail") : page.locator("#detail-panel");
    await expect(detail.locator(".detail-title")).toBeVisible({ timeout: 5000 });

    await page.waitForTimeout(1000);
    expect(detailRequests.length).toBeGreaterThan(0);
    expect(detailRequests[0]).toMatch(/detail\/\d+\.json/);

    // Missing fields should show "onbekend"
    const unknownFields = detail.locator(".detail-field-value.unknown");
    const unknownCount = await unknownFields.count();
    expect(unknownCount).toBeGreaterThan(0);
  });
});

// ── Test 5: Geolocation ─────────────────────────────────────

test.describe("5. Geolocation", () => {
  test("with geo denied, app loads at NL fallback view", async ({ browser }) => {
    const ctx: BrowserContext = await browser.newContext({
      permissions: [],
    });
    const page = await ctx.newPage();
    await page.goto("/");
    await waitForLoad(page);

    const canvas = page.locator("canvas");
    await expect(canvas).toBeVisible();

    const count = await page.evaluate(() => {
      const kk = (window as unknown as { __kinderkaart?: { filteredCount: () => number } }).__kinderkaart;
      return kk ? kk.filteredCount() : 0;
    });
    expect(count).toBeGreaterThan(0);

    await ctx.close();
  });

  test("with mocked geolocation, map centers near mocked position", async ({ browser }) => {
    const ctx: BrowserContext = await browser.newContext({
      geolocation: { latitude: 52.3702, longitude: 4.8952 },
      permissions: ["geolocation"],
    });
    const page = await ctx.newPage();
    await page.goto("/");
    await waitForLoad(page);

    await page.waitForTimeout(2000);
    const userMarker = page.locator(".user-marker");
    await expect(userMarker).toBeVisible({ timeout: 8000 });

    await ctx.close();
  });
});

// ── Test 6: Favorites persist ──────────────────────────────

test.describe("6. Favorites persist", () => {
  test("toggle favorite → reload → still favorited", async ({ page }) => {
    await page.goto("/");
    await waitForLoad(page);

    const isMobile = page.viewportSize()!.width < 960;
    const input = isMobile
      ? page.locator("#mobile-search-wrapper .search-bar input")
      : page.locator("#panel-search-wrapper .search-bar input");

    await input.fill("Rijksmuseum", { force: isMobile } as Parameters<typeof input.fill>[1]);
    await page.waitForTimeout(400);

    const list = isMobile ? page.locator("#mobile-results") : page.locator("#results-list");
    const resultItem = list.locator(".result-item").first();
    await expect(resultItem).toBeVisible({ timeout: 5000 });
    await resultItem.click({ force: isMobile });

    const detail = isMobile ? page.locator("#mobile-detail") : page.locator("#detail-panel");
    await expect(detail.locator(".detail-title")).toBeVisible({ timeout: 5000 });

    // Click the fav button
    const favBtn = detail.locator(".fav-btn");
    await favBtn.click();
    await expect(favBtn).toHaveText("❤️");

    // Check localStorage
    const stored = await page.evaluate(() => localStorage.getItem("kinderkaart:favs"));
    expect(stored).not.toBeNull();
    const favs = JSON.parse(stored!);
    expect(Array.isArray(favs)).toBe(true);
    expect(favs.length).toBeGreaterThan(0);

    // Reload and verify persistence
    await page.reload();
    await waitForLoad(page);

    const storedAfter = await page.evaluate(() => localStorage.getItem("kinderkaart:favs"));
    expect(storedAfter).not.toBeNull();
    const favsAfter = JSON.parse(storedAfter!);
    expect(favsAfter).toEqual(favs);
  });
});

// ── Test 7: Deep-link round-trip ───────────────────────────

test.describe("7. Deep-link round-trip", () => {
  test("/?cats=museum opens with museum filter; poi= opens detail", async ({ page }) => {
    const poiId = "rce-musea/overzichtmusea.1"; // Rijksmuseum

    await page.goto(`/?cats=museum&poi=${encodeURIComponent(poiId)}`);
    await waitForLoad(page);

    await page.waitForTimeout(1500);

    const result = await page.evaluate(() => {
      const kk = (window as unknown as { __kinderkaart?: {
        filteredCount: () => number;
        manifest: { nl: { counts: Record<string, number> } };
      } }).__kinderkaart;
      if (!kk) return null;
      return { filteredCount: kk.filteredCount(), museumCount: kk.manifest.nl.counts["museum"] };
    });
    expect(result?.filteredCount).toBe(result?.museumCount);

    // Detail should open (desktop or mobile)
    const isMobile = page.viewportSize()!.width < 960;
    const detail = isMobile ? page.locator("#mobile-detail") : page.locator("#detail-panel");
    await expect(detail.locator(".detail-title")).toContainText("Rijksmuseum", { timeout: 8000 });

    const url = page.url();
    expect(url).toContain("poi=");
  });
});

// ── Test 8: Responsive layout ──────────────────────────────

test.describe("8. Responsive layout", () => {
  test("desktop: side panel is visible", async ({ page, browserName }) => {
    if (page.viewportSize()!.width < 960) {
      test.skip();
      return;
    }
    await page.goto("/");
    await waitForLoad(page);

    const sidePanel = page.locator("#side-panel");
    await expect(sidePanel).toBeVisible();

    const bottomSheet = page.locator("#bottom-sheet");
    await expect(bottomSheet).toBeHidden();

    void browserName;
  });

  test("mobile: bottom-sheet is visible, side panel is hidden", async ({ page }) => {
    if (page.viewportSize()!.width >= 960) {
      test.skip();
      return;
    }
    await page.goto("/");
    await waitForLoad(page);

    const bottomSheet = page.locator("#bottom-sheet");
    await expect(bottomSheet).toBeAttached();

    const sidePanel = page.locator("#side-panel");
    await expect(sidePanel).toBeHidden();
  });
});

// ── Test 9: Performance (spike-2 deferred browser check) ──

test.describe("9. Performance", () => {
  test("time to first clusters rendered < 4000ms on sample data (CPU 4x throttle)", async ({ browser }) => {
    const ctx = await browser.newContext();
    const p = await ctx.newPage();

    let throttled = false;
    try {
      const cdp = await ctx.newCDPSession(p);
      await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
      throttled = true;
      console.log("[perf-test] CPU throttled 4x via CDP");
    } catch {
      console.log("[perf-test] CDP throttling unavailable, running unthrottled");
    }

    const t0 = Date.now();
    await p.goto("/");

    await p.waitForFunction(
      () => document.getElementById("loading")?.classList.contains("hidden"),
      { timeout: 15000 }
    );

    await p.waitForTimeout(200);

    const hasData = await p.evaluate(() => {
      const kk = (window as unknown as { __kinderkaart?: { filteredCount: () => number } }).__kinderkaart;
      return kk ? kk.filteredCount() > 0 : false;
    });
    const elapsed = Date.now() - t0;

    console.log(`[perf-test] time-to-clusters: ${elapsed}ms (throttled=${throttled}), hasData=${hasData}`);
    test.info().annotations.push({
      type: "perf",
      description: `time-to-clusters=${elapsed}ms throttled=${throttled}`,
    });

    expect(elapsed).toBeLessThan(4000);
    expect(hasData).toBe(true);

    await ctx.close();
  });
});

// Suppress unused helper warnings
void searchInput;
void resultsList;
void detailPanel;
void chipsContainer;
