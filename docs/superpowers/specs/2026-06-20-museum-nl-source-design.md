# museum.nl data source — design

**Date:** 2026-06-20
**Status:** approved (revised after inspecting real page HTML), ready for implementation plan
**Context:** Both spec §11 legal gates passed 2026-06-20 (ODbL combined-DB review = go;
museum.nl written permission secured). This unblocks building a `sources/museum_nl/` module.

## Purpose

Add museum.nl as a data source that enriches the canonical museum set (description, phone, website)
on top of museums already provided with coordinates by RCE and Wikidata. museum.nl covers ~400 NL
museums and overlaps heavily with the existing canonical museum set.

## Role in the two-phase model

museum.nl follows the same contract as every other source: its adapter emits `SourcePOI` records
with `categories=[museum]`. The existing geo-based matcher (`data_pipeline/matcher.py`) deduplicates
and merges these into existing `CanonicalPOI` museum entries. Enrichment therefore happens through
the normal merge — **no separate enrichment path, no schema/contract change to `SourcePOI`.**

## Acquisition: scrape detail pages, read JSON-LD

museum.nl is a Vue SPA; the listing/map is client-rendered. The reliable enumeration surface is the
sitemap. Each museum detail page (`/nl/<slug>`) embeds a **`<script type="application/ld+json">`
block of `@type: Museum`** containing structured fields — verified against the live
`anne-frank-huis` page:

```json
{"@context":"https://schema.org","@type":"Museum",
 "name":"Anne Frank Huis",
 "telephone":"020   55 67 105",
 "address":{"@type":"PostalAddress","streetAddress":"Westermarkt 20",
            "addressLocality":"Amsterdam","postalCode":"1016 DK","addressCountry":"NL"},
 "geo":{"@type":"GeoCoordinates","latitude":52.375083,"longitude":4.884031},
 "sameAs":"www.annefrank.org"}
```

So **coordinates are available directly** (`geo.latitude`/`geo.longitude`, WGS84) — no PDOK geocoding
and no RD→WGS84 conversion. The description comes from the page's `<meta name="description">` /
`og:description` tag. Opening hours live only in a fragile, partly JS-toggled HTML table and are
**out of scope for v1** (see below).

Invariant honored: **all network in `snapshot()`; `normalize()` is deterministic and network-free.**
`snapshot()` only fetches pages — there are no geocoding or secondary calls.

### `snapshot(output, *, client) -> SnapshotMetadata`

1. Fetch `https://www.museum.nl/sitemap.xml`; extract candidate detail slugs (`/nl/<slug>`).
2. Fetch each candidate detail page HTML via the `adapter_base` `http_get` retry/User-Agent helper.
3. Write the raw envelope as **NDJSON**, one record per page: `{slug, url, html}`. The raw HTML is the
   single auditable artifact; all parsing happens deterministically in `normalize()`.
4. Return `SnapshotMetadata` with `checksum = sha256` of the written bytes.

### `normalize(path, *, fetched_at) -> Iterator[SourcePOI]`

Read the NDJSON envelope and, per record, parse from `html` (stdlib only — `re` to pull the
`ld+json` script body and the meta description, `json.loads` to parse the block):

- **Filter:** skip the record unless the page has a JSON-LD block with `@type == "Museum"` (string or
  list membership) **and** a `geo` with numeric `latitude`/`longitude`. This drops the
  theme/region/campaign pages that share the `/nl/<slug>` sitemap pattern.
- `name` ← JSON-LD `name`; `lat`/`lon` ← `geo.latitude`/`geo.longitude`.
- `address` ← JSON-LD `PostalAddress` → `Address(street, housenumber, postcode, city)`. Split
  `streetAddress` into `street` + `housenumber` with a trailing-number regex; fall back to
  `street=streetAddress`, `housenumber=None` when no match.
- `website` ← JSON-LD `sameAs` (first entry if a list); prepend `https://` when it has no scheme;
  drop it if the result is not a valid http(s) URL.
- `phone` ← JSON-LD `telephone` (whitespace-collapsed) → `tags["phone"]`.
- `description` ← `<meta name="description">` (or `og:description`) → `tags["description"]`.
- `categories = [museum]` (derived from `MANIFEST.category_map`, never hard-coded).
- `field_provenance` set to `MANIFEST.id` for every populated field (`name`, `categories`, `lat`,
  `lon`, `country`, `address`, and `website`/`tags` when populated).

Identity: `source_record_id = f"museum-nl:{slug}"` (stable per place across runs; the slug never
changes for the same museum).

## Manifest (`sources/museum_nl/manifest.yaml`)

- `id: museum-nl`, package dir `museum_nl`, `country: nl`.
- `endpoint: "https://www.museum.nl/sitemap.xml"`.
- `runtime: codespace-only`, `update_frequency: manual`.
- `license`: not openly licensed; carried as a permission. `license_evidence_date: "2026-06-20"`,
  `republication_terms: "Used with written permission from Museumvereniging/museum.nl; not openly
  licensed."`, `attribution: "© Museumvereniging / museum.nl"`. `license_url` is validated as
  http(s) (`manifest.py`), so point it at the museum.nl terms page, e.g.
  `"https://www.museum.nl/nl/over-ons"` (confirm the exact terms URL when implementing).
- `category_map: {museum: [museum]}`.
- `expected_count: [300, 500]`.

## Dependencies

**None added.** Parsing uses the Python standard library (`re`, `json`) — JSON-LD is structured data,
so no HTML parser (e.g. BeautifulSoup) is needed once opening-hours scraping is deferred.

## Testing

`tests/test_museum_nl.py` drives `normalize()` against a fixture NDJSON envelope built from real
JSON-LD shapes (2–3 museum pages + 1 non-museum/theme page with no Museum JSON-LD). Assert: `name`,
`lat`/`lon`, and `address` map from JSON-LD; `phone` and `description` land in `tags`; `website` is
`https://`-normalized; the non-museum page is skipped; a Museum block without `geo` is skipped;
`source_record_id` is stable and slug-derived; `field_provenance` is set for every populated field.
`normalize()` is network-free so the test is fully deterministic. Pure JSON-LD/sitemap parsing
helpers (slug extraction, JSON-LD extraction) get their own focused unit tests. The manifest guard
test validates the manifest automatically.

## Out of scope

- **Opening hours** — only in a fragile, partly JS-rendered HTML table; deferred from v1 (would need
  an HTML parser and brittle selectors). Revisit if the enrichment proves needed.
- PDOK geocoding / address-based coordinate lookup (unnecessary — coordinates are in the JSON-LD).
- New `description`/`phone` schema fields and any web-client changes to surface them.
- Flipping `runtime` to `github-action` or triggering a public deploy (stays a manual human decision).
