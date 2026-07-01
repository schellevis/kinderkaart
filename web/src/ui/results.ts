/**
 * Results list UI component.
 */

import type { Point } from "../lib/points.js";
import { displayName } from "../lib/displayName.js";
import { CATEGORY_ICONS, PIN_ICON, SEARCH_ICON, iconSpan } from "../lib/icons.js";

const CAT_COLORS: Record<string, string> = {
  playground: "#F2994A",
  museum: "#6C5CE7",
  zoo: "#27AE60",
  petting_zoo: "#8D6E63",
  pool: "#2D9CDB",
  play_park: "#EB5757",
  restaurant_kidfriendly: "#F2C94C",
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

export interface ResultsOptions {
  points: Point[];
  selectedId: string | null;
  onSelect: (poiId: string) => void;
  /** Max items to render into the DOM (rest is summarised). Guards against 30k+ nodes. */
  max?: number;
}

/** Default cap on rendered result rows — the full set can be ~40k POIs. */
export const DEFAULT_MAX_RESULTS = 200;

export function renderResults(container: HTMLElement, opts: ResultsOptions): void {
  while (container.firstChild) container.removeChild(container.firstChild);

  if (opts.points.length === 0) {
    const empty = document.createElement("div");
    empty.className = "results-empty";

    const emojiEl = iconSpan(SEARCH_ICON, "results-empty-emoji");

    const msg = document.createElement("p");
    msg.className = "results-empty-msg";
    msg.textContent = "Geen resultaten gevonden.";

    const sub = document.createElement("p");
    sub.className = "results-empty-sub";
    sub.textContent = "Probeer andere filters of een bredere zoekopdracht.";

    empty.appendChild(emojiEl);
    empty.appendChild(msg);
    empty.appendChild(sub);
    container.appendChild(empty);
    return;
  }

  const max = opts.max ?? DEFAULT_MAX_RESULTS;

  // Fix 6a: top truncation hint when list is capped
  if (opts.points.length > max) {
    const topHint = document.createElement("p");
    topHint.className = "results-truncated-top";
    topHint.textContent = `Dichtstbijzijnde ${max} van ${opts.points.length} getoond`;
    container.appendChild(topHint);
  }

  for (const pt of opts.points.slice(0, max)) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "result-item";
    item.setAttribute("role", "listitem");
    item.dataset.poiId = pt.poiId;

    if (pt.poiId === opts.selectedId) {
      item.classList.add("selected");
    }

    const color = CAT_COLORS[pt.cats[0]] ?? "#9E9E9E";
    const glyph = CATEGORY_ICONS[pt.cats[0]] ?? PIN_ICON;

    const marker = document.createElement("div");
    marker.className = "result-marker";
    marker.style.background = color + "33";
    marker.style.color = color;
    marker.innerHTML = glyph;
    marker.setAttribute("aria-hidden", "true");

    const info = document.createElement("div");
    info.className = "result-info";

    const name = document.createElement("div");
    name.className = "result-name";
    name.textContent = displayName(pt.name, pt.cats);

    const meta = document.createElement("div");
    meta.className = "result-meta";
    meta.textContent = pt.cats.map((c) => CAT_LABELS[c] ?? c).join(", ");

    info.appendChild(name);
    info.appendChild(meta);
    item.appendChild(marker);
    item.appendChild(info);

    const activate = () => opts.onSelect(pt.poiId);
    item.addEventListener("click", activate);
    item.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        activate();
      }
    });

    container.appendChild(item);
  }

  if (opts.points.length > max) {
    const more = document.createElement("p");
    more.className = "results-truncated";
    more.textContent =
      `Eerste ${max} van ${opts.points.length} getoond — zoom in op de kaart, ` +
      `zoek of filter om te verfijnen.`;
    container.appendChild(more);
  }
}
