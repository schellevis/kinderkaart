/**
 * Detail panel UI component.
 * All DOM construction uses textContent / createElement — no innerHTML with untrusted content.
 */

import { Favorites } from "../lib/favorites.js";

const CAT_COLORS: Record<string, string> = {
  playground: "#F2994A",
  museum: "#6C5CE7",
  zoo: "#27AE60",
  petting_zoo: "#8D6E63",
  pool: "#2D9CDB",
  play_park: "#EB5757",
  restaurant_kidfriendly: "#F2C94C",
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
}

export interface DetailOptions {
  poiId: string;
  record: DetailRecord;
  onClose: () => void;
  onFavToggle?: (poiId: string, isFav: boolean) => void;
}

const UNKNOWN = "onbekend";

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
    const a = document.createElement("a");
    a.href = value;
    a.textContent = value;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    val.appendChild(a);
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

  // Header: title + fav button + close button
  const header = document.createElement("div");
  header.className = "detail-header";

  const title = document.createElement("h2");
  title.className = "detail-title";
  title.textContent = opts.record.name;

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
    const color = CAT_COLORS[cat] ?? "#9E9E9E";
    chip.style.color = color;
    chip.style.borderColor = color;
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

  // Opening hours
  content.appendChild(field("Openingstijden", opts.record.opening_hours));

  // Website
  content.appendChild(field("Website", opts.record.website, true));

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
        const a = document.createElement("a");
        a.href = src.source_url;
        a.textContent = src.source_id;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.style.color = "var(--color-accent)";
        srcLine.appendChild(a);
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
