# Kinderkaart — Ontwerpdocument

**Datum:** 2026-06-19
**Status:** Goedgekeurd ontwerp (klaar voor implementatieplan)

## 1. Doel

Een web-app met kaartinterface die leuke dingen om te doen met kinderen toont
(speeltuinen, musea, dierentuinen/kinderboerderijen, zwembaden/speelparken,
kindvriendelijke restaurants). Met uitgebreide zoek- en filtermogelijkheden.

**Kernprincipes:**
- **Zo statisch mogelijk** — deploybaar naar GitHub Pages.
- **Modulair bron-model** — een LLM kan snel een nieuwe databron toevoegen.
- **Zware verwerking in GitHub Actions** (gratis, offline) — niet in de browser, niet runtime.
- **Multi-country-proof** — Nederland eerst, andere landen later zonder herbouw.
- **Vercel Hobby (free tier)** — alleen voor vrije-tekstzoeken, agressief gecachet.

## 2. Architectuur in één oogopslag

```
sources/ (bron-modules)  ──┐
                           ▼
GitHub Actions (cron + handmatig):
  fetch elke bron → normaliseer naar gedeeld POI-schema
  → merge/dedup (naam + geo) → bouw artefacten:
      • statische tegel-JSON (browse, gratis via GitHub Pages CDN)
      • compacte zoekindex (voor Vercel-API)
                           │
        ┌──────────────────┼───────────────────────┐
        ▼                  ▼                         ▼
GitHub Pages          GitHub Pages              Vercel (Hobby)
 • web-app (MapLibre)  • tegel-JSON (ODbL)        • /api/search
                                                   (alleen vrije tekst,
                                                    edge-gecachet)
```

**Browse/filter = statisch** (voorgebakken tegel-JSON van GitHub Pages, kost
niets). **Vrije-tekst zoeken** → Vercel-functie, met fallback naar client-side
filteren als de API faalt of een limiet raakt.

## 3. Tech-stack (beslist)

| Laag | Keuze | Reden |
|---|---|---|
| Front-end / kaart | **MapLibre GL + Vite + TypeScript** | Vector-kaart, soepele clustering van duizenden punten, eigen styling, snelle static build |
| Scrapers / pipeline | **Python** | Past bij bestaande repo (uv, py3.13); sterk ecosysteem (osmium, pyproj, pydantic, httpx) |
| Zoek-API | **Vercel serverless (TypeScript), Hobby** | Krachtigste zoekfunctie; index meegebundeld; agressieve edge-caching |
| Basemap-tegels | **PDOK BRT Achtergrondkaart** (CC-BY-4.0) | Landelijke, stabiele NL-basemap |

## 4. Repo-structuur (monorepo)

```
kinderkaart/
├── sources/                      # bron-modules — hier voegt de LLM nieuwe bronnen toe
│   ├── _template/                # kopieerbaar startpunt (manifest.yaml + fetch.py)
│   ├── osm/                      # Geofabrik .pbf + osmium (alle OSM-categorieën)
│   ├── wikidata-attractions/     # SPARQL: musea, dieren-/pretparken
│   ├── rce-musea/                # RCE "Musea in Nederland" WFS
│   ├── gemeente-denhaag/         # Opendatasoft speeltuinen
│   ├── gemeente-eindhoven/
│   └── museum-nl/                # museum.nl verrijkingslaag (evalueren of het toevoegt)
├── data-pipeline/
│   ├── schema.py                 # gedeeld POI-schema (pydantic)
│   ├── normalize.py              # helpers (RD→WGS84 reprojectie, naam-normalisatie)
│   ├── merge.py                  # dedup op naam+geo, veld-merge, bron-prioriteit
│   └── build.py                  # → tegel-JSON + zoekindex (per land)
├── data/
│   └── nl/                       # build-output per land (multi-country)
│       ├── tiles/                # voorgebakken browse-JSON
│       └── search-index/         # input voor de Vercel-functie
├── api/
│   └── search.ts                 # Vercel serverless zoekfunctie
├── web/                          # MapLibre + Vite + TS front-end
└── .github/workflows/            # cron-scrapers + build/deploy
```

De `data/<land>/`-partitie en het `country`-veld per bron maken multi-country
later puur een kwestie van nieuwe bron-modules + landselector in de UI.

## 5. Het bron-contract (kern van LLM-uitbreidbaarheid)

Elke bron = een map onder `sources/` met:

**`manifest.yaml`** (declaratief, leesbaar voor mens én LLM):
```yaml
id: osm-playgrounds
name: OpenStreetMap speeltuinen
country: nl
license: ODbL              # bepaalt tonen + attributie + share-alike
attribution: "© OpenStreetMap contributors"
runtime: github-action     # of: codespace-only (handmatig)
schedule: "0 3 * * 1"      # cron; leeg = handmatig (workflow_dispatch)
category_map:              # bron-tags/types → onze categorieën
  "leisure=playground": playground
output: poi
```

**`fetch.py`** — implementeert `def fetch() -> list[POI]`. Vrij in implementatie
(osmium op .pbf, SPARQL, WFS-GeoJSON, Opendatasoft-export, HTTP-scrape).

**Gedeeld POI-schema** (`data-pipeline/schema.py`, pydantic):
```python
class POI:
    id: str              # stabiel, deterministisch (bron + bron-id)
    name: str
    category: str        # playground | museum | zoo | pool | restaurant | ...
    lat: float; lon: float
    country: str         # "nl"
    tags: dict           # vrije eigenschappen (indoor, leeftijd, gratis, openingstijden, ...)
    sources: list[str]   # herkomst (na merge meerdere)
    source_urls: dict    # bron → url (attributie + "meer info")
    image: str | None    # bv. Wikidata P18
    website: str | None
    updated: date
```

**Categorieën** zijn taal-onafhankelijke keys; vertaalde labels in de UI
(multi-country / i18n-proof).

## 6. Merge / dedup

`merge.py` voegt kandidaten samen die:
- dezelfde `category` hebben, **én**
- binnen ~50 m van elkaar liggen, **én**
- een vergelijkbare (genormaliseerde) naam hebben.

Velden worden aangevuld via **bron-prioriteit** (bv. OSM-geometrie + Wikidata
website/foto + RCE adres + museum.nl openingstijden). Resultaat: één POI met
`sources: [osm, wikidata, rce]`. Alle bronnen blijven traceerbaar voor attributie.

## 7. Databronnen (geverifieerd 2026-06-19)

### Tier 1 — juridisch schoon, in MVP

| Bron | Categorieën | Toegang | Licentie |
|---|---|---|---|
| **OpenStreetMap** | speeltuinen (~32.780), kinderboerderijen (`tourism=zoo`+`zoo=petting_zoo`), zwembaden (`leisure=sports_centre`+`sport=swimming`, filter privé), indoor-speel, long tail | Nachtelijke **Geofabrik `netherlands-latest.osm.pbf` + `osmium tags-filter`/`export`** in CI (reproduceerbaarder dan live Overpass) | ODbL |
| **Wikidata** | musea, dieren-/pretparken (mét website P856 + foto P18) | `curl` SPARQL per type (`wdt:P31/wdt:P279*`, `wdt:P17 wd:Q55`, coords P625) | **CC0** |
| **RCE "Musea in Nederland"** | 629 musea, landelijk gezaghebbend | WFS GeoJSON; **RD (EPSG:28992) → WGS84 herprojecteren** (of `srsName=EPSG:4326`) | **CC0** |
| **Gemeente Den Haag** | speeltuinen + toestellen/ondergrond/foto | Opendatasoft GeoJSON-export-URL | CC-BY-4.0 |
| **Gemeente Eindhoven** | speelplekken/toestellen | Opendatasoft GeoJSON/CSV + ArcGIS REST | CC-BY-4.0 |
| **museum.nl** | musea-verrijking (openingstijden, beschrijving, kindvriendelijkheid?) | scrape (JSON-LD); **evalueren of het iets toevoegt** bovenop RCE+Wikidata | geen open licentie — zie §10 |
| **PDOK BRT** | basemap-tegels | OGC API | CC-BY-4.0 |

Later uitbreidbaar (zelfde patroon): Gemeente Arnhem (ArcGIS, rijke attributen),
Amsterdam (`maps.amsterdam.nl/open_geodata`), Rotterdam/Utrecht (verifiëren).

### Tier 2 — NIET als primaire feed (vastgelegd voor later)

Commerciële, redactionele aggregators zonder open licentie/API. Naast
auteursrecht beschermt het **EU/NL databankenrecht** substantiële extractie,
**ongeacht robots.txt**. Voor later: overweeg per bron expliciete toestemming /
datapartnerschap; bronvermelding beperkt het risico maar heft het niet op.
- **uitmetkinderen.nl** — beste dataset (3000+, leeftijdsfilters), maar voorwaarden verbieden automatische extractie. Hoog risico.
- **dagjeweg.nl** — 403 voor bots, `ai-train=no`. Hoog risico.
- **kidsproof.nl** — permissieve robots + JSON-LD, maar auteurs-/databankenrecht. Midden-hoog.
- Mission-aligned alternatief (de moeite waard i.p.v. scrapen): datapartnerschap met **Jantje Beton Buitenspeelkaart / Bureau Speelplan**, **Natuurmonumenten OERRR Speelnatuur**, **Springzaad**.

### Ondersteunende lagen (later)
- **PDOK BAG** (publiek domein) — geocoding.
- **CBS "Nabijheid voorzieningen"** (CC-BY-4.0) — aggregaat per buurt (choropleth-context, geen punten).

## 8. Datapijplijn & GitHub Actions

- **`scrape-<bron>.yml`** — cron per bron (uit `manifest.schedule`); draait
  `fetch()`, commit genormaliseerde data terug (of als release-artefact).
- **`osm-refresh.yml`** — wekelijkse Geofabrik-pull + osmium-filter.
- **`build-deploy.yml`** — merge + build (tegel-JSON + zoekindex), deploy `web/`
  naar GitHub Pages, push index naar Vercel.
- **Codespace-only bronnen** — `workflow_dispatch` (handmatig) voor scrapes met
  IP-/rate-limits of die niet in CI horen (bv. museum.nl).

## 9. Front-end (MapLibre GL + Vite + TS)

- Vector-kaart met **clustering**, categorie-iconen, PDOK BRT basemap.
- **Filterpaneel:** categorie, eigenschappen (indoor/outdoor, gratis, leeftijd), afstand.
- **Browse = statisch:** bij pan/zoom laadt voorgebakken tegel-JSON van GitHub Pages.
- **Vrije-tekst zoeken** → Vercel `/api/search`.
- **Deep-links** (`?cat=museum&lat=..&lon=..&z=..`) om een view te delen.
- **Attributie** zichtbaar op de kaart: "© OpenStreetMap contributors" + CC-BY-bronnen (gemeenten, PDOK).

## 10. Zoek-API (Vercel Hobby — zuinig)

- Eén functie `/api/search`, leest een **compacte vooraf gebouwde index**
  (meegebundeld, < ~250 MB bundle-limiet) — MiniSearch/FlexSearch-serialisatie
  of klein SQLite-FTS-bestand.
- **Caching:** `Cache-Control: s-maxage=86400, stale-while-revalidate` → identieke
  query's komen van Vercel's edge (geen function-invocation). Blijft binnen free tier.
- **Graceful degradation:** API faalt/limiet → app valt terug op client-side
  filteren van geladen tegels. App blijft werken.

## 11. Licentie & juridisch (beslist)

- **Gepubliceerde datalaag (tegel-JSON) = ODbL** (share-alike) + zichtbare
  "© OpenStreetMap contributors". Vereist omdat we OSM-afgeleide data als bestand
  publiceren. CC0-bronnen (Wikidata, RCE) vereisen niets; CC-BY-bronnen (gemeenten,
  PDOK) vereisen attributie — opgenomen in de UI.
- **museum.nl:** geen open hergebruik-licentie; databankenrecht is van toepassing.
  Bewuste keuze van de eigenaar om het op te nemen (museum.nl publiceert namens de
  musea, die bezoek willen). Opgenomen als verrijkingsbron mét bronvermelding;
  risico vastgelegd. Draaien via `codespace-only` indien gewenst.

## 12. Multi-country (voorbereid, later geactiveerd)

- Alles per `country` gepartitioneerd (data, tegels, index).
- Bron-modules dragen `country`; categorieën zijn keys met vertaalde labels.
- Tweede land = nieuwe bron-modules + landselector. Geen architectuurwijziging.

## 13. MVP-scope

**Categorieën:** speeltuinen, musea, dierentuinen/kinderboerderijen,
zwembaden/speelparken, kindvriendelijke restaurants.
**Land:** Nederland (`nl`).
**Bronnen MVP:** OSM, Wikidata, RCE, Den Haag + Eindhoven Opendatasoft, PDOK BRT
basemap; museum.nl ter evaluatie.
**Eindresultaat MVP:** werkende statische kaart op GitHub Pages met browse/filter
op voorgebakken data + vrije-tekstzoeken via Vercel, gevoed door een
GitHub-Actions-pijplijn die de bronnen periodiek ververst.

## 14. Testing (richting)

- **Schema/normalisatie:** unit-tests per `fetch()`-output tegen het POI-schema.
- **Merge/dedup:** tests met bekende overlappende punten (bv. een museum in OSM + RCE + Wikidata → 1 POI).
- **Build:** smoke-test dat tegel-JSON + index geldig en niet-leeg zijn.
- **Front-end:** basis e2e (kaart laadt, filter werkt, deep-link herstelt view) — Playwright beschikbaar.
