# Herbeoordeling Kinderkaart — Ontwerpdocument

**Datum:** 2026-06-19  
**Beoordeeld document:** `2026-06-19-kinderkaart-design.md`  
**Advies:** de twee spikes kunnen starten nadat de onderstaande P0-contractproblemen
zijn gecorrigeerd; front-end- en pipeline-implementatie blijven terecht geblokkeerd op
de spike-uitkomsten.

## Samenvatting

Vrijwel alle eerdere feedback is inhoudelijk verwerkt. Het ontwerp heeft nu expliciete
facetten met een onbekende toestand, aparte `SourcePOI`- en `CanonicalPOI`-modellen, een
verklaarbaar dedupmodel, een identity registry, versiegebonden artefacten, een publish-gate,
een zoekspike met beslisregel, een landenconfiguratie en concrete eisen voor
toegankelijkheid, privacy en beheer.

Er blijft één fundamenteel probleem vóór de spikes over: PMTiles met clustering over alleen
geladen/in-viewport features is nog geen aangetoond correct clustermodel. Daarnaast moeten
de meetfixture, provenance op recordniveau, publicatie, identity-transities en het bewust
geaccepteerde `museum.nl`-risico scherper worden afgebakend.

## P0 — vóór uitvoering van de spikes corrigeren

### 1. Behandel het PMTiles-clustermodel als hypothese, niet als besluit

De stacktabel noemt “ongeclusterde PMTiles + client-side clustering” beslist, terwijl
§9b de technische haalbaarheid en zelfs een alternatief nog moet bepalen. Zet deze keuze
tot na spike 2 op **hypothese / te valideren**.

De spike moet meer toetsen dan performance:

- MapLibre bevraagt bij een vectorbron alleen de momenteel geladen tegels; features
  buiten de viewport ontbreken en door tile buffering kunnen resultaten dubbel
  voorkomen. Een Supercluster-index over dat resultaat is dus geen samenhangende
  landelijke dataset. Zonder expliciete buffer, deduplicatie en update-algoritme worden
  clusters aan viewportranden afgekapt en kunnen aantallen bij klein pannen veranderen.
- MVT-properties zijn scalair (`string`, getal of boolean), niet `list` of `null`.
  `categories: list[str]` en de onbekende toestand van facetten hebben daarom een
  expliciete tile-encoding nodig, inclusief bijbehorende MapLibre-filterexpressies.
- Leg vast op welk tegelzoomniveau features worden gelezen, dat de tiler geen punten
  dropt, hoe world-wrap en tilebuffer-duplicaten op `poi_id` worden verwijderd en wanneer
  de clusterindex bij pan, zoom en filterwijziging opnieuw wordt gebouwd.

Vergelijk in de spike ten minste: (a) een volledige of regionaal gesharde clientindex
van punten, (b) PMTiles met een expliciete gebufferde tile-decodeerroute, en pas bij
falen daarvan (c) viewportaggregatie buiten de client. Voeg een correctness-oracle toe:
voor vaste viewports en filtercombinaties moeten de getoonde `poi_id`'s, clusteraantallen
en clusterleden overeenkomen met clustering over de canonieke dataset. De officiële
[MapLibre-documentatie voor `querySourceFeatures`](https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/#querysourcefeatures)
benoemt de geladen-tegelgrens en mogelijke duplicaten; de
[MVT 2.1-specificatie](https://github.com/mapbox/vector-tile-spec/tree/master/2.1)
definieert de toegestane propertytypen.

### 2. Maak de spike-fixture en meetmethode uitvoerbaar

§9 noemt “de echte NL-POI's uit Plannen 1–3”, maar de spikes zijn juist de eerste
werkpakketten en de pipelineplannen volgen pas daarna. Benoem welk minimaal
fixture-/bootstrapwerk de representatieve merged dataset oplevert, en pin die invoer met
checksum zodat beide alternatieven exact dezelfde data meten.

“Startwaarden, te bevestigen” zijn nog geen vooraf vastgelegde acceptatiegrenzen. Bevries
vóór elke meting:

- dataset en relevante verdeling van categorieën/facetten;
- apparaat, browser, netwerkprofiel en testlocatie;
- koude versus warme HTTP- en applicatiecache;
- aantal runs en berekening van p95;
- meetpunt voor eerste-load, eerste zoekactie, first-points en detail-fetch.

Met name `detail-fetch < 150 ms p95` moet zeggen of dit een warme cachemeting is; als
koude netwerkmeting is de uitkomst voornamelijk hostingafstand en netwerkprofiel. Voeg
naast snelheid de correctness-tests uit punt 1 als harde acceptatiegrens toe.

## P0 — vóór publieke MVP-publicatie oplossen

### 3. Maak het publicatieprotocol passend bij de gekozen host

§7 schrijft exacte `Cache-Control`-headers en een “manifest als laatste stap”-switch
voor, maar beschrijft niet hoe een GitHub Pages-deployment die afzonderlijke stap en
headers uitvoert. Evenmin staat vast hoe oude versiepaden beschikbaar blijven wanneer
een nieuw Pages-artefact wordt gedeployed.

Kies en documenteer daarom concreet:

1. waar PMTiles, detailshards, zoekindex en manifest werkelijk worden gehost;
2. of die host HTTP Range requests voor PMTiles en, indien cross-origin, correcte CORS
   ondersteunt;
3. welke cacheheaders de host feitelijk levert en hoe een manifestrefresh wordt getest;
4. de transactie: immutable artefacten uploaden, checksums/leesbaarheid verifiëren en pas
   daarna het manifest publiceren;
5. rollback, minimale retentie van oude `data_version`s en garbage collection.

Retentie hoort ook de reproduceerbaarheidsclaim te respecteren: snapshot-GC mag geen
input verwijderen waarnaar een behouden of gepubliceerde build verwijst. Houd rekening
met de officiële [GitHub Pages-limiet van 1 GB per gepubliceerde site](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
wanneer meerdere volledige dataversies in één Pages-deployment blijven staan.

### 4. Haal `museum.nl` uit de publieke MVP of maak toestemming een release-gate

De eerdere licentiebevinding is niet opgelost maar als eigenaarsrisico geaccepteerd.
`codespace-only` beperkt de uitvoeromgeving; het geeft geen recht om de geëxtraheerde
data opnieuw te publiceren. Dat botst met het eigen kernprincipe “conservatief,
uitvoerbaar” en met een publiek herbruikbare database.

De verdedigbare ontwerpkeuze is één van beide:

- `museum.nl` niet opnemen in publieke artefacten totdat schriftelijke toestemming of
  een passende licentie is vastgelegd; of
- die toestemming/licentie als harde release-gate vastleggen.

Maak de externe juridische toets voor de ODbL/CC-BY-combinatie eveneens een expliciete
go/no-go vóór brede publicatie, niet alleen een actie-item zonder beslismoment. Dit is
geen juridisch advies.

## P1 — opnemen in spike-output of implementatieplan

### 5. Maak canonieke provenance herleidbaar tot het bronrecord

De tweefasensplitsing in §4 is correct, maar `CanonicalPOI.field_provenance` wijst nog
alleen naar een `source_id`. Eén bron kan meerdere records bijdragen of meerdere records
kunnen tijdens dedup in één POI belanden. Gebruik daarom minimaal
`(source_id, source_record_id)` als provenance-reference. Definieer voor geneste en
meervoudige velden de granulariteit, bijvoorbeeld JSON Pointer per subveld en provenance
per lijstitem.

Ook `source_urls: source_id → URL`, één canonieke `source_date` en één `fetched_at` verliezen
informatie zodra meerdere records of snapshots van dezelfde bron bijdragen. Maak dit een
lijst van bronrecord-references met URL en snapshotmetadata, en definieer afzonderlijk hoe
een eventueel samenvattend `last_updated` voor de UI wordt afgeleid.

### 6. Definieer identity-transities en de autoritatieve registry-opslag

`aliases` lost een merge op wanneer één overlevende `poi_id` wordt gekozen, maar niet
automatisch een split: één oude deep-link kan niet zonder ambiguïteit naar meerdere nieuwe
POI's redirecten. Leg een transition table vast voor merge, split, verwijdering en later
herstel. Bijvoorbeeld: bij merge één deterministische survivor; bij split behoudt één
object de oude id en krijgen andere objecten nieuwe ids, of de oude id wordt een tombstone
met expliciet ambigu gedrag.

Kies daarnaast één autoritatieve opslag voor de registry. “Gecommit/als release-asset”
zijn verschillende state- en transactie­modellen. Beschrijf single-writer locking,
wanneer de registry wordt bijgewerkt, rollback bij een mislukte publicatie en hoe een
nieuwe build gegarandeerd de laatst gepubliceerde registry leest.

### 7. Maak de detailsharding deterministisch én begrensd

Een geohash-prefix is alleen uit `poi_id` niet afleidbaar; hash-modulo wel, maar garandeert
niet vanzelf zowel maximaal circa 300 POI's als maximaal 50 KB gzip. De spike-output moet
één lookupcontract geven: shardfunctie en versie, eventuele sharddirectory, gedrag bij
groeiende buckets en een build-gate op zowel recordaantal als bytes. Een deep-link moet
een detailrecord kunnen vinden zonder eerst de bijbehorende kaarttegel te laden.

### 8. Versterk het bewijscontract voor restaurants

“Minstens één verifieerbaar signaal” is te zwak als een nabijgelegen speeltuin zelfstandig
voldoende kan zijn om een restaurant `restaurant_kidfriendly` te noemen. Onderscheid
direct bewijs (restaurant noemt kindermenu, speelhoek, kinderstoel of vergelijkbare
voorziening) van indirecte context. Vereis ten minste één direct signaal, of publiceer een
neutralere categorie/score waarbij de UI exact toont welk bewijs beschikbaar is. Pin ook
bewijsdatum en het specifieke bronrecord; alleen een URL is later niet auditbaar.

## Conclusie

De eerdere brede herziening hoeft niet opnieuw. Maak spike 2 expliciet een correctness- én
performancevergelijking en pin voor beide spikes eerst de dataset en meetmethode. Laat de
spikes vervolgens het zoek-, tile-, cluster- en detailcontract vastleggen. Pipeline- en
publicatie-implementatie kunnen pas groen worden nadat provenance, hosting/retentie,
identity-transities en de open juridische gates concreet zijn afgehandeld.
