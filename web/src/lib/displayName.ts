/**
 * Shared helper for resolving a human-readable display name from a POI name
 * and its categories.
 *
 * Raw source-record IDs like `node/4294671069`, `way/1313184818`, or
 * `overzichtmusea.222` must never reach the UI. This helper detects those
 * patterns and substitutes a category label instead.
 */

const CAT_LABELS: Record<string, string> = {
  playground: "Speeltuin",
  museum: "Museum",
  zoo: "Dierentuin",
  petting_zoo: "Kinderboerderij",
  pool: "Zwembad",
  play_park: "Speelpark",
  restaurant_kidfriendly: "Restaurant",
};

/** OSM element id: `node/123`, `way/123`, `relation/123` */
const OSM_ID_RE = /^(node|way|relation)\/\d+$/;
/** Source-record-id leak: `<source_id>.<numeric_id>` e.g. `overzichtmusea.222` */
const SOURCE_RECORD_ID_RE = /^[a-z0-9_]+\.\d+$/i;

/**
 * Returns the display name to use in the results list and detail panel.
 * Falls back to the category label (+ "(onbekend)") when the stored name is
 * empty or looks like a raw internal identifier.
 */
export function displayName(name: string, cats: string[]): string {
  if (!name || OSM_ID_RE.test(name) || SOURCE_RECORD_ID_RE.test(name)) {
    const label = cats.length > 0 ? (CAT_LABELS[cats[0]] ?? cats[0]) : "Locatie";
    return `${label} (onbekend)`;
  }
  return name;
}
