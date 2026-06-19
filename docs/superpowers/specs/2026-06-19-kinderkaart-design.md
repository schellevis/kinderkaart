# Kinderkaart — Ontwerpdocument

**Datum:** 2026-06-19
**Status:** Concept — kernkeuzes gemaakt, één benchmark-spike (zoekarchitectuur) staat
nog open als expliciet eerste werkpakket. Daarna implementatieklaar.
**Reviews verwerkt:** codex-review (`2026-06-19-kinderkaart-design-feedback.md`) +
onafhankelijke Opus-review.

## 1. Doel

Een statische web-app met kaartinterface die leuke dingen om te doen met kinderen
toont (speeltuinen, musea, dierentuinen/kinderboerderijen, zwembaden, speelparken,
kindvriendelijke restaurants), met uitgebreide zoek- en filtermogelijkheden.

**Kernprincipes:**
- **Zo statisch mogelijk** — primaire runtime is GitHub Pages.
- **Modulair bron-model** — een LLM/agent kan snel een nieuwe databron toevoegen.
- **Zware verwerking in GitHub Actions** (offline, gratis), niet in de browser of runtime.
- **Multi-country-proof** — Nederland eerst; andere landen via configuratie + bronnen.
- **Reproduceerbaar & auditbaar** — deterministische builds, traceerbare provenance.

## 2. Tech-stack

| Laag | Keuze | Status |
|---|---|---|
| Front-end / kaart | MapLibre GL + Vite + TypeScript | beslist |
| Browse-data | **PMTiles** (vector tiles, build-time clusters) + apart POI-detailrecord | beslist |
| Scrapers / pipeline | Python (uv, py3.13): osmium, pyproj, pydantic, httpx | beslist |
| Basemap | PDOK BRT (NL) — endpoint/format gepind in §10; landspecifiek | beslist |
| Zoeken | **Open: benchmark client-side static index vs Vercel-API** (§9) | **spike** |
| Restaurant-bron | Agent-gedreven, codespace-only, gecureerd met provenance (§8) | beslist |

## 3. Architectuur

```
sources/<bron>/  (manifest.yaml + adapter CLI)
        │  fetch → ruwe snapshot (met checksum) → normaliseer naar POI (NDJSON)
        ▼
GitHub Actions (één build-coördinator, concurrency-locked):
  merge/dedup (sterke sleutels + verklaarbare score) → canonieke POI-database
  → publicatie-artefacten met één gedeelde data_version:
      • PMTiles (browse: clusters per zoom + detailrecords)
      • zoekindex (vorm volgt uit §9-benchmark)
      • licentierapport (machineleesbaar + UI-weergave)
  → publish-gate (schema, aantallen, coördinaten, bron-aanwezigheid)
        │  alleen bij groen: atomair publiceren; anders last-known-good behouden
        ▼
GitHub Pages: web-app + PMTiles + (evt.) statische zoekindex  ── atomair, versiegebonden
(optioneel) Vercel: /api/search  ── alleen als de benchmark daarvoor kiest
```

Browse/filter draait op de statische PMTiles (CDN, gratis). Vrije-tekstzoeken via de
in §9 gekozen route. Web-app, browse-data en zoekindex komen uit **dezelfde build** en
delen één `data_version`.

## 4. Gedeeld POI-schema

Getypeerd (pydantic). Onbekend ≠ false; ontbrekende info is expliciet `null`.

```python
class Image:
    url: str
    source_page: str        # bv. Commons-bestandspagina
    author: str | None
    license: str            # bv. "CC-BY-SA-4.0"
    license_url: str

class POI:
    # Identiteit
    poi_id: str             # stabiele publieke sleutel van het samengevoegde object
    external_ids: dict      # {"osm": "...", "wikidata": "Q..", "rce": ".."}
    aliases: list[str]      # eerder gepubliceerde poi_id's (redirects voor deep-links)

    # Kern
    name: str
    categories: list[str]   # >1 toegestaan: playground | museum | zoo | petting_zoo
                            #                | pool | play_park | restaurant_kidfriendly
    lat: float; lon: float  # representatief punt (regel: zie §6)
    country: str            # ISO 3166-1 alpha-2, bv. "nl"
    address: dict | None    # straat, huisnr, postcode, plaats

    # Canonieke facetten (filterbaar) — alle optioneel, "onbekend" = null
    indoor: bool | None
    free: bool | None
    price_model: str | None         # free | paid | donation | mixed
    age_min: int | None; age_max: int | None
    accessibility: dict | None      # wheelchair, toilet, etc. (per veld true|false|null)
    opening_hours: str | None       # genormaliseerd (OSM opening_hours-syntax)

    # Media & links
    website: str | None
    images: list[Image]             # leeg in MVP (zie §11)

    # Provenance (per veld traceerbaar in field_provenance)
    sources: list[str]              # alle bijdragende bron-id's
    source_urls: dict               # bron-id → bron-URL
    field_provenance: dict          # veld → bron-id die de waarde leverde
    source_date: date | None        # wijzigingsdatum bij de bron, indien bekend
    fetched_at: datetime            # wanneer opgehaald
    build_version: str              # data_version van de build

    tags: dict                      # alleen long-tail/bron-specifiek; NIET voor MVP-filters
```

MVP-filtervelden (`indoor`, `free`, `age_*`, `categories`) zijn **getypeerde
contractvelden**, niet vrije `tags`. Elke adapter documenteert zijn mapping + datakwaliteit.

## 5. Het bron-contract (kern van LLM/agent-uitbreidbaarheid)

Elke bron = een map onder `sources/<id>/` met een manifest + een adapter.

**`manifest.yaml`** (gevalideerd tegen een JSON-schema):
```yaml
schema_version: 1
id: osm-playgrounds
name: OpenStreetMap speeltuinen
country: nl
endpoint: "https://download.geofabrik.de/europe/netherlands-latest.osm.pbf"
license: ODbL
license_url: "https://opendatacommons.org/licenses/odbl/1-0/"
attribution: "© OpenStreetMap contributors"
runtime: github-action            # of: codespace-only (handmatig)
update_frequency: weekly
expected_count: [25000, 40000]    # verwachte bandbreedte; build-gate gebruikt dit
contact_policy: "User-Agent met contact; honor 429/Retry-After"
category_map:
  "leisure=playground": [playground]
entrypoint: "adapter.py"
```

**Adapter = CLI**, niet één in-memory functie (testbaar, herstartbaar):
- `adapter.py snapshot`  → haalt op, schrijft ruwe snapshot + checksum naar `data/raw/`.
- `adapter.py normalize` → leest snapshot, **streamt genormaliseerde POI's als NDJSON**.

Zo zijn netwerkfouten, fixtures en retries los te testen. Timeouts, retries, backoff en
User-Agent staan centraal vastgelegd (gedeelde helper), niet per adapter herhaald.

## 6. Merge / dedup (toetsbaar model, geen vaste vuistregel)

1. **Sterke sleutels eerst:** gedeeld extern id, website-domein, telefoon, of exact adres → directe match.
2. **Daarna verklaarbare score** over naam-similarity, afstand, adres en categorie.
   Drempels en afstandsradius **per categorie** (klein voor speeltuinen, ruimer voor zoo/park).
3. **Normalisatie:** Unicode, lidwoorden, afkortingen, plaatsnamen, hoofdletters.
4. **Veld-merge** via veldspecifieke bron-prioriteit; conflictgedrag expliciet; resultaat vult `field_provenance`.
5. **Meerdere categorieën** waar inhoudelijk nodig (museum dat ook kinderboerderij is).
6. **Representatief punt:** voorkeur voor entree-node; anders centroid van geometrie.
7. **Deterministisch & idempotent:** zelfde input → zelfde output.
8. **`poi_id`-stabiliteit:** afgeleid van de hoogst-geprioriteerde bron-id; bij wisselende
   clustermembership behoudt het object zijn `poi_id` en schrijft de oude id naar `aliases`.
9. **Handmatige overrides:** versiebeheerd `overrides.yaml` voor geforceerde merges,
   geforceerde splits en veldcorrecties.
10. **Regressieset:** gelabelde echte merges én non-merges; golden tests in CI (§14).

## 7. Datapijplijn & publicatie

- **Opslagmodel:** ruwe snapshots als **workflow-cache/release-asset** (niet in Git →
  geen repogroei); genormaliseerde NDJSON + canonieke build-output als **release-asset**
  per `data_version`. De repo blijft klein; elke build is reproduceerbaar uit snapshot+checksum+adapterversie.
- **Atomische publicatie:** web-app + PMTiles als één versiegebonden Pages-artefact;
  zoekindex uit exact dezelfde build; alle responses/artefacten dragen `data_version`.
- **Publish-gate** (anders: behoud last-known-good): schemafouten, aantallen buiten
  `expected_count`, ongeldige coördinaten, of een ontbrekende verplichte bron blokkeren publicatie.
- **Verwijdering/veroudering:** een record dat uit de bron verdwijnt wordt na N builds
  uitgefaseerd; bij een gedeeltelijk mislukte scrape gebruikt de build de laatste goede snapshot van die bron.
- **Concurrency:** één build-coördinator; `concurrency`-group + locking voorkomt botsende deploys.
- **Cron-realiteit:** GitHub Actions `schedule` staat **statisch in workflow-YAML** — een
  cron-waarde in `manifest.yaml` genereert niet vanzelf een schedule. We kiezen één
  dispatcher-workflow die manifests leest en per bron `snapshot`/`normalize` draait
  (matrix), met `workflow_dispatch` voor `codespace-only` bronnen. Scheduled runs kunnen
  vertragen/overslaan → we monitoren **freshness** i.p.v. exacte uitvoering aan te nemen.

## 8. Databronnen (geverifieerd 2026-06-19)

### Tier 1 — in MVP

| Bron | Categorieën | Toegang | Licentie |
|---|---|---|---|
| **OpenStreetMap** | playground, petting_zoo, pool, play_park, long tail | Geofabrik `.pbf` + osmium (nightly/wekelijks) | ODbL |
| **Wikidata** | museum, zoo, play_park (+ website P856) | `curl` SPARQL per type | CC0 |
| **RCE "Musea in Nederland"** | museum (629, landelijk) | WFS GeoJSON; RD→WGS84 herprojecteren | CC0 |
| **Gemeente Den Haag / Eindhoven** | playground (toestellen/leeftijd) | Opendatasoft/ArcGIS export | CC-BY-4.0 |
| **museum.nl** | museum-verrijking (openingstijden/beschrijving) | scrape (codespace-only) | geen open licentie — zie §11 |
| **Agent-restaurantbron** | restaurant_kidfriendly | agents (codespace-only), gecureerd | zie §8.1 |
| **PDOK BRT** | basemap | OGC API | CC-BY-4.0 |

### 8.1 Agent-gedreven restaurantbron

Geen open dataset levert overtuigend "kindvriendelijke restaurants". We bouwen daarom
een `codespace-only` bron waarin **agents gericht zoeken** (web + OSM-signalen als
`kids_area=yes`, nabije `leisure=playground`, `highchair=yes`) en kandidaten **cureren**.
Eisen tegen ruis/hallucinatie:
- elke POI krijgt **harde bewijs-velden** (`evidence`: bron-URL's + welk signaal),
- alleen opnemen bij ≥1 verifieerbaar signaal; geen vrije "lijkt kindvriendelijk"-claim,
- output gaat door **dezelfde normalisatie + publish-gate** als elke andere bron,
- `runtime: codespace-only` → jij draait dit handmatig en kunt de output reviewen vóór publicatie.

### Tier 2 — NIET als primaire feed (vastgelegd voor later)

Commerciële aggregators zonder open licentie/API. EU/NL **databankenrecht** beschermt
substantiële extractie, ongeacht robots.txt. Voor later: expliciete toestemming /
datapartnerschap; bronvermelding beperkt risico maar heft het niet op.
- **uitmetkinderen.nl** (voorwaarden verbieden extractie — hoog risico), **dagjeweg.nl**
  (`ai-train=no`, 403 — hoog), **kidsproof.nl** (auteurs-/databankenrecht — midden-hoog).
- Mission-aligned alternatief: **Jantje Beton Buitenspeelkaart / Bureau Speelplan**,
  **Natuurmonumenten OERRR**, **Springzaad** (toestemming vragen i.p.v. scrapen).

## 9. Zoeken — benchmark-spike (eerste werkpakket)

Voor ~40k punten is een serverless API niet bewezen nodig. **Eerste werkpakket = spike**
die twee routes meet en vastlegt:

- **A) Statische client-side index** (FlexSearch/MiniSearch, evt. gesharded per regio,
  op GitHub Pages): gratis, privacyvriendelijk (geen zoektekst naar derden), geen extra stack.
- **B) Vercel-API** (Hobby): server-side index. Let op: 250 MB is de **ongecomprimeerde
  Node-bundle inclusief runtime** — geen doelgrootte; echte risico = cold-start
  rehydratie/geheugen binnen de timeout.

**Meetcriteria:** indexgrootte, initiële/cold laadtijd, query-latency (p50/p95),
geheugen op een beoogde mobiel, privacy, kosten. Keuze valt na meting.

**Als A wint:** vorm + sharding-strategie + `data_version`-koppeling vastleggen.
**Als B wint, specificeer:** request/response-schema, normalisatie, ranking,
typo-tolerantie, geo-ranking, filters, resultaatlimiet, CORS, invoerlimieten, gedrag bij
lege/onbekende query, exacte cache-key + headers, `data_version`-coördinatie tussen
web/browse/index, en het concrete deploymentmechanisme (geen vaag "push naar Vercel").

**Fallback-eerlijkheid:** "zoek alleen in geladen tegels" is géén volwaardige zoek
(alleen huidige kaartomgeving). We leveren ofwel een statische client-index als echte
fallback, ofwel benoemen dit expliciet in de UI als beperkte offline-modus.

## 10. Front-end (MapLibre GL + Vite + TS)

- Vector-kaart met clusters uit PMTiles; categorie-iconen; PDOK BRT basemap
  (endpoint/format gepind; custom MapLibre-style indien nodig).
- **Filterpaneel** op de getypeerde facetten (categorie, indoor/outdoor, gratis,
  leeftijd, afstand). **Onbekend toont niet als negatief** (geen `null`→`false`).
- **Browse = statische PMTiles** (CDN, gratis). **Zoeken** via §9-route.
- **Afstand** wordt gemeten vanaf een expliciete referentie: (1) apparaatlocatie na
  toestemming, anders (2) kaartmiddelpunt, of (3) gezochte plaats. Toestemmingsstatus en
  een alternatief zonder geolocatie zijn onderdeel van de UI.
- **Deep-links:** view (`lat/lon/z`) **én** geselecteerde `poi_id` (via `aliases`
  redirect-bestendig) **én** actieve query + filters — volledig deelbaar.
- **Attributie:** zichtbaar op de kaart ("© OpenStreetMap contributors" + CC-BY-bronnen),
  gegenereerd uit het licentierapport.
- **Sanitisatie:** alle bronvelden worden geschoond vóór weergave; links alleen met
  toegestane protocollen (http/https). Brondata = onbetrouwbare invoer.

## 11. Licentie & juridisch (conservatief, uitvoerbaar)

- **Per bron in het manifest:** licentie, licentie-URL, vereiste creditline, bewijsdatum,
  herpublicatievoorwaarden. De build genereert hieruit een **machineleesbaar
  licentierapport** + de zichtbare UI-attributie.
- **Gepubliceerde POI-database = ODbL** (eenvoudigste verdedigbare positie voor de
  OSM-afgeleide combinatie); per-bron CC-BY-attributies blijven behouden in `source_urls`.
- **museum.nl:** geen open hergebruik-licentie; opgenomen als bewuste eigenaarskeuze met
  bronvermelding (museum.nl publiceert namens musea die bezoek willen). Draait
  `codespace-only`; risico expliciet vastgelegd. *Geen juridisch advies.*
- **Afbeeldingen:** Wikidata-velden zijn CC0, maar een Commons-afbeelding (P18) heeft een
  **eigen licentie per bestand** (vaak maker-/licentievermelding). Daarom is `image: str`
  onvoldoende → het `Image`-type (§4) draagt maker, bronpagina, licentie, licentie-URL.
  **MVP publiceert geen afbeeldingen** (`images: []`); we activeren ze pas met correcte
  per-bestand-attributie.
- Eindcombinatie ODbL + concrete CC-BY-bronnen juridisch laten toetsen.

## 12. Multi-country (voorbereid, niet "gratis")

Niet "tweede land zonder wijziging", wél met een expliciete **landenconfiguratie**:
basemap + style, default-view, locale, tijdzone, beschikbare categorieën, bronlicenties,
zoekpartitie. `country` = ISO 3166-1 alpha-2. **Taal is geen eigenschap van het land**
(apart i18n-systeem). PDOK/RCE/gemeentebronnen zijn NL-specifiek en dus vervangbaar per land.

## 13. MVP-scope

- **Categorieën:** playground, museum, zoo, petting_zoo, **pool** en **play_park**
  (gesplitst), restaurant_kidfriendly (agent-gecureerd).
- **Land:** `nl`.
- **Bronnen:** OSM, Wikidata, RCE, Den Haag + Eindhoven, museum.nl (codespace-only),
  agent-restaurantbron (codespace-only), PDOK basemap.
- **Eerste werkpakket:** de zoek-benchmark-spike (§9).
- **Eindresultaat:** statische kaart op GitHub Pages, browse/filter op PMTiles + zoeken
  via de gekozen route, gevoed door een reproduceerbare GitHub-Actions-pijplijn met
  publish-gate en last-known-good.

## 14. Kwaliteit, tests & beheer

- **Determinisme:** GitHub Actions + toolversies gepind; checksums vastgelegd.
- **Tests:** contracttests per adapter; golden tests voor merge/overrides (incl. de
  regressieset uit §6); attributie-output-test; PMTiles tegelgrens-/clustertests.
- **Data-asserts (niet alleen "niet leeg"):** aantallen binnen band, unieke `poi_id`'s,
  geografische grenzen, categorie-percentages, maximale artefactgrootte.
- **Performancebudgetten (browse):** initiële bytes, time-to-first-points, pan-respons,
  piekgeheugen op een beoogde mobiel — vastgelegd en in CI bewaakt.
- **Toegankelijkheid:** mobiele bediening, toetsenbord, screenreader, kleurcontrast,
  `prefers-reduced-motion` — in acceptatiecriteria.
- **Observability:** bronstatus + `last_updated` per bron in de UI; pipelinefouten en
  freshness gerapporteerd.
- **Privacy:** vrije zoektekst gaat alleen naar een server als route B (Vercel) wint;
  apparaatlocatie bij voorkeur niet verzonden; geen analytics zonder expliciete opt-in.
