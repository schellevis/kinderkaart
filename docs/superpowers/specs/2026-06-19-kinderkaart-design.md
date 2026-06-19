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
| Browse-data | **Hypothese:** PMTiles met *ongeclusterde* punten + client-side clustering over gefilterde features (§9b) — of een (regionaal gesharde) client-puntindex | **hypothese — te valideren in spike 2 (correctness + perf)** |
| POI-detail | gesharde statische JSON, lazy per klik, immutable + cache (§9b) | **shard-/lookupcontract te bepalen in spike 2** |
| Data-hosting | Web-app op GitHub Pages; **data-artefacten (PMTiles/shards/index/manifest) als immutable GitHub Releases-assets** (Range + versieretentie, buiten 1 GB Pages-limiet) | **hypothese — Range/CORS te verifiëren in spike 2** |
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

class SourceRef:                     # één bijdragend bronrecord (na merge ≥1)
    source_id: str
    source_record_id: str
    source_url: str | None
    source_date: date | None
    fetched_at: datetime             # snapshot-tijd van dat record

class CanonicalPOI(FacetFields):
    poi_id: str                      # stabiele publieke sleutel (identity registry, §6)
    external_ids: dict               # {"osm": "...", "wikidata": "Q..", "rce": ".."}
    aliases: list[str]               # eerder gepubliceerde poi_id's (deep-link redirects)
    contributing: list[SourceRef]    # alle bijdragende bronrecords (URL + snapshotmetadata)
    field_provenance: dict           # veld(-JSON-Pointer) → (source_id, source_record_id);
                                     # per lijstitem traceerbaar
    last_updated: date | None        # UI-samenvatting, afgeleid uit contributing (regel in §6)
    build_version: str               # data_version van de build
```

`field_provenance` verwijst naar **`(source_id, source_record_id)`**, niet alleen een bron;
voor geneste/meervoudige velden geldt JSON-Pointer-granulariteit per subveld/lijstitem. `contributing`
vervangt het verliesgevende `source_urls/source_date/fetched_at` zodra meerdere records of
snapshots van dezelfde bron bijdragen.

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
   niet genoeg: een stabiele publieke `poi_id` vereist **historische state**.
   - **Eén autoritatieve opslag:** de registry is een **gecommit bestand in de repo**
     (`data/<land>/identity.json`) — single source of truth, single-writer. De build-coördinator
     (§7) is de enige schrijver (concurrency-lock); een nieuwe build leest gegarandeerd de
     laatst gepubliceerde registry (uit de default branch), en commit de bijgewerkte registry
     **in dezelfde atomische publicatie**; bij een mislukte publish wordt de registry-commit
     teruggerold (geen half-bijgewerkte state).
   - **Transitietabel (deterministisch):**
     - *nieuw object* → mint nieuw `poi_id`.
     - *match* (overlappende `external_ids` met precies één bestaand object) → hergebruik dat `poi_id`.
     - *merge* (≥2 oude objecten → 1) → kies één **deterministische survivor** (hoogste bron-prioriteit,
       tie-break op laagste oude `poi_id`); de overige oude id's worden `aliases` van de survivor.
     - *split* (1 oud → ≥2 nieuw) → **één** nieuw object behoudt de oude `poi_id` (deterministische regel:
       grootste `external_ids`-overlap, tie-break geografisch); de andere krijgen nieuwe id's. Kan de
       eigenaar niet eenduidig kiezen, dan wordt de oude id een **tombstone** met expliciet "ambigu"-gedrag
       (deep-link toont een keuzepagina i.p.v. te raden).
     - *verwijdering* → `poi_id` wordt tombstone (na N builds), nooit hergebruikt voor een ander object.
   - Registry is append-only voor aliases/tombstones; een `poi_id` wijst nooit naar een ander fysiek object.
9. **Provenance-regel:** elk gemerged veld registreert `(source_id, source_record_id)` in
   `field_provenance`; `last_updated` (UI) = max `source_date` (val terug op `fetched_at`) over `contributing`.
10. **Handmatige overrides:** versiebeheerd `overrides.yaml` voor geforceerde merges,
    geforceerde splits en veldcorrecties.
11. **Regressieset:** gelabelde echte merges én non-merges; golden tests in CI (§14).

## 7. Datapijplijn & publicatie

- **Opslagmodel + retentie:** ruwe snapshots als **immutable, gedateerde release-assets**
  (tag `snapshot-<bron>-<datum>`, niet in Git → geen repogroei). Retentiebeleid: bewaar de
  laatste *K* snapshots per bron + maandelijkse archieven; een **scheduled GC-workflow**
  ruimt oudere op. Builds refereren aan een snapshot via release-tag + checksum, zodat elke
  build reproduceerbaar/auditbaar is uit snapshot + checksum + adapterversie. **GC-invariant:**
  een snapshot of dataversie waarnaar een behouden/gepubliceerde build (of het huidige manifest)
  verwijst, wordt **nooit** opgeruimd — retentie respecteert de reproduceerbaarheidsclaim.
- **Hosting (passend bij de host — hypothese, te verifiëren in spike 2):** GitHub Pages kan
  **geen per-bestand `Cache-Control` zetten**, vervangt bij elke deploy de hele site, en kent
  een **1 GB-limiet** — ongeschikt om meerdere immutable dataversies vast te houden. Daarom:
  - **Web-app** (HTML/JS/CSS) → **GitHub Pages**.
  - **Data-artefacten** (`tiles.pmtiles`, `detail/<shard>.json`, `search-index.*`) →
    **immutable GitHub Releases-assets** per `data_version` (tag `data-<land>-<data_version>`):
    ondersteunen **HTTP Range** (nodig voor PMTiles), zijn onveranderlijk, vallen buiten de
    1 GB Pages-limiet en geven gratis versieretentie. **Te verifiëren in de spike:** Range +
    cross-origin **CORS** op release-asset-URL's; lukt dat niet → fallback Vercel static of
    Cloudflare R2 (custom headers + CORS + Range).
  - **`manifest.json`** (klein: `land → data_version + absolute artefact-URL's`) → op **Pages**,
    met de korte cache die Pages levert; client haalt eerst het manifest, daarna de
    (immutable) release-assets.
- **Atomische publicatie (transactie):** (1) upload alle immutable artefacten naar de nieuwe
  release; (2) **verifieer** checksums + leesbaarheid (incl. een Range-request-smoketest);
  (3) pas dán publiceer je het nieuwe `manifest.json` op Pages (de switch). Een client met een
  oud manifest blijft geldige oude release-assets gebruiken; versies wijzigen nooit in-place.
  **Rollback** = manifest terugzetten naar de vorige `data_version` (assets staan er nog).
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
- **Direct vs. indirect bewijs:** *direct* = het restaurant noemt zelf een kindervoorziening
  (kindermenu, speelhoek, kinderstoel, verschoontafel). *Indirect* = context (nabije speeltuin).
  **Vereist ≥1 direct signaal** om `restaurant_kidfriendly` te tonen; indirecte context is
  hooguit aanvullend, nooit op zichzelf voldoende.
- elke POI krijgt **harde bewijs-velden** (`evidence`: lijst van `{signaal-type,
  direct: bool, bron-record-id, bron-URL, bewijsdatum}`) — een URL alleen is later niet auditbaar,
- de UI toont **exact welk bewijs** beschikbaar is (transparant; geen kale "kindvriendelijk"-claim),
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
zonder beslisregel levert alleen meetwaarden.

**Meetdataset (bootstrap — de spikes zijn de éérste werkpakketten, dus de pipelineplannen
bestaan nog niet):** we bouwen een minimale bootstrap met de al beschikbare adapters
(Wikidata-museums uit Plan 1) aangevuld met een **éénmalige OSM-extract** (osmium op de
Geofabrik-`.pbf` voor playground/zoo/pool) tot een representatieve NL-set (~40–60k punten met
realistische categorie-/facetverdeling). Deze meetdataset wordt **gepind met checksum** en als
fixture-asset bewaard, zodat beide alternatieven **exact dezelfde data** meten.

**Meetmethode bevriezen vóór elke meting:** dataset + categorie-/facetverdeling; apparaat,
browser, netwerkprofiel en testlocatie; **koude vs. warme** HTTP- en applicatiecache (expliciet
per meetpunt); aantal runs + p95-berekening; en het exacte meetpunt voor eerste-load, eerste
zoekactie en (in §9b) first-points en detail-fetch. Pas met dit alles bevroren vergelijken we twee routes:

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

**Dit is een hypothese, geen besluit.** De spike toetst *correctness vóór performance*.
Bekende valkuilen die de spike expliciet moet oplossen:
- **Viewport-grens:** MapLibre's `querySourceFeatures` ziet alleen **geladen tegels** —
  features buiten de viewport ontbreken en tile-buffer kan features **dubbel** opleveren. Een
  Supercluster-index over dát resultaat is geen samenhangende landelijke dataset; clusters aan
  viewportranden worden afgekapt en aantallen kunnen bij klein pannen veranderen.
- **MVT-properties zijn scalair** (string/getal/boolean) — **geen `list` of `null`**.
  `categories: list[str]` en de "onbekend"-toestand van facetten vereisen een **expliciete
  tile-encoding** (bv. bitmask/CSV-string + sentinelwaarde) **plus** bijbehorende MapLibre-
  filterexpressies. Leg die encoding vast.
- **Vast te leggen:** tegelzoomniveau waarop features worden gelezen; bewijs dat de tiler geen
  punten dropt; world-wrap + buffer-duplicaten dedupliceren op `poi_id`; en **wanneer** de
  clusterindex herbouwt (pan / zoom / filterwijziging).

**Te vergelijken alternatieven (minimaal drie):** (a) een **volledige of regionaal gesharde
client-puntindex** (filter + Supercluster over de héle dataset, niet alleen viewport);
(b) **PMTiles met een expliciete gebufferde tile-decodeerroute** (dedup op `poi_id`); en bij
falen (c) **viewport-aggregatie buiten de client**.

**Correctness-oracle (harde acceptatiegrens):** voor een set vaste viewports × filtercombinaties
moeten de getoonde `poi_id`'s, clusteraantallen én clusterleden **exact overeenkomen** met
clustering over de canonieke dataset. Faalt dit → het alternatief valt af, ongeacht snelheid.

**POI-detail — begrensd, deterministisch lookupcontract (spike-output):**
detail (beschrijving, openingstijden, adres, images, provenance) zit **niet** in de tiles maar
in **gesharde statische JSON**. De spike levert één contract: **shardfunctie + versie**
(deterministisch uit `poi_id`, bv. hash-modulo) + optionele shard-directory voor lookup, met een
**build-gate op zowel recordaantal (≤ ~300) als bytes (≤ ~50 KB gz)** en gedrag bij groeiende
buckets (re-shard/split). Een **deep-link moet een detailrecord vinden zonder eerst de
bijbehorende kaarttegel te laden** (lookup via directory/manifest, niet via de tile).

**Vooraf vastgelegde acceptatiegrenzen (startwaarden, te bevestigen) op NL-schaal (~40–60k punten),
náást de correctness-oracle:** time-to-first-points < 2 s (mid-range mobiel, "fast 3G", **koude**
cache); pan/zoom-respons < 100 ms (**warme** index); initiële browse-transfer < 2 MB gz;
piekgeheugen < 250 MB; detail-fetch < 150 ms p95 (**koud**, dus inclusief hostingafstand —
expliciet als koude netwerkmeting genoteerd). **Beslisregel:** een alternatief is alleen kandidaat
als het de **correctness-oracle** haalt; daarna wint het alternatief dat alle perf-grenzen haalt.
Geen enkel alternatief groen → model bijstellen en opnieuw meten. Dit blokkeert het front-end-plan
tot er een correct én gemeten contract ligt (zoomniveaus, tile-encoding, dedup, herbouw-triggers,
shard-/lookupcontract, hosting).

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
- **museum.nl:** geen open hergebruik-licentie; `codespace-only` beperkt alleen de
  uitvoeromgeving, niet het recht om de geëxtraheerde data te **herpubliceren**. Daarom: museum.nl
  zit **niet in publieke artefacten** totdat er schriftelijke toestemming of een passende licentie
  is — dat is een **harde release-gate**, geen los actie-item. De build levert zonder museum.nl een
  geldige publicatie (verwijderbaar gehouden). *Geen juridisch advies.*
- **Afbeeldingen:** Wikidata-velden zijn CC0, maar een Commons-afbeelding (P18) heeft een
  **eigen licentie per bestand** (vaak maker-/licentievermelding). Daarom is `image: str`
  onvoldoende → het `Image`-type (§4) draagt maker, bronpagina, licentie, licentie-URL.
  **MVP publiceert geen afbeeldingen** (`images: []`); we activeren ze pas met correcte
  per-bestand-attributie.
- Eindcombinatie ODbL + concrete CC-BY-bronnen juridisch laten toetsen.
- **Juridische go/no-go-gates vóór brede publicatie (geen losse actie-items):**
  (1) externe juridische toets van de gecombineerde ODbL + CC-BY-database = expliciet
  **go/no-go**; (2) museum.nl in publieke artefacten = **geblokkeerd** tot schriftelijke
  toestemming/licentie (release-gate, zie boven). De publieke MVP mag uitrollen zonder museum.nl;
  de combinatie-toets moet "go" zijn vóór brede publicatie.

## 12. Multi-country (voorbereid, niet "gratis")

Niet "tweede land zonder wijziging", wél met een expliciete **landenconfiguratie**:
basemap + style, default-view, locale, tijdzone, beschikbare categorieën, bronlicenties,
zoekpartitie. `country` = ISO 3166-1 alpha-2. **Taal is geen eigenschap van het land**
(apart i18n-systeem). PDOK/RCE/gemeentebronnen zijn NL-specifiek en dus vervangbaar per land.

## 13. MVP-scope

- **Categorieën:** playground, museum, zoo, petting_zoo, **pool** en **play_park**
  (gesplitst), restaurant_kidfriendly (agent-gecureerd).
- **Land:** `nl`.
- **Bronnen:** OSM, Wikidata, RCE, Den Haag + Eindhoven, agent-restaurantbron (codespace-only),
  PDOK basemap. **museum.nl staat klaar maar blijft uit publieke artefacten** tot toestemming
  (release-gate, §11).
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
