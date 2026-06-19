# Kinderkaart — Ontwerpdocument

**Datum:** 2026-06-19
**Status:** Concept — kernkeuzes gemaakt. **Twee spikes** staan open als eerste
werkpakketten en moeten af zijn vóór de overige plannen implementatieklaar zijn:
(1) zoekarchitectuur (§9), (2) tegel-/filter-/cluster-/detail-model (§9b). Beide
draaien op representatieve data met **vooraf vastgelegde acceptatiegrenzen**.
**Reviews verwerkt:** codex-review (`2026-06-19-kinderkaart-design-feedback.md`) +
onafhankelijke Opus-review + derde review (clustering/identity/publicatie).

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
| Browse-data | **PMTiles met *ongeclusterde* punten** (facetten als attributen) + **client-side clustering over gefilterde features** (§9b) | beslist (perf te valideren in spike 2) |
| POI-detail | **gesharde statische JSON**, lazy per klik, immutable + cache (§9b) | beslist (shard-schema in spike 2) |
| Scrapers / pipeline | Python (uv, py3.13): osmium, pyproj, pydantic, httpx | beslist |
| Basemap | PDOK BRT-A — endpoint/style/fallback te verifiëren + pinnen in front-end-plan (§10); landspecifiek | te pinnen |
| Zoeken | **Open: benchmark client-side static index vs Vercel-API** (§9) | **spike 1** |
| Tegel/cluster/detail | **Validatie ongeclusterde PMTiles + client-cluster + lazy detail** (§9b) | **spike 2** |
| Restaurant-bron | Agent-gedreven, codespace-only, gecureerd met provenance (§8) | beslist |

## 3. Architectuur

```
sources/<bron>/  (manifest.yaml + adapter CLI)
        │  fetch → ruwe snapshot (met checksum) → normaliseer naar POI (NDJSON)
        ▼
GitHub Actions (één build-coördinator, concurrency-locked):
  merge/dedup (sterke sleutels + verklaarbare score) → canonieke POI-database
  → identity registry (§6) bewaart stabiele poi_id's + aliases over builds
  → publicatie-artefacten met één gedeelde data_version:
      • PMTiles: ongeclusterde punten + filter-attributen (geen build-time clusters)
      • gesharde POI-detail-JSON (lazy lookup)
      • zoekindex (vorm volgt uit §9-spike)
      • licentierapport (machineleesbaar + UI-weergave)
      • versie-manifest.json (country → data_version + artefact-URL's)
  → publish-gate (schema, aantallen, coördinaten, bron-aanwezigheid)
        │  alleen bij groen: atomair publiceren (manifest-switch als laatste stap);
        │  anders last-known-good behouden
        ▼
GitHub Pages: web-app + PMTiles + detail-shards + (evt.) zoekindex  ── immutable, versiegebonden
(optioneel) Vercel: /api/search  ── alleen als spike 1 daarvoor kiest
```

Browse draait op statische PMTiles (CDN, gratis); **filteren + clustering gebeurt
client-side over de gefilterde features** (§9b). Vrije-tekstzoeken via de in §9 gekozen
route. Web-app, browse-data, detail-shards en zoekindex komen uit **dezelfde build** en
delen één `data_version`, geactiveerd via één manifest-switch (§7).

## 4. Twee-fasen POI-schema (bron vs canoniek)

Getypeerd (pydantic, alle contractmodellen `extra="forbid"`). Onbekend ≠ false;
ontbrekende info is expliciet `null`. **Twee fasen, twee modellen** — de adapter-output
en de publicatie-output zijn semantisch verschillend en mogen niet hetzelfde type delen:

- **`SourcePOI`** — output van een adapter (één bron, vóór merge). Heeft een **eigen
  bronidentiteit** (`source_id`, `source_record_id`) en bronprovenance; **geen** publieke
  `poi_id`, `aliases` of `build_version`.
- **`CanonicalPOI`** — output van de merge/publicatie (§6). Heeft de stabiele publieke
  `poi_id`, `external_ids`, `aliases`, gemergde provenance en `build_version`.

```python
class FacetFields:                   # gedeelde, getypeerde domeinvelden
    name: str                        # niet-leeg
    categories: list[str]            # uniek, ⊆ vocabulary; ≥1
    lat: float; lon: float           # representatief punt (§6)
    country: str                     # ISO 3166-1 alpha-2, ⊆ ondersteunde landen (§12)
    address: Address | None
    indoor: bool | None
    free: bool | None
    price_model: Literal["free","paid","donation","mixed"] | None   # consistent met free
    age_min: int | None; age_max: int | None   # ≥0, age_min ≤ age_max
    accessibility: Accessibility | None         # per veld true|false|null
    opening_hours: str | None                   # OSM opening_hours-syntax
    website: str | None                         # alleen http/https
    images: list[Image]                         # leeg in MVP (§11); per-bestand licentie
    tags: dict                                  # long-tail/bron-specifiek; NIET voor MVP-filters

class SourcePOI(FacetFields):
    source_id: str                   # = manifest.id
    source_record_id: str            # stabiele sleutel binnen die bron
    source_url: str | None
    source_date: date | None
    fetched_at: datetime             # tz-aware, genormaliseerd naar UTC (= start van fetch)
    field_provenance: dict           # veld → source_id, voor álle daadwerkelijk geleverde velden

class CanonicalPOI(FacetFields):
    poi_id: str                      # stabiele publieke sleutel (identity registry, §6)
    external_ids: dict               # {"osm": "...", "wikidata": "Q..", "rce": ".."}
    aliases: list[str]               # eerder gepubliceerde poi_id's (deep-link redirects)
    sources: list[str]               # alle bijdragende source_id's (niet-leeg)
    source_urls: dict                # source_id → bron-URL
    field_provenance: dict           # veld → winnende source_id
    source_date: date | None
    fetched_at: datetime
    build_version: str               # data_version van de build
```

`Image` draagt per bestand `url, source_page, author|None, license, license_url` (§11).
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

**Adapter = CLI met een file/stream-contract** (testbaar, herstartbaar, schaalt naar een
1,3 GB `.pbf`):
- `adapter.py snapshot --output PATH` → downloadt **chunked naar disk** en schrijft een
  **sidecar `PATH.meta.json`** (snapshot-envelope): `source_id`, endpoint + query(-hash),
  `checksum` (sha256), `fetched_at` (start van fetch, UTC), adapter-/git-versie. De
  orchestratie bewaart dit als immutable release-asset (§7).
- `adapter.py normalize PATH [--fetched-at ISO]` → leest de snapshot **streamend**, neemt
  `fetched_at` uit de sidecar (of `--fetched-at`), en **streamt `SourcePOI` als NDJSON**.

Reproduceerbaar: dezelfde snapshot + metadata → byte-identieke NDJSON. Een adapter die om
formaatredenen de hele snapshot in geheugen houdt (bv. Wikidata-JSON) benoemt dat als
**adapterspecifieke** keuze, niet als eigenschap van het gedeelde contract. Netwerkfouten,
fixtures en retries zijn los te testen. Timeouts, retries (alleen retrybare statussen/
transportfouten), backoff, `Retry-After` (seconden én HTTP-date) en een niet-overschrijfbare
`User-Agent` staan centraal in een gedeelde helper met een injecteerbare client + sleep.

## 6. Merge / dedup (toetsbaar model, geen vaste vuistregel)

1. **Sterke sleutels eerst:** gedeeld extern id, website-domein, telefoon, of exact adres → directe match.
2. **Daarna verklaarbare score** over naam-similarity, afstand, adres en categorie.
   Drempels en afstandsradius **per categorie** (klein voor speeltuinen, ruimer voor zoo/park).
3. **Normalisatie:** Unicode, lidwoorden, afkortingen, plaatsnamen, hoofdletters.
4. **Veld-merge** via veldspecifieke bron-prioriteit; conflictgedrag expliciet; resultaat vult `field_provenance`.
5. **Meerdere categorieën** waar inhoudelijk nodig (museum dat ook kinderboerderij is).
6. **Representatief punt:** voorkeur voor entree-node; anders centroid van geometrie.
7. **Deterministisch & idempotent:** zelfde input → zelfde output.
8. **`poi_id`-stabiliteit via een persistente identity registry.** Determinisme alleen is
   niet genoeg: een stabiele publieke `poi_id` vereist **historische state**. We houden een
   **versiebeheerde identity registry** bij (bv. `data/<land>/identity.json` of een kleine
   SQLite, gecommit/als release-asset per build). De merge:
   - leest de vorige registry,
   - matcht een nieuw cluster op een bestaand `poi_id` via overlappende `external_ids`,
   - **hergebruikt** dat `poi_id` (ook als de samenstelling licht wijzigt),
   - **mint** een nieuw id alleen voor echt nieuwe objecten,
   - bij split/merge: nieuwe id(s) + oude id(s) als `aliases` (deep-link-redirects),
   - registry is append-only voor aliases; ids worden nooit hergebruikt voor een ander object.
9. **Handmatige overrides:** versiebeheerd `overrides.yaml` voor geforceerde merges,
   geforceerde splits en veldcorrecties.
10. **Regressieset:** gelabelde echte merges én non-merges; golden tests in CI (§14).

## 7. Datapijplijn & publicatie

- **Opslagmodel + retentie:** ruwe snapshots als **immutable, gedateerde release-assets**
  (tag `snapshot-<bron>-<datum>`, niet in Git → geen repogroei). Retentiebeleid: bewaar de
  laatste *K* snapshots per bron + maandelijkse archieven; een **scheduled GC-workflow**
  ruimt oudere op. Builds refereren aan een snapshot via release-tag + checksum, zodat elke
  build reproduceerbaar/auditbaar is uit snapshot + checksum + adapterversie.
- **Atomische publicatie (concreet):**
  - Artefacten staan onder een **per-versie pad**: `data/<land>/<data_version>/…`
    (`tiles.pmtiles`, `detail/<shard>.json`, `search-index.*`). Deze zijn **immutable** en
    content-gehasht → `Cache-Control: public, max-age=31536000, immutable`.
  - Eén klein **`manifest.json`** (top-level) mapt `land → huidige data_version + artefact-URL's`,
    geserveerd met `Cache-Control: no-cache` (of `max-age=60, stale-while-revalidate`).
  - **Switch = manifest.json als láátste stap updaten.** Een client met een oud manifest
    blijft geldige oude (nog aanwezige) artefacten gebruiken; na refetch van het manifest
    krijgt hij de nieuwe versie. Geen half-verouderde mix omdat versies nooit in-place wijzigen.
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

## 9. Spike 1 — Zoekarchitectuur (eerste werkpakket)

**Verplicht: representatieve data + vooraf vastgelegde acceptatiegrenzen.** Een spike
zonder beslisregel levert alleen meetwaarden. De spike draait op een **representatieve
merged dataset** (de echte NL-POI's uit Plannen 1–3), en we leggen de pass/fail-drempels
*vóór* het meten vast. Pas dan vergelijken we twee routes:

- **A) Statische client-side index** (FlexSearch/MiniSearch, evt. gesharded per regio,
  op GitHub Pages): gratis, privacyvriendelijk (geen zoektekst naar derden), geen extra stack.
- **B) Vercel-API** (Hobby): server-side index. Let op: 250 MB is de **ongecomprimeerde
  Node-bundle inclusief runtime** — geen doelgrootte; echte risico = cold-start
  rehydratie/geheugen binnen de timeout.

**Vooraf vastgelegde acceptatiegrenzen (concrete startwaarden, te bevestigen):**
query-latency p95 < 150 ms; eerste-load extra transfer voor zoeken < 1,5 MB gz; piek­geheugen
toename op een mid-range mobiel < 80 MB; (route B) p95 inclusief cold start < 800 ms; kosten
binnen free tier. **Beslisregel:** voldoet A aan alle grenzen → kies A (simpeler, gratis,
privacyvriendelijk). Anders → B, mits B alle grenzen haalt. Spike-output = pass/fail + keuze.

**Als A wint:** vorm + sharding-strategie + `data_version`-koppeling vastleggen.
**Als B wint, specificeer:** request/response-schema, normalisatie, ranking,
typo-tolerantie, geo-ranking, filters, resultaatlimiet, CORS, invoerlimieten, gedrag bij
lege/onbekende query, exacte cache-key + headers, `data_version`-coördinatie tussen
web/browse/index, en het concrete deploymentmechanisme (geen vaag "push naar Vercel").

**Fallback-eerlijkheid:** "zoek alleen in geladen tegels" is géén volwaardige zoek
(alleen huidige kaartomgeving). We leveren ofwel een statische client-index als echte
fallback, ofwel benoemen dit expliciet in de UI als beperkte offline-modus.

## 9b. Spike 2 — Tegel-, filter-, cluster- en detailmodel (eerste werkpakket)

**Het probleem (terecht door de review aangewezen):** build-time clusters kunnen niet
correct worden herberekend voor willekeurige combinaties van categorie, leeftijd, gratis,
indoor en afstand. Punten verbergen laat clusteraantallen/-geometrie op ongefilterde data
staan. Daarom: **geen build-time clusters.**

**Voorgesteld model (te valideren in deze spike):**
- **PMTiles bevat ongeclusterde punten**, elk met de filterbare facetten als tile-attributen
  (`categories`, `indoor`, `free`, `age_min`, `age_max`) + `poi_id` + minimale labelvelden.
- De client laadt **in-viewport** features uit PMTiles, **filtert client-side**, en draait
  **client-side clustering (supercluster)** over de *gefilterde* set. Clusteraantallen en
  -geometrie kloppen dus altijd met de actieve filters. Afstandsfilter relatief aan het
  referentiepunt (§10), client-side.
- **POI-detail** (beschrijving, openingstijden, adres, images, provenance) zit **niet** in de
  tiles maar in **gesharde statische JSON**: `detail/<shard>.json`, waarbij `shard` =
  deterministische bucket (bv. geohash-prefix of hash-modulo van `poi_id`). Lazy ophalen bij
  marker-klik, immutable + HTTP-gecachet. Shard-doel: ≤ ~300 POI's / ≤ ~50 KB gz per shard.

**Vooraf vastgelegde acceptatiegrenzen (startwaarden, te bevestigen) op NL-schaal (~40–60k punten):**
time-to-first-points < 2 s (mid-range mobiel, "fast 3G"); pan/zoom-respons < 100 ms;
initiële browse-transfer < 2 MB gz; piekgeheugen < 250 MB; detail-fetch < 150 ms p95.
**Beslisregel:** haalt het model alle grenzen → vastleggen als definitief tegelcontract
(zoomniveaus, attribuutset, shard-schema, lookup + cache). Zo niet → het model bijstellen
(bv. server-side viewport-aggregatie of zoom-afhankelijke vereenvoudiging) en opnieuw meten;
dit blokkeert het front-end-plan tot er een passend, gemeten contract ligt.

## 10. Front-end (MapLibre GL + Vite + TS)

- Ongeclusterde PMTiles-punten + **client-side clustering over gefilterde features** (§9b);
  categorie-iconen.
- **Basemap = PDOK BRT-A** (Achtergrondkaart). Exacte service (vector-tiles + style-JSON,
  met WMTS-raster als fallback) en style-versie worden **geverifieerd en gepind in het
  front-end-plan** (niet aannemen dat een endpoint stabiel is); attributie verplicht.
- **Filterpaneel** op de getypeerde facetten (categorie, indoor/outdoor, gratis,
  leeftijd, afstand). **Onbekend toont niet als negatief** (geen `null`→`false`).
- **Browse = statische PMTiles** (CDN, gratis); **detail lazy uit gesharde JSON** (§9b).
  **Zoeken** via §9-route.
- **Geolocatie + auto-centreren:** bij het laden vraagt de app via de browser
  (`navigator.geolocation`) toestemming voor de gebruikerslocatie. Bij toestemming
  **centreert de kaart automatisch** op de gebruiker (passende zoom) en plaatst een
  "jij hier"-marker; bij weigering/fout/onbeschikbaar valt de app terug op een default
  NL-view. Toestemming wordt niet geforceerd en kan later via een knop opnieuw worden
  aangevraagd. Locatie blijft client-side (privacy, §14) — niet naar een server gestuurd.
- **Afstand** wordt gemeten vanaf een expliciete referentie: (1) apparaatlocatie na
  toestemming, anders (2) kaartmiddelpunt, of (3) gezochte plaats. Toestemmingsstatus en
  een alternatief zonder geolocatie zijn onderdeel van de UI.
- **Mobile-first, responsive layout:** primair ontworpen voor mobiel (kaart full-screen,
  filters/resultaten in een bottom-sheet of overlay, touch-vriendelijke targets). Op
  **desktop extra overzicht**: kaart naast een persistent zijpaneel met de resultatenlijst
  + filters tegelijk zichtbaar. Eén codebase, breakpoint-gestuurd; geen aparte build.
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
- **Open projectrisico's (expliciet, nog niet opgelost):** (1) de juridische houdbaarheid
  van de gecombineerde ODbL-database mét CC-BY-bronnen vraagt een externe toets vóór brede
  publicatie; (2) museum.nl blijft zonder expliciete toestemming/licentie een risico — daarom
  geïsoleerd als `codespace-only` bron en **verwijderbaar** gehouden (de build moet zonder
  museum.nl een geldige publicatie opleveren). Beide staan als actie-items, niet als opgelost.

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
- **Eerste werkpakketten:** spike 1 (zoekarchitectuur, §9) + spike 2 (tegel-/cluster-/
  detailmodel, §9b), beide op representatieve data met vooraf vastgelegde acceptatiegrenzen.
  Pas na beide spikes zijn front-end en build-plan implementatieklaar.
- **Eindresultaat:** statische kaart op GitHub Pages, browse + client-side gefilterde
  clustering op PMTiles + lazy detail-shards + zoeken via de gekozen route, gevoed door een
  reproduceerbare GitHub-Actions-pijplijn met identity registry, publish-gate en last-known-good.

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
