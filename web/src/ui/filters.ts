/**
 * Category chips + toggle filters UI.
 */

import type { Filter } from "../lib/filter.js";

const CAT_LABELS: Record<string, string> = {
  playground: "Speeltuin",
  museum: "Museum",
  zoo: "Dierentuin",
  petting_zoo: "Kinderboerderij",
  pool: "Zwembad",
  play_park: "Speelpark",
  restaurant_kidfriendly: "Restaurant",
};

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

export interface FiltersOptions {
  categories: string[];
  filter: Filter;
  onFilterChange: (f: Filter) => void;
}

export function createFilterChips(opts: FiltersOptions): HTMLElement {
  const container = document.createElement("div");
  container.className = "chip-scroll";
  container.setAttribute("role", "group");
  container.setAttribute("aria-label", "Categorieën filteren");

  for (const cat of opts.categories) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.dataset.cat = cat;
    chip.setAttribute("type", "button");
    chip.setAttribute("aria-pressed", String(opts.filter.categories?.has(cat) ?? false));

    const dot = document.createElement("span");
    dot.className = "chip-dot";
    dot.style.background = CAT_COLORS[cat] ?? "#9E9E9E";
    dot.setAttribute("aria-hidden", "true");

    chip.appendChild(dot);
    chip.appendChild(document.createTextNode(
      (CAT_GLYPHS[cat] ? CAT_GLYPHS[cat] + " " : "") + (CAT_LABELS[cat] ?? cat)
    ));

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

  return container;
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
    { key: "indoor", label: "Binnen", icon: "🏠" },
    { key: "free", label: "Gratis", icon: "🆓" },
  ];

  for (const t of toggles) {
    const btn = document.createElement("button");
    btn.className = "toggle-btn";
    btn.setAttribute("type", "button");
    btn.setAttribute("aria-pressed", String(opts.filter[t.key] === true));
    btn.textContent = `${t.icon} ${t.label}`;

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
