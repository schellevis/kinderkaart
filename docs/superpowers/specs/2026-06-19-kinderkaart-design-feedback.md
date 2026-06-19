# Feedback op Kinderkaart — Ontwerpdocument

**Datum:** 2026-06-19  
**Beoordeeld document:** `2026-06-19-kinderkaart-design.md`  
**Advies:** eerst herzien; daarna pas het implementatieplan maken

## Samenvatting

Het ontwerp heeft een goede hoofdrichting: statische distributie, verwerking buiten
de browser, een broncontract, traceerbare herkomst en degradatie bij uitval van de
zoek-API. De afbakening van risicovolle commerciële bronnen is eveneens nuttig.

Het document is alleen nog niet implementatieklaar. De precieze distributievorm van
de POI-data, de licentiestrategie, stabiele identiteit en deduplicatie, de lifecycle
van buildartefacten, de zoekarchitectuur en een aantal MVP-definities zijn nog open
of onderling tegenstrijdig. Deze beslissingen beïnvloeden het dataschema, de
pipeline, de front-end en de deployment; ze horen dus vóór het implementatieplan in
het ontwerp te staan.

## Wat al sterk is

- De scheiding tussen bronadapters, normalisatie, merge en publicatie is helder.
- Bronherkomst blijft na een merge beschikbaar; dat is nodig voor debugging en
  attributie.
- GitHub Pages als primaire runtime beperkt kosten en operationele complexiteit.
- Deterministische verwerking van een Geofabrik-snapshot is beter reproduceerbaar
  dan afhankelijkheid van live Overpass-queries.
- Taalonafhankelijke categoriekeys en landpartities zijn een nuttige basis.
- Graceful degradation, schema-validatie en end-to-endtests zijn al als eisen
  herkend.

## Blokkerende punten (P0)

### 1. Kies en specificeer één publicatieformaat voor POI's

“Tegel-JSON” is geen voldoende technisch contract. Het ontwerp specificeert niet:

- of dit GeoJSON, vector tiles of een eigen JSON-formaat is;
- de URL- en zoomstructuur, compressie en cacheheaders;
- hoe objecten op tegelgrenzen worden behandeld;
- waar clustering plaatsvindt;
- hoe filters eigenschappen uit het formaat lezen.

Dit is relevant omdat MapLibre client-side clustering aanbiedt voor een
`GeoJSONSource`; losse GeoJSON-bestanden per tegel vormen niet automatisch één
clusterbare dataset. Vector tiles vragen daarentegen om build-time clustering of
een ander weergavemodel.

**Advies:** maak een korte benchmark en kies daarna expliciet één van deze twee
routes:

1. Voor de MVP één versiegebonden, gecomprimeerde GeoJSON-dataset per land, met
   MapLibre-clustering in de browser. Accepteer dit alleen als downloadgrootte,
   parse-tijd en geheugen op een beoogde mobiele telefoon binnen vooraf gekozen
   budgetten blijven.
2. Anders vector tiles in bijvoorbeeld PMTiles, met vooraf berekende clusters per
   zoomniveau en een apart detailrecord per POI.

Vermijd een eigen tiled-JSON-protocol tenzij een benchmark aantoont dat beide
standaardroutes tekortschieten. Leg ook performancebudgetten vast, bijvoorbeeld
voor initiële bytes, time-to-first-points, pan-respons en piekgeheugen.

### 2. Maak de licentiestrategie conservatief en uitvoerbaar

De zin “gepubliceerde datalaag = ODbL” bewijst nog niet dat alle ingevoegde
CC-BY-datasets onderling en met de gekozen databasepublicatie combineerbaar zijn.
Ook is één algemene kaartvermelding mogelijk onvoldoende voor brongebonden
attributie. Per bron moeten licentie-URL, vereiste creditline, bewijsdatum en
herpublicatievoorwaarden in het manifest staan. De build moet daaruit een
machineleesbaar licentierapport en een zichtbare UI-weergave genereren.

Twee concrete problemen moeten worden gecorrigeerd:

- `museum.nl` heeft volgens het ontwerp geen open hergebruiklicentie. Veronderstelde
  intentie van musea is geen toestemming. `codespace-only` verandert alleen waar de
  extractie draait en neemt het herpublicatierisico niet weg. Sluit deze bron uit de
  MVP totdat schriftelijke toestemming of een passende licentie is vastgelegd.
- Wikidata-eigenschappen zijn CC0, maar een P18-afbeelding op Wikimedia Commons heeft
  een eigen licentie en vaak maker-/licentievermelding. `image: str` is daarom niet
  genoeg. Voeg per afbeelding maker, bronpagina, licentie en licentie-URL toe, of
  publiceer in de MVP geen afbeeldingen.

De officiële [OSMF-attributierichtlijn](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines)
vereist onder meer zichtbare herkomst en toegang tot licentie-informatie. De
[Wikimedia Commons-hergebruikhandleiding](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia)
bevestigt dat de voorwaarden per bestand verschillen. Laat de uiteindelijke
combinatie van ODbL en de concrete CC-BY-bronnen juridisch toetsen; deze review is
geen juridisch advies.

### 3. Definieer stabiele identiteit vóór deduplicatie

Het schema zegt dat `id` uit bron plus bron-id bestaat, terwijl de merge één POI uit
meerdere bronnen maakt. Het is daardoor niet duidelijk welk id het resultaat krijgt.
Een wisselende id breekt deep-links, caches en handmatige correcties.

**Advies:** onderscheid minimaal:

- `source_record_id`: stabiele sleutel binnen één bron;
- `poi_id`: stabiele publieke sleutel van het samengevoegde object;
- `external_ids`: OSM-, Wikidata-, RCE- en andere identifiers;
- `aliases` of redirects voor eerder gepubliceerde `poi_id`'s.

Leg vast hoe een `poi_id` behouden blijft wanneer een bron verdwijnt, een merge
splitst of een extra bron wordt toegevoegd. Voeg een versiebeheerbaar overridebestand
toe voor geforceerde merges, geforceerde splits en veldcorrecties.

### 4. Vervang de vaste dedupregel door een toetsbaar model

“Zelfde categorie + binnen circa 50 m + vergelijkbare naam” is niet deterministisch
genoeg en geeft voorspelbare fouten: locaties op hetzelfde terrein worden onterecht
samengevoegd, terwijl naamloze of anders gecategoriseerde duplicaten blijven staan.

Gebruik eerst sterke sleutels (gedeeld extern id, website, telefoon of exact adres)
en daarna een verklaarbare score op naam, afstand, adres en categorie. Drempels mogen
per categorie verschillen. Definieer daarnaast:

- normalisatie voor Unicode, lidwoorden, afkortingen en plaatsnamen;
- veldspecifieke bronprioriteit en conflictgedrag;
- ondersteuning voor meerdere categorieën waar dat inhoudelijk nodig is;
- een gelabelde regressieset met echte merges en non-merges;
- deterministische en idempotente output.

Een implementatieplan kan pas worden geschat nadat bekend is hoe goed de merge moet
zijn en hoe fouten worden hersteld.

### 5. Maak filtervelden onderdeel van het contract

Een vrije `tags: dict` maakt adapters makkelijk, maar verplaatst alle complexiteit
naar filters en UI. `indoor`, `gratis`, `leeftijd` en openingstijden zullen per bron
anders worden geïnterpreteerd. Ontbrekende informatie mag bovendien niet als `false`
worden behandeld.

Definieer getypeerde, canonieke facetten met ten minste een onbekende toestand. Denk
aan `indoor: true | false | null`, een prijsmodel, leeftijdsminimum/-maximum,
toegankelijkheid en gestandaardiseerde openingstijden. Bewaar bron-specifieke velden
apart. Leg per adapter de mapping en datakwaliteit vast.

Het schema mist daarnaast adres, oorspronkelijke en opgehaalde tijd, geometrie of de
regel voor een representatief punt, en veldniveau-provenance. `updated: date` is
onduidelijk: wijzigingsdatum bij de bron, ophaaldatum of builddatum.

### 6. Onderbouw de zoek-API en definieer haar contract

Voor de genoemde orde van grootte is nog niet aangetoond dat een serverless API
nodig is. Een compacte, statisch gehoste en eventueel gesharde clientindex kan
eenvoudiger, goedkoper en privacyvriendelijker zijn. Benchmark die optie tegen de
Vercel-route voordat Vercel als definitieve stackkeuze wordt vastgelegd.

Als Vercel blijft, specificeer dan:

- request- en response-schema, normalisatie, ranking, typo-tolerantie en geo-ranking;
- ondersteunde filters, resultaatlimiet, CORS en invoerlimieten;
- het gedrag bij een onbekende of lege query;
- de exacte cachekey en headers;
- één `data_version` voor web-app, browse-data en zoekindex;
- de concrete deployment: “push index naar Vercel” is nog geen mechanisme;
- cold-start-, geheugen-, bundlegrootte- en latencybudgetten.

De fallback “zoek alleen in geladen tegels” is functioneel niet gelijkwaardig: een
gebruiker vindt dan alleen locaties in de huidige kaartomgeving. Benoem dit als
beperkte offline zoekmodus in de UI, of lever een statische clientindex als echte
fallback.

De huidige Vercel-limiet van 250 MB geldt voor de ongecomprimeerde Node.js-function
bundle inclusief runtimebestanden; gebruik dit niet als doelgrootte. Zie de officiële
[function limits](https://vercel.com/docs/functions/limitations) en
[cache-control-documentatie](https://vercel.com/docs/caching/cache-control-headers).

## Belangrijke aanvullingen (P1)

### Datapijplijn en publicatie

- Kies tussen data in Git, release-assets of workflowartefacten. “Commit terug (of
  release-artefact)” laat een fundamentele keuze open. Grote, periodieke snapshots in
  Git veroorzaken blijvende repositorygroei; tijdelijke workflowartefacten zijn
  geen duurzame bron van waarheid.
- Publiceer web-app en browse-data atomair als één versiegebonden Pages-artefact.
  Deploy de zoekindex uit exact dezelfde build en laat responses de `data_version`
  teruggeven.
- Bewaar per bron de ruwe snapshot of ten minste URL/query, checksum, ophaaltijd en
  adapterversie, zodat een build reproduceerbaar en auditbaar is.
- Definieer verwijderingen en veroudering: wanneer verdwijnt een record dat niet meer
  in de bron staat, en wat gebeurt er na een gedeeltelijk mislukte scrape?
- Blokkeer publicatie bij schemafouten, onverwachte daling/stijging in aantallen,
  ongeldige coördinaten of een ontbrekende bron. Behoud de laatst bekende goede
  publicatie.
- Voorkom conflicterende commits of deployments van gelijktijdige workflows met
  `concurrency`, locking en één buildcoördinator.
- Een cronwaarde in `manifest.yaml` genereert niet vanzelf een GitHub Actions
  schedule; schedules staan statisch in workflow-YAML. Kies één vaste dispatcher of
  genereer en commit workflows bewust. Scheduled runs kunnen vertraagd of overgeslagen
  worden; ontwerp freshness-monitoring in plaats van exacte uitvoering te veronderstellen.
  Zie [GitHub Actions: `schedule`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

### Broncontract

Breid `manifest.yaml` uit met `schema_version`, bronendpoint, licentie-URL,
attributietekst, updatefrequentie, verwachte bandbreedte van recordaantallen,
contact/rate-limitbeleid en adapter-entrypoint. Valideer het manifest met een schema.

`fetch() -> list[POI]` koppelt ophalen en normaliseren en houdt alles in geheugen.
Een robuuster contract is een CLI die een bron-snapshot leest/schrijft en
genormaliseerde NDJSON streamt. Daardoor zijn netwerkfouten, fixtures en retries
apart te testen. Leg timeouts, retries, backoff en een herkenbare User-Agent centraal
vast.

### MVP-scope en productsemantiek

- Geen genoemde MVP-bron levert overtuigend “kindvriendelijke restaurants”. Definieer
  objectieve selectiecriteria en een bron, hernoem de categorie naar restaurants met
  bekende kindervoorzieningen, of haal haar uit de MVP.
- Splits `pool` en `play_park`; “zwembaden/speelparken” is geen eenduidige categorie.
- Definieer waar “afstand” vanaf wordt gemeten: apparaatlocatie, kaartmiddelpunt of
  gekozen plaats. Beschrijf toestemming, foutstatus en een alternatief zonder
  geolocatie.
- Definieer wat de UI toont bij onbekende prijs, leeftijd, openingstijden of
  kindvriendelijkheid. Toon ontbrekende gegevens niet als negatieve eigenschap.
- Voeg een POI-deep-link op stabiel `poi_id` toe; alleen kaartcoördinaten herstellen
  niet het geselecteerde resultaat.

### Multi-country

“Tweede land zonder architectuurwijziging” is te sterk. PDOK is Nederland-specifiek;
ook basemap, taal/locale, tijdzone, landsgrenzen, bronlicenties en zoekpartitie moeten
vervangbaar zijn. Introduceer een landenconfiguratie met basemap/style, default view,
locale, tijdzone en beschikbare categorieën. Gebruik een expliciete standaard zoals
ISO 3166-1 alpha-2 voor `country`, maar behandel taal niet als eigenschap van het land.

## Kwaliteits- en beheerpunten (P2)

- Sanitiseer alle bronvelden vóór weergave en sta voor links alleen verwachte
  protocollen toe; brondata is onbetrouwbare invoer.
- Pin GitHub Actions en toolversies, maak builds deterministisch en leg checksums vast.
- Voeg contracttests per adapter, golden tests voor merge/overrides, een test voor
  attributie-output en tegelgrens-/cluster-tests toe.
- Test niet alleen dat output “niet leeg” is, maar ook aantallen, unieke ids,
  geografische grenzen, categoriepercentages en maximale artefactgrootte.
- Neem mobiele bediening, toetsenbordgebruik, screenreaders, kleurcontrast en
  `prefers-reduced-motion` op in acceptatiecriteria.
- Publiceer bronstatus en `last_updated` in de UI; rapporteer pipelinefouten en
  freshness per bron.
- Leg privacy vast: vrije zoektekst gaat naar Vercel en apparaatlocatie bij voorkeur
  niet. Voeg geen analytics toe zonder expliciete keuze.

## Aanbevolen wijzigingen aan het ontwerp

Voer vóór het implementatieplan minimaal de volgende beslissingen door:

1. Zet de status terug naar **concept — open beslissingen**.
2. Kies via een benchmark GeoJSON óf vector tiles/PMTiles en beschrijf het volledige
   artefactcontract.
3. Sluit `museum.nl` zonder toestemming uit en ontwerp correcte afbeeldingslicenties.
4. Voeg canonieke facetten, stabiele ids, veldprovenance en licentiemetadata aan het
   bron- en POI-schema toe.
5. Specificeer dedupscoring, handmatige overrides en een regressiedataset.
6. Beslis op basis van een benchmark tussen statisch client-side zoeken en Vercel;
   beschrijf daarna API, caching en versiecoördinatie.
7. Kies één opslag- en publicatiemodel met atomische, reproduceerbare builds en
   last-known-good-gedrag.
8. Los de restaurantcategorie, afstandssemantiek en multi-country-basemap expliciet op.

Daarna is de architectuur voldoende begrensd om werkpakketten en acceptatiecriteria
te maken zonder tijdens implementatie terug te moeten naar fundamentele keuzes.
