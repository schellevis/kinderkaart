/**
 * Detail panel UI component.
 * All DOM construction uses textContent / createElement — no innerHTML with untrusted content.
 */

import { Favorites } from "../lib/favorites.js";
import { safeHttpUrl } from "../lib/url.js";
import { displayName } from "../lib/displayName.js";

/**
 * Darker text/border colors for category chips — ≥4.5:1 contrast on #FBFAF7/white (WCAG AA).
 * The bright fill colors listed above fail AA for text; these darker variants pass.
 */
const CAT_CHIP_COLORS: Record<string, string> = {
  playground: "#9A5A00",
  museum: "#6C5CE7",
  zoo: "#1A7A40",
  petting_zoo: "#6B4E45",
  pool: "#1A6899",
  play_park: "#C0392B",
  restaurant_kidfriendly: "#9A7A00",
};

const CAT_GLYPHS: Record<string, string> = {
  playground: "🛝",
  museum: "🏛️",
  zoo: "🦁",
  petting_zoo: "🐑",
  pool: "🏊",
  play_park: "🌳",
  restaurant_kidfriendly: "🍽️",
};

const CAT_LABELS: Record<string, string> = {
  playground: "Speeltuin",
  museum: "Museum",
  zoo: "Dierentuin",
  petting_zoo: "Kinderboerderij",
  pool: "Zwembad",
  play_park: "Speelpark",
  restaurant_kidfriendly: "Restaurant",
};

export interface DetailRecord {
  name: string;
  lat: number;
  lon: number;
  categories: string[];
  address: {
    street?: string;
    city?: string;
    postcode?: string;
    country?: string;
  } | null;
  opening_hours: string | null;
  website: string | null;
  sources: Array<{
    source_id: string;
    source_record_id: string;
    source_url: string | null;
  }>;
  last_updated: string | null;
  tags?: {
    evidence?: Array<{
      signal: string;
      direct: boolean;
      source_record_id: string;
      source_url: string;
      evidence_date: string;
    }>;
  };
}

export interface DetailOptions {
  poiId: string;
  record: DetailRecord;
  onClose: () => void;
  onFavToggle?: (poiId: string, isFav: boolean) => void;
}

const UNKNOWN = "onbekend";

/** Fix 7b: Build the Website field row with hostname as link text. */
function buildWebsiteField(website: string | null | undefined): HTMLElement {
  const row = document.createElement("div");
  row.className = "detail-field";

  const lbl = document.createElement("span");
  lbl.className = "detail-field-label";
  lbl.textContent = "Website";

  const val = document.createElement("span");
  val.className = "detail-field-value";

  if (!website) {
    val.textContent = UNKNOWN;
    val.classList.add("unknown");
  } else {
    const safe = safeHttpUrl(website);
    if (safe !== null) {
      const a = document.createElement("a");
      a.href = safe;
      // Show hostname (without www.) as the link text, or fallback to "Bezoek website →"
      let linkText: string;
      try {
        const hostname = new URL(safe).hostname.replace(/^www\./, "");
        linkText = hostname || "Bezoek website →";
      } catch {
        linkText = "Bezoek website →";
      }
      a.textContent = linkText;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      val.appendChild(a);
    } else {
      val.textContent = website;
    }
  }

  row.appendChild(lbl);
  row.appendChild(val);
  return row;
}

function field(label: string, value: string | null | undefined, isLink = false): HTMLElement {
  const row = document.createElement("div");
  row.className = "detail-field";

  const lbl = document.createElement("span");
  lbl.className = "detail-field-label";
  lbl.textContent = label;

  const val = document.createElement("span");
  val.className = "detail-field-value";

  if (!value) {
    val.textContent = UNKNOWN;
    val.classList.add("unknown");
  } else if (isLink) {
    const safe = safeHttpUrl(value);
    if (safe !== null) {
      const a = document.createElement("a");
      a.href = safe;
      a.textContent = value;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      val.appendChild(a);
    } else {
      val.textContent = value;
    }
  } else {
    val.textContent = value;
  }

  row.appendChild(lbl);
  row.appendChild(val);
  return row;
}

export function renderDetail(container: HTMLElement, opts: DetailOptions): void {
  // Clear safely (no untrusted HTML)
  while (container.firstChild) container.removeChild(container.firstChild);

  const favs = new Favorites();
  const content = document.createElement("div");
  content.className = "detail-content";

  // Set left accent-border color to the primary category's bright fill color
  const primaryCat = opts.record.categories[0];
  const accentColors: Record<string, string> = {
    playground: "#F2994A",
    museum: "#6C5CE7",
    zoo: "#27AE60",
    petting_zoo: "#8D6E63",
    pool: "#2D9CDB",
    play_park: "#EB5757",
    restaurant_kidfriendly: "#F2C94C",
  };
  const accentColor = accentColors[primaryCat] ?? "var(--color-accent)";
  content.style.setProperty("--detail-accent-color", accentColor);

  // Header: title + fav button + close button
  const header = document.createElement("div");
  header.className = "detail-header";

  const title = document.createElement("h2");
  title.className = "detail-title";
  title.textContent = displayName(opts.record.name, opts.record.categories);

  const actions = document.createElement("div");
  actions.style.display = "flex";
  actions.style.gap = "var(--space-2)";

  const favBtn = document.createElement("button");
  favBtn.className = "fav-btn";
  favBtn.setAttribute("type", "button");
  const isFav = favs.has(opts.poiId);
  favBtn.textContent = isFav ? "❤️" : "🤍";
  favBtn.setAttribute("aria-label", isFav ? "Verwijder uit favorieten" : "Voeg toe aan favorieten");
  favBtn.setAttribute("aria-pressed", String(isFav));
  if (isFav) favBtn.classList.add("active");

  favBtn.addEventListener("click", () => {
    const now = favs.toggle(opts.poiId);
    favBtn.textContent = now ? "❤️" : "🤍";
    favBtn.setAttribute("aria-label", now ? "Verwijder uit favorieten" : "Voeg toe aan favorieten");
    favBtn.setAttribute("aria-pressed", String(now));
    favBtn.classList.toggle("active", now);
    opts.onFavToggle?.(opts.poiId, now);
  });

  const closeBtn = document.createElement("button");
  closeBtn.className = "detail-close";
  closeBtn.setAttribute("type", "button");
  closeBtn.setAttribute("aria-label", "Sluit details");
  closeBtn.textContent = "✕";
  closeBtn.addEventListener("click", opts.onClose);

  actions.appendChild(favBtn);
  actions.appendChild(closeBtn);
  header.appendChild(title);
  header.appendChild(actions);

  // Category chips
  const cats = document.createElement("div");
  cats.className = "detail-cats";
  for (const cat of opts.record.categories) {
    const chip = document.createElement("span");
    chip.className = "detail-cat-chip";
    // Use darker variant for text/border (AA contrast), bright color only for background hint
    const chipColor = CAT_CHIP_COLORS[cat] ?? "#6B7280";
    chip.style.color = chipColor;
    chip.style.borderColor = chipColor;
    chip.textContent = (CAT_GLYPHS[cat] ?? "") + " " + (CAT_LABELS[cat] ?? cat);
    cats.appendChild(chip);
  }

  content.appendChild(header);
  content.appendChild(cats);

  // Address
  const addr = opts.record.address;
  const addrStr = addr
    ? [addr.street, addr.city, addr.postcode].filter(Boolean).join(", ") || null
    : null;
  content.appendChild(field("Adres", addrStr));

  // Fix 7a: Directions link
  const dirRow = document.createElement("div");
  dirRow.className = "detail-field";
  const dirLbl = document.createElement("span");
  dirLbl.className = "detail-field-label";
  dirLbl.textContent = "Route";
  const dirVal = document.createElement("span");
  dirVal.className = "detail-field-value";
  const dirUrl = safeHttpUrl(
    `https://www.google.com/maps/dir/?api=1&destination=${opts.record.lat},${opts.record.lon}`
  );
  if (dirUrl) {
    const dirA = document.createElement("a");
    dirA.href = dirUrl;
    dirA.textContent = "Routebeschrijving";
    dirA.target = "_blank";
    dirA.rel = "noopener noreferrer";
    dirVal.appendChild(dirA);
  }
  dirRow.appendChild(dirLbl);
  dirRow.appendChild(dirVal);
  content.appendChild(dirRow);

  // Opening hours
  content.appendChild(field("Openingstijden", opts.record.opening_hours));

  // Fix 7b: Website — show hostname as link text instead of full raw URL
  const websiteRow = buildWebsiteField(opts.record.website);
  content.appendChild(websiteRow);

  const evidence = opts.record.tags?.evidence ?? [];
  if (evidence.length > 0) {
    const evidenceRow = document.createElement("div");
    evidenceRow.className = "detail-field";
    const label = document.createElement("span");
    label.className = "detail-field-label";
    label.textContent = "Waarom kindvriendelijk?";
    const values = document.createElement("span");
    values.className = "detail-field-value";
    for (const item of evidence) {
      const line = document.createElement("div");
      const safe = safeHttpUrl(item.source_url);
      const text = `${item.signal}${item.direct ? " (direct bewijs)" : ""}`;
      if (safe) {
        const link = document.createElement("a");
        link.href = safe;
        link.textContent = text;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        line.appendChild(link);
      } else {
        line.textContent = text;
      }
      values.appendChild(line);
    }
    evidenceRow.appendChild(label);
    evidenceRow.appendChild(values);
    content.appendChild(evidenceRow);
  }

  // Last updated
  const lastUpdated = opts.record.last_updated
    ? new Date(opts.record.last_updated).toLocaleDateString("nl-NL", {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : null;
  content.appendChild(field("Bijgewerkt", lastUpdated));

  // Provenance
  if (opts.record.sources.length > 0) {
    const provRow = document.createElement("div");
    provRow.className = "detail-field";

    const provLbl = document.createElement("span");
    provLbl.className = "detail-field-label";
    provLbl.textContent = "Bronnen";

    const provVal = document.createElement("span");
    provVal.className = "detail-field-value";
    provVal.style.fontSize = "var(--font-size-xs)";
    provVal.style.color = "var(--color-ink-subtle)";

    for (const src of opts.record.sources) {
      const srcLine = document.createElement("div");
      if (src.source_url) {
        const safe = safeHttpUrl(src.source_url);
        if (safe !== null) {
          const a = document.createElement("a");
          a.href = safe;
          a.textContent = src.source_id;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.style.color = "var(--color-accent)";
          srcLine.appendChild(a);
        } else {
          srcLine.textContent = src.source_id;
        }
      } else {
        srcLine.textContent = src.source_id;
      }
      provVal.appendChild(srcLine);
    }

    provRow.appendChild(provLbl);
    provRow.appendChild(provVal);
    content.appendChild(provRow);
  }

  container.appendChild(content);
}
