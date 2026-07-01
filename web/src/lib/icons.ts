/**
 * Inline SVG icon set — replaces emoji glyphs across the UI.
 * All icons are 24x24, sized to "1em" so they scale with the font-size of
 * their container the same way the emoji they replace did, and use
 * currentColor so existing per-category / per-state color logic still works.
 */

function svg(inner: string, filled = false): string {
  const paint = filled
    ? 'fill="currentColor" stroke="none"'
    : 'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
  return `<svg viewBox="0 0 24 24" width="1em" height="1em" ${paint} aria-hidden="true" focusable="false">${inner}</svg>`;
}

export const PIN_ICON = svg(
  '<path d="M12 22s8-7.58 8-13a8 8 0 1 0-16 0c0 5.42 8 13 8 13z"/><circle cx="12" cy="9" r="2.5"/>'
);

export const SEARCH_ICON = svg(
  '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>'
);

export const CLOSE_ICON = svg('<line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>');

const HEART_PATH =
  '<path d="M12 20.5s-7.5-4.6-10-9.3C.6 8 2 4.5 5.3 4A5 5 0 0 1 12 6.5 5 5 0 0 1 18.7 4C22 4.5 23.4 8 22 11.2 19.5 15.9 12 20.5 12 20.5z"/>';
export const HEART_OUTLINE_ICON = svg(HEART_PATH);
export const HEART_FILLED_ICON = svg(HEART_PATH, true);

export const HOME_ICON = svg('<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M9 20v-6h6v6"/>');

export const FREE_ICON = svg(
  '<path d="M20 12.5l-8.5 8.5a2 2 0 0 1-2.8 0L3 15.3a2 2 0 0 1 0-2.8L11.5 4H19a1 1 0 0 1 1 1v7.5z"/>' +
    '<circle cx="15.5" cy="8.5" r="1.4" fill="currentColor" stroke="none"/>'
);

export const MAP_ICON = svg(
  '<path d="M9 3 3 5v16l6-2 6 2 6-2V3l-6 2-6-2z"/><line x1="9" y1="3" x2="9" y2="19"/><line x1="15" y1="5" x2="15" y2="21"/>'
);

export const CATEGORY_ICONS: Record<string, string> = {
  playground: svg(
    '<line x1="4" y1="3" x2="4" y2="21"/><line x1="20" y1="3" x2="20" y2="21"/>' +
      '<line x1="4" y1="3" x2="20" y2="3"/><line x1="7" y1="3" x2="6" y2="15"/>' +
      '<line x1="17" y1="3" x2="18" y2="15"/><line x1="6" y1="15" x2="18" y2="15"/>'
  ),
  museum: svg(
    '<path d="M3 10l9-6 9 6"/><line x1="4" y1="10" x2="20" y2="10"/>' +
      '<line x1="5" y1="10" x2="5" y2="19"/><line x1="9" y1="10" x2="9" y2="19"/>' +
      '<line x1="15" y1="10" x2="15" y2="19"/><line x1="19" y1="10" x2="19" y2="19"/>' +
      '<line x1="3" y1="21" x2="21" y2="21"/>'
  ),
  zoo: svg(
    '<circle cx="12" cy="15" r="4"/><circle cx="6" cy="9" r="2"/><circle cx="18" cy="9" r="2"/>' +
      '<circle cx="9" cy="5.5" r="1.8"/><circle cx="15" cy="5.5" r="1.8"/>',
    true
  ),
  petting_zoo: svg(
    '<circle cx="12" cy="13" r="6"/><circle cx="6" cy="8" r="3"/><circle cx="18" cy="8" r="3"/>' +
      '<circle cx="9.5" cy="12" r="1" fill="currentColor" stroke="none"/>' +
      '<circle cx="14.5" cy="12" r="1" fill="currentColor" stroke="none"/>'
  ),
  pool: svg(
    '<path d="M2 8c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/>' +
      '<path d="M2 14c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/>' +
      '<path d="M2 20c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/>'
  ),
  play_park: svg('<circle cx="12" cy="9" r="6"/><line x1="12" y1="15" x2="12" y2="21"/>'),
  restaurant_kidfriendly: svg(
    '<line x1="6" y1="2" x2="6" y2="22"/><line x1="3" y1="2" x2="3" y2="8"/>' +
      '<line x1="9" y1="2" x2="9" y2="8"/><path d="M3 8c0 2 1.5 3 3 3s3-1 3-3"/>' +
      '<path d="M18 2c-2 0-3 2-3 5s1 3 3 3v12"/>'
  ),
};

export function categoryIcon(cats: string[]): string {
  for (const c of cats) {
    if (CATEGORY_ICONS[c]) return CATEGORY_ICONS[c];
  }
  return PIN_ICON;
}

/** Build an aria-hidden span containing a trusted inline SVG icon constant from this module. */
export function iconSpan(iconSvg: string, className?: string): HTMLSpanElement {
  const span = document.createElement("span");
  if (className) span.className = className;
  span.setAttribute("aria-hidden", "true");
  span.innerHTML = iconSvg;
  return span;
}
