/**
 * Category chips + toggle filters UI.
 */

import type { Filter } from "../lib/filter.js";
import { CATEGORY_ICONS, FREE_ICON, HOME_ICON, iconSpan } from "../lib/icons.js";

const CAT_LABELS: Record<string, string> = {
  playground: "Speeltuin",
  museum: "Museum",
  zoo: "Dierentuin",
  petting_zoo: "Kinderboerderij",
  pool: "Zwembad",
  play_park: "Speelpark",
  restaurant_kidfriendly: "Restaurant",
};

/** Bright fill colors used on map markers */
const CAT_COLORS: Record<string, string> = {
  playground: "#F2994A",
  museum: "#6C5CE7",
  zoo: "#27AE60",
  petting_zoo: "#8D6E63",
  pool: "#2D9CDB",
  play_park: "#EB5757",
  restaurant_kidfriendly: "#F2C94C",
};

/**
 * Darker text/border colors for chip active state — ≥4.5:1 contrast (WCAG AA).
 * Matches tokens.css --cat-chip-* values.
 */
const CAT_CHIP_TEXT_COLORS: Record<string, string> = {
  playground: "#9A5A00",
  museum: "#6C5CE7",
  zoo: "#1A7A40",
  petting_zoo: "#6B4E45",
  pool: "#1A6899",
  play_park: "#C0392B",
  restaurant_kidfriendly: "#9A7A00",
};

/**
 * Preferred display order for category chips — most family-salient first.
 * Categories not listed here are appended at the end in whatever order they arrive.
 */
const CAT_ORDER = [
  "playground",
  "petting_zoo",
  "zoo",
  "play_park",
  "pool",
  "museum",
  "restaurant_kidfriendly",
];

export interface FiltersOptions {
  categories: string[];
  filter: Filter;
  onFilterChange: (f: Filter) => void;
}

export function createFilterChips(opts: FiltersOptions): HTMLElement {
  // Wrap scroll row in a container that provides the right-edge fade mask
  const wrapper = document.createElement("div");
  wrapper.className = "chip-scroll-wrapper";

  const container = document.createElement("div");
  container.className = "chip-scroll";
  container.setAttribute("role", "group");
  container.setAttribute("aria-label", "Categorieën filteren");

  // Sort categories according to CAT_ORDER preference
  const sortedCats = [...opts.categories].sort((a, b) => {
    const ia = CAT_ORDER.indexOf(a);
    const ib = CAT_ORDER.indexOf(b);
    if (ia === -1 && ib === -1) return 0;
    if (ia === -1) return 1;
    if (ib === -1) return -1;
    return ia - ib;
  });

  for (const cat of sortedCats) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.dataset.cat = cat;
    chip.setAttribute("type", "button");
    chip.setAttribute("aria-pressed", String(opts.filter.categories?.has(cat) ?? false));

    // Set CSS variables for category-colored active state
    const fillColor = CAT_COLORS[cat] ?? "#9E9E9E";
    const textColor = CAT_CHIP_TEXT_COLORS[cat] ?? "#6B7280";
    chip.style.setProperty("--chip-cat-color", fillColor);
    chip.style.setProperty("--chip-cat-color-text", textColor);

    // Icon carries identity — no separate dot
    const icon = CATEGORY_ICONS[cat];
    if (icon) chip.appendChild(iconSpan(icon));
    chip.appendChild(document.createTextNode(CAT_LABELS[cat] ?? cat));

    if (opts.filter.categories?.has(cat)) {
      chip.classList.add("active");
    }

    chip.addEventListener("click", () => {
      const currentCats = opts.filter.categories ? new Set(opts.filter.categories) : null;
      const newCats = currentCats ?? new Set<string>();

      if (newCats.has(cat)) {
        newCats.delete(cat);
      } else {
        newCats.add(cat);
      }

      opts.filter = {
        ...opts.filter,
        categories: newCats.size > 0 ? newCats : null,
      };

      // Update chip UI
      chip.classList.toggle("active", newCats.has(cat));
      chip.setAttribute("aria-pressed", String(newCats.has(cat)));

      opts.onFilterChange(opts.filter);
    });

    container.appendChild(chip);
  }

  wrapper.appendChild(container);
  return wrapper;
}

export function createToggleBar(opts: FiltersOptions): HTMLElement {
  const bar = document.createElement("div");
  bar.className = "toggles-bar";
  bar.setAttribute("role", "group");
  bar.setAttribute("aria-label", "Extra filters");

  const toggles: Array<{
    key: "indoor" | "free";
    label: string;
    icon: string;
  }> = [
    { key: "indoor", label: "Binnen", icon: HOME_ICON },
    { key: "free", label: "Gratis", icon: FREE_ICON },
  ];

  for (const t of toggles) {
    const btn = document.createElement("button");
    btn.className = "toggle-btn";
    btn.dataset.toggle = t.key;
    btn.setAttribute("type", "button");
    btn.setAttribute("aria-pressed", String(opts.filter[t.key] === true));
    btn.appendChild(iconSpan(t.icon));
    btn.appendChild(document.createTextNode(t.label));

    if (opts.filter[t.key] === true) {
      btn.classList.add("active");
    }

    btn.addEventListener("click", () => {
      const current = opts.filter[t.key];
      opts.filter = {
        ...opts.filter,
        [t.key]: current === true ? null : true,
      };
      const isActive = opts.filter[t.key] === true;
      btn.classList.toggle("active", isActive);
      btn.setAttribute("aria-pressed", String(isActive));
      opts.onFilterChange(opts.filter);
    });

    bar.appendChild(btn);
  }

  // Age filter
  const ageWrapper = document.createElement("div");
  ageWrapper.className = "age-filter";

  const ageLabel = document.createElement("label");
  ageLabel.textContent = "Leeftijd:";
  ageLabel.setAttribute("for", "age-input");

  const ageInput = document.createElement("input");
  ageInput.type = "number";
  ageInput.id = "age-input";
  ageInput.dataset.filterInput = "age";
  ageInput.min = "0";
  ageInput.max = "18";
  ageInput.placeholder = "–";
  ageInput.value = opts.filter.ageForChild == null ? "" : String(opts.filter.ageForChild);
  ageInput.setAttribute("aria-label", "Leeftijd van het kind");

  ageInput.addEventListener("input", () => {
    const val = parseInt(ageInput.value, 10);
    opts.filter = {
      ...opts.filter,
      ageForChild: isNaN(val) ? null : val,
    };
    opts.onFilterChange(opts.filter);
  });

  ageWrapper.appendChild(ageLabel);
  ageWrapper.appendChild(ageInput);
  bar.appendChild(ageWrapper);

  const distanceLabel = document.createElement("label");
  distanceLabel.className = "age-filter";
  distanceLabel.appendChild(document.createTextNode("Afstand: "));
  const distance = document.createElement("select");
  distance.dataset.filterInput = "distance";
  const distanceOptions: Array<[string, number | null]> = [
    ["Alle", null], ["5 km", 5000], ["10 km", 10000],
    ["25 km", 25000], ["50 km", 50000],
  ];
  for (const [label, value] of distanceOptions) {
    const option = document.createElement("option");
    option.textContent = label;
    option.value = value == null ? "" : String(value);
    option.selected = value === opts.filter.maxDistanceM;
    distance.appendChild(option);
  }
  distance.addEventListener("change", () => {
    opts.filter = {
      ...opts.filter,
      maxDistanceM: distance.value ? Number(distance.value) : null,
    };
    opts.onFilterChange(opts.filter);
  });
  distanceLabel.appendChild(distance);
  bar.appendChild(distanceLabel);

  return bar;
}
