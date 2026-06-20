# Feedback op Kinderkaart Data Foundation Implementation Plan

**Datum:** 2026-06-19  
**Beoordeeld document:** `2026-06-19-kinderkaart-data-foundation.md`  
**Advies:** eerst herzien; daarna uitvoeren

## Samenvatting

Het plan heeft een bruikbare taakindeling en maakt de eerste verticale slice klein
genoeg: schema, manifest, gedeelde adaptercode, één concrete bron en een template. De
fixtures en de expliciete teststappen maken het plan bovendien goed overdraagbaar aan
een uitvoerende agent.

De huidige versie legt echter een paar verkeerde fundamentele contracten vast. Met
name bronidentiteit versus canonieke identiteit, reproduceerbaarheid van
`fetched_at`, het volledig inlezen van snapshots en de loskoppeling tussen manifest en
adapter moeten vóór implementatie worden opgelost. Anders moeten volgende plannen
het fundament en alle adapters weer migreren. Ook claimt de self-review op enkele
punten meer specdekking dan daadwerkelijk is geleverd.

## Wat al sterk is

- De taken zijn klein, geordend op afhankelijkheid en voorzien van concrete
  bestandsnamen en acceptatiechecks.
- Netwerkophalen en normaliseren zijn conceptueel gescheiden; fixtures kunnen daardoor
  zonder live netwerk worden getest.
- Onbekende facetwaarden krijgen standaard `None` en categorieën en coördinaten worden
  aan de modelgrens gevalideerd.
- Eén centrale HTTP-helper en één NDJSON-writer voorkomen direct veel duplicatie.
- Een echte adapter plus een kopieerbare template is een goede manier om het
  broncontract vroeg te toetsen.

## Blokkerende punten (P0)

### 1. Scheid bronrecords van canonieke POI's

Het ontwerp definieert `poi_id` als stabiele publieke sleutel van het **samengevoegde**
object. Dit plan laat een nog niet samengevoegd Wikidata-record al
`poi_id="wikidata:Q..."` produceren en gebruikt hetzelfde `POI`-model vóór en na de
merge. Daarmee zijn de fasen semantisch niet meer te onderscheiden. Velden als
`aliases` en `build_version` horen bij canonieke/publicatie-output, terwijl een
bronrecord juist een expliciete `source_id` en `source_record_id` nodig heeft.

Kies vóór Task 1 een van deze contracten:

1. Maak een `SourcePOI`/`NormalizedPOI` voor adapteroutput met minimaal `source_id`,
   `source_record_id`, bronprovenance en zonder publieke `poi_id`; laat de merge later
   een `CanonicalPOI` produceren.
2. Definieer expliciet dat `poi_id` vóór de merge slechts een kandidaat-id is en voeg
   alsnog een afzonderlijke stabiele bronsleutel toe. Dit is minder typeveilig en dus
   niet de voorkeursroute.

Pas daarna de adapter-, NDJSON- en testinterfaces aan. Zonder dit onderscheid kan
Plan 3 geen stabiele identiteit implementeren zonder een contractbreuk.

### 2. Het CLI-contract is niet reproduceerbaar

Het doel belooft een reproduceerbare normalisatie. De Python-functie accepteert een
injecteerbare `fetched_at`, maar de CLI kan die waarde niet ontvangen. `run_cli()`
roept `normalize(raw)` aan, waarna de adapter de actuele tijd gebruikt. Dezelfde
snapshot levert op twee momenten dus verschillende NDJSON op.

Daarnaast wijkt het plan af van het snapshotcontract in ontwerp §5 en de
auditability-eisen in §7: `snapshot` schrijft alleen bytes naar stdout, zonder
checksum of metadata. Minimaal moeten `source_id`, endpoint/query, checksum,
`fetched_at` en adapter/git-versie naast de bytes worden vastgelegd. Maak de
orchestratie verantwoordelijk voor dit sidecar-manifest of definieer een expliciet
snapshot-envelope; de orchestratie kan het resultaat daarna als immutable
release-asset opslaan.

Voeg aan `normalize` een verplichte `--fetched-at` of `--snapshot-metadata` toe en test
dat twee runs met dezelfde snapshotmetadata byte-identieke output geven. Leg ook vast
of `fetched_at` het begin of einde van de fetch betekent.

### 3. Het gedeelde contract streamt niet en schaalt niet naar de volgende adapter

Hoewel het plan herhaaldelijk “streamt” zegt, doet `sys.stdin.buffer.read()` een
volledige read en vereist `normalize(raw: bytes)` dat de hele snapshot in geheugen
staat. `snapshot() -> bytes` en `resp.content` doen hetzelfde aan de downloadkant. Dat
is bij de geplande Geofabrik `.pbf`-adapter geen houdbaar contract.

Definieer nu een pad- of file-objectcontract, bijvoorbeeld:

```python
snapshot(output: BinaryIO) -> SnapshotMetadata
normalize(input: BinaryIO, *, fetched_at: datetime) -> Iterator[SourcePOI]
```

Een eenvoudiger CLI-variant met `snapshot --output PATH` en `normalize PATH` is ook
prima. Laat HTTP-downloads chunked naar disk schrijven en houd alleen de NDJSON-output
record-voor-record. Als Wikidata-JSON bewust volledig in geheugen blijft, benoem dat
dan als adapterspecifieke keuze en niet als eigenschap van het gedeelde contract.

### 4. Het manifest is geen werkelijke bron van waarheid

De Wikidata-adapter dupliceert `id`, endpoint, land en categorie uit het manifest als
Python-constanten. Het manifest wordt alleen door een losse guard geladen; de runtime
gebruikt het niet. Beide kunnen daardoor geldig zijn en toch onderling verschillen.

Laat de adapter zijn configuratie uit het naastgelegen manifest laden, of voeg
contracttests toe die alle gedupliceerde waarden exact vergelijken. De eerste optie is
robuuster. De guard moet daarnaast controleren dat:

- `schema_version` exact een ondersteunde versie is;
- `id` kebab-case en uniek is, en overeenkomt met de mapnaamconventie;
- `category_map` alleen bekende, niet-lege categorielijsten bevat;
- `expected_count` niet-negatief is en `min <= max` heeft;
- `entrypoint` bestaat, binnen de bronmap blijft en importeerbaar is;
- URL-velden geldige toegestane `http`/`https`-URL's zijn;
- de in ontwerp §11 vereiste licentiebewijsdatum en herpublicatievoorwaarden aanwezig
  en valide zijn;
- onbekende manifestvelden worden geweigerd in plaats van stil genegeerd.

Het ontwerp noemt bovendien expliciet een JSON-schema. Exporteer daarom het Pydantic-
schema als versiebeheerd JSON-schema, of wijzig het ontwerp zodat Pydantic-validatie
bewust het enige contract is.

## Belangrijke verbeteringen (P1)

### Maak het POI-schema werkelijk gelijk aan ontwerp §4

De interface zegt “fields per spec §4”, maar `tags` ontbreekt en `build_version` is
optioneel gemaakt. Dat laatste kan logisch zijn voor bronrecords, maar onderstreept
dat er twee fasemodellen nodig zijn. Verder zijn meerdere domeinregels nog niet
getypeerd:

- `price_model` moet een vaste enum/literal zijn en consistent zijn met `free`;
- `age_min` en `age_max` moeten niet-negatief zijn en `age_min <= age_max` volgen;
- `address` en `accessibility` verdienen eigen modellen; bij accessibility is per
  veld `true | false | null` vereist;
- `fetched_at` moet timezone-aware en bij voorkeur naar UTC genormaliseerd zijn;
- `country` valideert nu alleen twee kleine alfabetische Unicode-tekens; waarden als
  `zz` en `éé` voldoen syntactisch maar zijn geen ISO-landcode;
- namen, ids, licenties en bronlijsten moeten waar vereist niet-leeg zijn;
- dubbele categorieën moeten worden geweigerd of canoniek verwijderd;
- bron-URL's en afbeeldings-URL's moeten alleen toegestane protocollen accepteren;
- provenance-keys en source-ids moeten onderling consistent zijn.

Gebruik op alle contractmodellen `extra="forbid"`. De standaard van Pydantic negeert
onbekende velden, waardoor typfouten en schema-evolutie anders ongemerkt data laten
verdwijnen.

### Corrigeer de HTTP retry-semantiek

De helper heeft nu meerdere randgevallen:

- `backoff=0.0` veroorzaakt standaard directe retryloops;
- een HTTP-date in `Retry-After` kan niet met `float(...)` worden verwerkt;
- ook permanente 4xx-responses worden opnieuw geprobeerd;
- na de laatste mislukte poging wordt nog geslapen;
- bij uitsluitend 429-responses is `last_exc` leeg;
- aangeleverde headers kunnen de verplichte `User-Agent` overschrijven;
- `retries` betekent in de lus feitelijk totaal aantal pogingen, niet aantal retries.

Definieer retrybare statussen en transportfouten expliciet, ondersteun zowel seconden
als HTTP-date voor `Retry-After`, en injecteer een `httpx.Client` en sleep-functie.
Tests met `httpx.MockTransport` zijn representatiever dan het globaal monkeypatchen van
`httpx.get` en maken connection reuse mogelijk.

### Maak de Wikidata-normalisatie deterministisch per QID

De SPARQL-query kan meerdere rijen voor hetzelfde item opleveren, bijvoorbeeld bij
meerdere websites of coördinaten. De adapter emitteert dan dubbele ids en kiest niets
deterministisch. Leg vast hoe multivalues worden behandeld: consolideer per QID, kies
een waarde via een stabiele regel of modelleer meerdere waarden waar het schema dat
toelaat. `SELECT DISTINCT` alleen lost verschillende websitewaarden niet op.

Valideer ook het QID-formaat en definieer beleid voor een ongeldige binding: de hele
bron hard laten falen is verdedigbaar, records overslaan alleen met een machineleesbaar
foutenrapport. Breid `field_provenance` uit voor alle werkelijk geleverde velden, niet
alleen naam en coördinaten.

### Versterk de contract- en CLI-tests

De shellcheck met `| head -n 1` is handmatig, controleert niet alle output en kan een
foutstatus van het Python-proces maskeren. Maak hiervan een subprocess-test die
exitcode, stderr, aantal regels, JSON-parsebaarheid en de vaste `fetched_at` controleert.
Test ook `snapshot()` met een mocktransport zodat endpoint, query, headers en bytes
onder contract vallen.

Voeg verder tests toe voor uitgeputte retries, 5xx, permanente 4xx, beide vormen van
`Retry-After`, naïeve datetimes, extra velden, ongeldige manifestcategorieën,
omgekeerde count-banden, duplicate QIDs en een kapot entrypoint. Valideer ook de
`_template` zelf; de huidige guard sluit die juist uit. Draai vóór iedere commit de
volledige suite, niet alleen het nieuw toegevoegde testbestand.

### Leg de package- en id-conventie eenduidig vast

Het manifest vereist een kebab-case id (`wikidata-museums`), terwijl de importeerbare
Python-map een underscore gebruikt (`wikidata_museums`). De template zegt nu
`sources/<your-id>/`, wat bij letterlijk kopiëren een niet-importeerbare module kan
opleveren. Documenteer `manifest.id` versus `package_dir` en test de omzettingsregel,
of kies één naamvorm die voor beide werkt.

### Commit de lockfile

Task 1 specificeert minimale dependencyversies maar noemt `uv.lock` niet bij de files
of commit. Voeg `uv.lock` toe en verifieer met een locked install/run. Anders voldoet
de eerste slice niet aan de in het ontwerp geëiste reproduceerbare, gepinde toolchain.

### Herstel de roadmapvolgorde en artefactarchitectuur

De actuele ontwerpstatus noemt twee verplichte eerste spikes: zoeken en het
tegel-/filter-/cluster-/detailmodel. Deze roadmap zet zoeken als Plan 5 en bevat geen
aparte tweede spike. Bovendien belooft Plan 4 build-time clusters en detailrecords in
PMTiles, terwijl het actuele ontwerp juist ongeclusterde PMTiles, client-side
clustering en losse detail-shards voorschrijft.

Het ontwerp is op dit punt zelf nog niet volledig bijgewerkt: het verwijst naar §9b,
maar die sectie ontbreekt, en §13 noemt nog alleen de zoekspike. Rond eerst die
ontwerpwijziging af. Leg vervolgens bewust vast of beide spikes vroeg met
representatieve data draaien, of pas na een eerste echte merged dataset, en pas de
planvolgorde en Plan 4 daarop aan.

## Kleinere punten (P2)

- Gebruik een immutable categoriecollectie (`frozenset`) of een enum/literal zodat
  runtimecode de vocabulary niet per ongeluk kan wijzigen.
- Vermijd `out=sys.stdout` als defaultargument; bepaal stdout in de functie zodat
  redirection en testcapture na import correct werken.
- `test_sources_manifests` heet in Step 4 “failing”, maar de beschreven verwachte
  uitkomst is direct groen. Maak de RED-stap concreet of benoem dit als guardtest.
- Laat de adapter-template ook de vereiste mappingdocumentatie en een minimale
  contracttest bevatten; alleen “vul de functies in” borgt dat doel nog niet.
- Verifieer aan het eind niet alleen tests, maar ook formatter/linter/typecheck als die
  onderdeel van de beoogde kwaliteitslat zijn. Voeg die tools dan expliciet toe aan
  Task 1.

## Aanbevolen herzieningsvolgorde

1. Definieer `SourcePOI` versus `CanonicalPOI` en pas Task 1, 3 en 4 daarop aan.
2. Kies een file/stream-gebaseerd snapshotcontract met metadata, checksum en een via
   CLI reproduceerbare `fetched_at`.
3. Maak het manifest de runtime-configuratie en verscherp model plus guardtests.
4. Versterk schema- en retry-invarianten en voeg de ontbrekende foutpaden aan tests toe.
5. Maak de Wikidata-output uniek en deterministisch per QID.
6. Voeg `uv.lock` en geautomatiseerde end-to-end CLI-tests toe.
7. Rond ontwerp §9b af, breng roadmap en artefactmodel daarmee in overeenstemming en
   actualiseer daarna de self-review; vooral “schema validation”, “streaming” en
   “reproducible” zijn nu nog niet volledig afgedekt.
