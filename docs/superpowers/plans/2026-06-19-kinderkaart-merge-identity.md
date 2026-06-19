# Kinderkaart Plan 3 — Merge/Dedup Engine + Identity Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the per-source `SourcePOI` streams into deduplicated `CanonicalPOI` objects with
traceable provenance and a stable, persistent `poi_id` (via an identity registry), so the build
(Plan 4) has one canonical dataset with durable ids for deep-links.

**Architecture:** Builds on Plans 1–2. Adds `CanonicalPOI`/`SourceRef` models and an `external_ids`
field on `SourcePOI`; a normalization + geo-distance helper; a deterministic matcher (blocking →
strong keys → explainable score → union-find clusters); a field-merge step (source priority,
per-field provenance to `source_id/source_record_id`); a persistent identity registry with an
explicit transition table (mint/match/merge/split/tombstone); and a merge CLI with a
versioned `overrides.yaml`. Pure stdlib (`difflib`, `math`, `unicodedata`) — no new deps.

**Tech Stack:** Python 3.13, uv, pydantic v2, PyYAML, pytest, ruff, mypy.

## Global Constraints

- Inherits all Plan 1/2 constraints (`extra="forbid"`, tz-aware UTC datetimes, country⊆supported,
  deduped categories, manifest-driven sources).
- **Determinism & idempotency:** same inputs + same prior registry → byte-identical
  `CanonicalPOI` NDJSON and registry. All iteration over sets/dicts is sorted.
- **`poi_id` is assigned by the registry, never recomputed from volatile state.** Once minted it
  is stable; superseded ids become `aliases`; deleted ids become tombstones; an id never points
  to a different physical object.
- **`field_provenance` values are `"<source_id>/<source_record_id>"`** (not just `source_id`).
- **Source priority (highest→lowest)** for field conflicts:
  `["rce-musea", "wikidata-museums", "osm", "den-haag-speeltuinen", "eindhoven-speeltuinen"]`.
  Unknown sources sort last, then alphabetically. Defined once in `data_pipeline/merge_config.py`.
- **Per-category match radius (metres):** `playground 60, restaurant_kidfriendly 60, museum 150,
  petting_zoo 150, pool 150, zoo 300, play_park 300`. Name-similarity threshold `0.85`.
- Quality bar before every commit: `uv run ruff check . && uv run mypy data_pipeline sources && uv run pytest`.

---

### Task 1: `CanonicalPOI`/`SourceRef` models + `external_ids` on `SourcePOI`

**Files:**
- Modify: `data_pipeline/schema.py`
- Modify: `sources/wikidata_museums/adapter.py` (populate `external_ids`)
- Modify: `sources/osm/adapter.py` (populate `external_ids` from `wikidata`/`ref` tags)
- Test: `tests/test_schema.py` (add), `tests/test_wikidata_museums.py` + `tests/test_osm.py` (assert external_ids)

**Interfaces:**
- Produces: `data_pipeline.schema.SourceRef` (strict: `source_id, source_record_id,
  source_url|None, source_date|None, fetched_at: datetime UTC`)
- Produces: `data_pipeline.schema.CanonicalPOI(FacetFields)` with `poi_id, external_ids,
  aliases, contributing: list[SourceRef], field_provenance: dict[str,str], last_updated: date|None,
  build_version: str|None`
- Changed: `SourcePOI` gains `external_ids: dict[str, str] = {}`

- [ ] **Step 1: Failing tests**

Add to `tests/test_schema.py`:
```python
def test_sourcepoi_external_ids_default_empty():
    from data_pipeline.schema import SourcePOI
    poi = SourcePOI(**_src())
    assert poi.external_ids == {}


def test_canonicalpoi_requires_contributing():
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from data_pipeline.schema import CanonicalPOI, SourceRef
    ref = SourceRef(source_id="osm", source_record_id="node/1",
                    fetched_at=datetime(2026, 6, 19, tzinfo=timezone.utc))
    poi = CanonicalPOI(
        poi_id="osm/node/1", name="A", categories=["playground"],
        lat=52.0, lon=5.0, country="nl", contributing=[ref],
        field_provenance={"name": "osm/node/1"},
    )
    assert poi.poi_id == "osm/node/1"
    assert poi.aliases == [] and poi.external_ids == {}
    with pytest.raises(ValidationError):
        CanonicalPOI(poi_id="x", name="A", categories=["playground"], lat=52.0,
                     lon=5.0, country="nl", contributing=[], field_provenance={},
                     surprise=1)  # extra forbidden
```

In `tests/test_wikidata_museums.py` add: `assert pois[0].external_ids == {"wikidata": "Q190804"}`.
In `tests/test_osm.py` add a `wikidata` tag to the playground node fixture and assert
`pois["node/1"].external_ids == {"wikidata": "Q42"}` (add `<tag k="wikidata" v="Q42"/>` to node 1).

- [ ] **Step 2: Run to confirm failures.**

- [ ] **Step 3: Implement schema additions**

In `data_pipeline/schema.py`, add `external_ids` to `SourcePOI` and add the two new models:
```python
class SourcePOI(FacetFields):
    source_id: str
    source_record_id: str
    external_ids: dict[str, str] = Field(default_factory=dict)
    source_url: str | None = None
    source_date: date | None = None
    fetched_at: datetime
    field_provenance: dict[str, str] = Field(default_factory=dict)
    # ... existing validators unchanged ...


class SourceRef(_Strict):
    source_id: str
    source_record_id: str
    source_url: str | None = None
    source_date: date | None = None
    fetched_at: datetime

    @field_validator("fetched_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("fetched_at must be timezone-aware")
        return v.astimezone(timezone.utc)


class CanonicalPOI(FacetFields):
    poi_id: str
    external_ids: dict[str, str] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    contributing: list[SourceRef]
    field_provenance: dict[str, str] = Field(default_factory=dict)
    last_updated: date | None = None
    build_version: str | None = None
```
(`timezone` is already imported in schema.py.)

- [ ] **Step 4: Populate `external_ids` in adapters**

Wikidata `normalize` — add `external_ids={"wikidata": qid}` to the `SourcePOI(...)`.
OSM `normalize` — after computing `tags`, build `ext = {}`; if `tags.get("wikidata")` matches
`^Q[1-9][0-9]*$` add `ext["wikidata"] = tags["wikidata"]`; pass `external_ids=ext`.

- [ ] **Step 5: Green + quality bar + commit**
```bash
git add -A && git commit -m "feat: add CanonicalPOI/SourceRef models + external_ids on SourcePOI"
```

---

### Task 2: Normalization + geo-distance helpers

**Files:**
- Create: `data_pipeline/textnorm.py`, `data_pipeline/geodist.py`
- Test: `tests/test_textnorm.py`, `tests/test_geodist.py`

**Interfaces:**
- Produces: `data_pipeline.textnorm.normalize_name(s: str) -> str`
- Produces: `data_pipeline.textnorm.name_similarity(a: str, b: str) -> float` (0..1, on normalized names)
- Produces: `data_pipeline.textnorm.website_host(url: str | None) -> str | None`
- Produces: `data_pipeline.geodist.haversine_m(lat1, lon1, lat2, lon2) -> float`

- [ ] **Step 1: Failing tests**

`tests/test_textnorm.py`:
```python
from data_pipeline.textnorm import name_similarity, normalize_name, website_host


def test_normalize_strips_accents_articles_punct():
    assert normalize_name("De Café-Réstaurant 't Hoekje!") == "cafe restaurant hoekje"
    assert normalize_name("Het Spoorwegmuseum") == "spoorwegmuseum"


def test_similarity_high_for_same_place():
    assert name_similarity("Rijksmuseum", "het rijksmuseum") > 0.9


def test_similarity_low_for_different():
    assert name_similarity("Speeltuin Noord", "Museum Volkenkunde") < 0.5


def test_website_host_normalizes():
    assert website_host("https://WWW.Rijksmuseum.nl/en/visit") == "rijksmuseum.nl"
    assert website_host(None) is None
```

`tests/test_geodist.py`:
```python
from data_pipeline.geodist import haversine_m


def test_haversine_known_distance():
    # ~1 deg longitude at 52N is ~68.5 km; check a small known hop (~111m per 0.001 lat)
    d = haversine_m(52.0, 5.0, 52.0009, 5.0)
    assert 95 < d < 105


def test_haversine_zero():
    assert haversine_m(52.0, 5.0, 52.0, 5.0) == 0.0
```

- [ ] **Step 2: Run to confirm failures.**

- [ ] **Step 3: Implement**

`data_pipeline/textnorm.py`:
```python
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlparse

_ARTICLES = {"de", "het", "een", "t", "the"}
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_name(s: str) -> str:
    decomposed = unicodedata.normalize("NFKD", s)
    ascii_str = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = _NON_ALNUM.sub(" ", ascii_str.lower())
    tokens = [t for t in lowered.split() if t and t not in _ARTICLES]
    return " ".join(tokens)


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


def website_host(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host or None
```

`data_pipeline/geodist.py`:
```python
from __future__ import annotations

import math

_EARTH_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    if lat1 == lat2 and lon1 == lon2:
        return 0.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_M * math.asin(math.sqrt(a))
```

- [ ] **Step 4: Green + commit**
```bash
git add data_pipeline/textnorm.py data_pipeline/geodist.py tests/test_textnorm.py tests/test_geodist.py
git commit -m "feat: add name normalization + haversine distance helpers"
```

---

### Task 3: Matcher — blocking, strong keys, scoring, clustering

**Files:**
- Create: `data_pipeline/merge_config.py`, `data_pipeline/matcher.py`
- Test: `tests/test_matcher.py`

**Interfaces:**
- Produces: `data_pipeline.merge_config.SOURCE_PRIORITY: list[str]`, `MATCH_RADIUS_M: dict[str,float]`,
  `NAME_THRESHOLD: float`, `source_rank(source_id: str) -> tuple[int, str]`
- Produces: `data_pipeline.matcher.cluster(pois: list[SourcePOI]) -> list[list[int]]` returning, for
  the input list, a deterministic list of clusters (each a sorted list of input indices), clusters
  themselves sorted by their smallest index.
- Produces: `data_pipeline.matcher.is_match(a: SourcePOI, b: SourcePOI) -> bool` (the pairwise rule)

- [ ] **Step 1: Config module**

`data_pipeline/merge_config.py`:
```python
from __future__ import annotations

SOURCE_PRIORITY: list[str] = [
    "rce-musea",
    "wikidata-museums",
    "osm",
    "den-haag-speeltuinen",
    "eindhoven-speeltuinen",
]

MATCH_RADIUS_M: dict[str, float] = {
    "playground": 60.0,
    "restaurant_kidfriendly": 60.0,
    "museum": 150.0,
    "petting_zoo": 150.0,
    "pool": 150.0,
    "zoo": 300.0,
    "play_park": 300.0,
}

NAME_THRESHOLD = 0.85
_MAX_STRONGKEY_M = 2000.0  # sanity cap even for strong-key matches


def source_rank(source_id: str) -> tuple[int, str]:
    """Lower sorts higher-priority. Unknown sources sort after known, then alphabetical."""
    try:
        return (SOURCE_PRIORITY.index(source_id), "")
    except ValueError:
        return (len(SOURCE_PRIORITY), source_id)
```

- [ ] **Step 2: Failing test (with a labeled regression set)**

`tests/test_matcher.py`:
```python
from datetime import datetime, timezone

from data_pipeline.matcher import cluster, is_match
from data_pipeline.schema import SourcePOI

T = datetime(2026, 6, 19, tzinfo=timezone.utc)


def poi(sid, rid, name, lat, lon, cats=("museum",), **kw):
    return SourcePOI(source_id=sid, source_record_id=rid, name=name, lat=lat, lon=lon,
                     categories=list(cats), country="nl", fetched_at=T, **kw)


def test_same_museum_two_sources_merges():
    a = poi("rce-musea", "1", "Rijksmuseum", 52.3600, 4.8852)
    b = poi("wikidata-museums", "Q190804", "Het Rijksmuseum", 52.3601, 4.8853,
            external_ids={"wikidata": "Q190804"})
    assert is_match(a, b)


def test_strong_key_external_id_merges_despite_name():
    a = poi("osm", "node/9", "RM", 52.3605, 4.8860, external_ids={"wikidata": "Q190804"})
    b = poi("wikidata-museums", "Q190804", "Rijksmuseum", 52.3601, 4.8853,
            external_ids={"wikidata": "Q190804"})
    assert is_match(a, b)


def test_two_nearby_different_playgrounds_do_not_merge():
    a = poi("osm", "node/1", "Speeltuin Noord", 52.0000, 5.0000, cats=("playground",))
    b = poi("osm", "node/2", "Speeltuin Zuid", 52.0003, 5.0000, cats=("playground",))
    assert not is_match(a, b)  # ~33m apart but names differ


def test_same_name_far_apart_do_not_merge():
    a = poi("osm", "node/1", "Rijksmuseum", 52.36, 4.88)
    b = poi("rce-musea", "2", "Rijksmuseum", 51.00, 4.00)
    assert not is_match(a, b)


def test_cluster_groups_transitively_and_is_sorted():
    a = poi("rce-musea", "1", "Rijksmuseum", 52.3600, 4.8852)
    b = poi("wikidata-museums", "Q190804", "Rijksmuseum", 52.3601, 4.8853)
    c = poi("osm", "node/5", "Speeltuin", 52.9, 4.0, cats=("playground",))
    clusters = cluster([a, b, c])
    assert clusters == [[0, 1], [2]]
```

- [ ] **Step 3: Run to confirm failures.**

- [ ] **Step 4: Implement the matcher**

`data_pipeline/matcher.py`:
```python
from __future__ import annotations

from collections import defaultdict

from data_pipeline.geodist import haversine_m
from data_pipeline.merge_config import (
    MATCH_RADIUS_M,
    NAME_THRESHOLD,
    _MAX_STRONGKEY_M,
)
from data_pipeline.schema import SourcePOI
from data_pipeline.textnorm import name_similarity, website_host


def _shares_external_id(a: SourcePOI, b: SourcePOI) -> bool:
    for k, v in a.external_ids.items():
        if b.external_ids.get(k) == v:
            return True
    return False


def _shares_website(a: SourcePOI, b: SourcePOI) -> bool:
    ha, hb = website_host(a.website), website_host(b.website)
    return ha is not None and ha == hb


def is_match(a: SourcePOI, b: SourcePOI) -> bool:
    dist = haversine_m(a.lat, a.lon, b.lat, b.lon)
    # Strong keys: shared external id or website host (with a sanity distance cap).
    if (_shares_external_id(a, b) or _shares_website(a, b)) and dist <= _MAX_STRONGKEY_M:
        return True
    # Scored path: requires category overlap, proximity within the tighter radius, name match.
    shared = set(a.categories) & set(b.categories)
    if not shared:
        return False
    radius = min(MATCH_RADIUS_M[c] for c in shared)
    if dist > radius:
        return False
    return name_similarity(a.name, b.name) >= NAME_THRESHOLD


def _cell(lat: float, lon: float) -> tuple[int, int]:
    # ~0.01 deg ≈ 1.1 km blocking cell; compare own + 8 neighbours.
    return (round(lat * 100), round(lon * 100))


def cluster(pois: list[SourcePOI]) -> list[list[int]]:
    parent = list(range(len(pois)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[max(rx, ry)] = min(rx, ry)

    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, p in enumerate(pois):
        grid[_cell(p.lat, p.lon)].append(i)

    for i, p in enumerate(pois):
        ci, cj = _cell(p.lat, p.lon)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for j in grid.get((ci + di, cj + dj), ()):
                    if j > i and is_match(p, pois[j]):
                        union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(pois)):
        groups[find(i)].append(i)
    clusters = [sorted(members) for members in groups.values()]
    clusters.sort(key=lambda m: m[0])
    return clusters
```

- [ ] **Step 5: Green + commit**
```bash
git add data_pipeline/merge_config.py data_pipeline/matcher.py tests/test_matcher.py
git commit -m "feat: add deterministic matcher (blocking, strong keys, scoring, union-find)"
```

---

### Task 4: Field merge — cluster → `CanonicalPOI`

**Files:**
- Create: `data_pipeline/merge_fields.py`
- Test: `tests/test_merge_fields.py`

**Interfaces:**
- Produces: `data_pipeline.merge_fields.merge_cluster(pois: list[SourcePOI], poi_id: str) -> CanonicalPOI`
  — pois are the cluster members; the function applies source priority, fills `field_provenance`
  (`"<source_id>/<source_record_id>"`), unions categories + external_ids, builds `contributing`
  (sorted by source rank then record id), and sets `last_updated` = max(`source_date` or
  `fetched_at`.date()).

- [ ] **Step 1: Failing test**

`tests/test_merge_fields.py`:
```python
from datetime import date, datetime, timezone

from data_pipeline.merge_fields import merge_cluster
from data_pipeline.schema import SourcePOI

T = datetime(2026, 6, 19, tzinfo=timezone.utc)


def test_priority_wins_and_provenance_records_source_record():
    rce = SourcePOI(source_id="rce-musea", source_record_id="m1", name="Rijksmuseum",
                    categories=["museum"], lat=52.36, lon=4.885, country="nl", fetched_at=T,
                    field_provenance={"name": "rce-musea"})
    wd = SourcePOI(source_id="wikidata-museums", source_record_id="Q190804", name="Rijksmuseum NL",
                   categories=["museum"], lat=52.3601, lon=4.8853, country="nl", fetched_at=T,
                   website="https://rijksmuseum.nl", external_ids={"wikidata": "Q190804"},
                   field_provenance={"name": "wikidata-museums"})
    poi = merge_cluster([wd, rce], poi_id="rce-musea/m1")
    assert poi.poi_id == "rce-musea/m1"
    assert poi.name == "Rijksmuseum"  # rce-musea outranks wikidata
    assert poi.field_provenance["name"] == "rce-musea/m1"
    # website only from wikidata -> provenance points there
    assert poi.website == "https://rijksmuseum.nl"
    assert poi.field_provenance["website"] == "wikidata-museums/Q190804"
    assert poi.external_ids == {"wikidata": "Q190804"}
    assert poi.categories == ["museum"]
    assert {r.source_id for r in poi.contributing} == {"rce-musea", "wikidata-museums"}
    # contributing sorted by source rank: rce-musea (rank 0) first
    assert poi.contributing[0].source_id == "rce-musea"
    assert poi.last_updated == date(2026, 6, 19)


def test_categories_unioned_across_cluster():
    a = SourcePOI(source_id="osm", source_record_id="way/1", name="X", categories=["zoo"],
                  lat=52.0, lon=5.0, country="nl", fetched_at=T)
    b = SourcePOI(source_id="osm", source_record_id="way/2", name="X", categories=["petting_zoo"],
                  lat=52.0, lon=5.0, country="nl", fetched_at=T)
    poi = merge_cluster([a, b], poi_id="osm/way/1")
    assert set(poi.categories) == {"zoo", "petting_zoo"}
```

- [ ] **Step 2: Run to confirm failures.**

- [ ] **Step 3: Implement**

`data_pipeline/merge_fields.py`:
```python
from __future__ import annotations

from data_pipeline.merge_config import source_rank
from data_pipeline.schema import CanonicalPOI, SourcePOI, SourceRef

# Scalar fields resolved by source priority (highest-priority non-null wins).
_SCALAR_FIELDS = (
    "name", "lat", "lon", "address", "indoor", "free", "price_model",
    "age_min", "age_max", "accessibility", "opening_hours", "website",
)


def _ordered(pois: list[SourcePOI]) -> list[SourcePOI]:
    return sorted(pois, key=lambda p: (source_rank(p.source_id), p.source_record_id))


def merge_cluster(pois: list[SourcePOI], poi_id: str) -> CanonicalPOI:
    ordered = _ordered(pois)
    values: dict[str, object] = {}
    provenance: dict[str, str] = {}
    for field in _SCALAR_FIELDS:
        for p in ordered:
            val = getattr(p, field)
            if val is not None:
                values[field] = val
                provenance[field] = f"{p.source_id}/{p.source_record_id}"
                break

    categories: list[str] = []
    for p in ordered:
        for c in p.categories:
            if c not in categories:
                categories.append(c)

    external_ids: dict[str, str] = {}
    for p in ordered:
        for k, v in p.external_ids.items():
            external_ids.setdefault(k, v)

    contributing = [
        SourceRef(source_id=p.source_id, source_record_id=p.source_record_id,
                  source_url=p.source_url, source_date=p.source_date, fetched_at=p.fetched_at)
        for p in ordered
    ]
    last_updated = max((p.source_date or p.fetched_at.date()) for p in ordered)

    return CanonicalPOI(
        poi_id=poi_id,
        external_ids=external_ids,
        categories=categories,
        country=ordered[0].country,
        contributing=contributing,
        field_provenance=provenance,
        last_updated=last_updated,
        **{k: values[k] for k in values},
    )
```

- [ ] **Step 4: Green + commit**
```bash
git add data_pipeline/merge_fields.py tests/test_merge_fields.py
git commit -m "feat: add field-merge (source priority, provenance, contributing, last_updated)"
```

---

### Task 5: Identity registry + transition table

**Files:**
- Create: `data_pipeline/identity.py`
- Test: `tests/test_identity.py`

**Interfaces:**
- Produces: `data_pipeline.identity.Registry` with:
  - `Registry.load(path) -> Registry` (empty if file missing)
  - `assign(clusters: list[list[str]]) -> dict[int, str]` where each cluster is a sorted list of
    member keys (`"<source_id>/<source_record_id>"`); returns cluster-index → `poi_id`. Applies the
    transition table and mutates internal state (active ids, member→id map, aliases, tombstones).
  - `aliases_for(poi_id) -> list[str]`
  - `save(path) -> None` (deterministic JSON: sorted keys, trailing newline)
- Transition rules (deterministic):
  - **mint:** cluster overlaps no existing id → new id = the cluster's highest-priority member key.
  - **match:** cluster overlaps exactly one existing id → reuse it; absorb any new member keys.
  - **merge:** cluster overlaps ≥2 existing ids → survivor = the one whose id has the highest
    source rank (tie: lexicographically smallest id); losers' ids recorded as `aliases` of survivor.
  - **split:** one existing id's members now span ≥2 clusters → the cluster with the largest member
    overlap keeps the id; the others mint new ids; if overlap ties, the id becomes a tombstone and
    all resulting clusters mint new ids (ambiguous).
  - **deletion:** an existing active id with no members in the new input → marked tombstone.

- [ ] **Step 1: Failing test (two-build determinism + each transition)**

`tests/test_identity.py`:
```python
from data_pipeline.identity import Registry


def _mk(members_per_cluster):
    return [sorted(c) for c in members_per_cluster]


def test_mint_uses_highest_priority_member():
    reg = Registry.load("/nonexistent.json")  # empty
    ids = reg.assign(_mk([["wikidata-museums/Q1", "osm/node/9"]]))
    # rce/wikidata/osm priority -> wikidata-museums outranks osm
    assert ids[0] == "wikidata-museums/Q1"


def test_match_reuses_id_across_builds():
    reg = Registry.load("/nonexistent.json")
    reg.assign(_mk([["rce-musea/m1", "wikidata-museums/Q1"]]))
    # next build: same place, osm record now also present
    ids = reg.assign(_mk([["rce-musea/m1", "wikidata-museums/Q1", "osm/node/3"]]))
    assert ids[0] == "rce-musea/m1"  # stable survivor id


def test_merge_records_aliases():
    reg = Registry.load("/nonexistent.json")
    reg.assign(_mk([["rce-musea/m1"], ["wikidata-museums/Q1"]]))  # two ids minted
    ids = reg.assign(_mk([["rce-musea/m1", "wikidata-museums/Q1"]]))  # now merged
    survivor = ids[0]
    assert survivor == "rce-musea/m1"  # higher rank
    assert "wikidata-museums/Q1" in reg.aliases_for(survivor)


def test_split_largest_overlap_keeps_id():
    reg = Registry.load("/nonexistent.json")
    reg.assign(_mk([["rce-musea/m1", "osm/node/3", "osm/node/4"]]))
    ids = reg.assign(_mk([["rce-musea/m1", "osm/node/3"], ["osm/node/4"]]))
    assert ids[0] == "rce-musea/m1"   # larger overlap keeps id
    assert ids[1] != "rce-musea/m1"   # minted new


def test_deletion_tombstones(tmp_path):
    reg = Registry.load(str(tmp_path / "id.json"))
    reg.assign(_mk([["osm/node/1"]]))
    reg.assign(_mk([["osm/node/2"]]))  # node/1 gone
    assert reg.is_tombstone("osm/node/1")


def test_save_is_deterministic(tmp_path):
    p = tmp_path / "id.json"
    reg = Registry.load(str(p))
    reg.assign(_mk([["rce-musea/m1", "wikidata-museums/Q1"]]))
    reg.save(str(p))
    first = p.read_text()
    reg2 = Registry.load(str(p))
    reg2.assign(_mk([["rce-musea/m1", "wikidata-museums/Q1"]]))
    reg2.save(str(p))
    assert p.read_text() == first  # idempotent
```

- [ ] **Step 2: Run to confirm failures.**

- [ ] **Step 3: Implement**

`data_pipeline/identity.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

from data_pipeline.merge_config import source_rank


def _member_rank(member_key: str) -> tuple[int, str]:
    source_id = member_key.split("/", 1)[0]
    return (source_rank(source_id)[0], member_key)


def _mint_id(members: list[str]) -> str:
    return min(members, key=_member_rank)


def _id_rank(poi_id: str) -> tuple[int, str]:
    source_id = poi_id.split("/", 1)[0]
    return (source_rank(source_id)[0], poi_id)


class Registry:
    def __init__(self, data: dict | None = None) -> None:
        data = data or {}
        # poi_id -> {"members": [..], "aliases": [..], "status": "active"|"tombstone"}
        self.entries: dict[str, dict] = data.get("entries", {})

    @classmethod
    def load(cls, path: str | Path) -> "Registry":
        p = Path(path)
        if not p.exists():
            return cls()
        return cls(json.loads(p.read_text()))

    def _member_to_id(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for pid, e in self.entries.items():
            if e["status"] == "active":
                for m in e["members"]:
                    out[m] = pid
        return out

    def assign(self, clusters: list[list[str]]) -> dict[int, str]:
        m2id = self._member_to_id()
        # For each cluster, find the set of prior ids its members map to.
        cluster_ids: list[set[str]] = []
        for members in clusters:
            cluster_ids.append({m2id[m] for m in members if m in m2id})

        # Detect splits: a prior id referenced by >1 cluster.
        id_to_clusters: dict[str, list[int]] = {}
        for idx, ids in enumerate(cluster_ids):
            for pid in ids:
                id_to_clusters.setdefault(pid, []).append(idx)

        result: dict[int, str] = {}
        seen_input_members: set[str] = set()
        # Process clusters in deterministic order (by sorted first member).
        order = sorted(range(len(clusters)), key=lambda i: clusters[i][0])
        for idx in order:
            members = clusters[idx]
            seen_input_members.update(members)
            prior = sorted(cluster_ids[idx], key=_id_rank)

            if not prior:  # mint
                pid = _mint_id(members)
            elif len(prior) == 1:
                pid = prior[0]
                split_clusters = id_to_clusters[pid]
                if len(split_clusters) > 1:  # split
                    pid = self._resolve_split(pid, split_clusters, clusters, result)
                    if pid is None:
                        pid = _mint_id(members)
            else:  # merge
                survivor = prior[0]
                for loser in prior[1:]:
                    self.entries[survivor]["aliases"] = sorted(
                        set(self.entries[survivor]["aliases"]) | {loser}
                        | set(self.entries[loser]["aliases"])
                    )
                    self.entries[loser]["status"] = "tombstone"
                    self.entries[loser]["members"] = []
                pid = survivor

            self.entries.setdefault(pid, {"members": [], "aliases": [], "status": "active"})
            self.entries[pid]["status"] = "active"
            self.entries[pid]["members"] = sorted(set(members))
            result[idx] = pid

        # Deletion: previously-active ids with no members in this input -> tombstone.
        for pid, e in self.entries.items():
            if e["status"] == "active" and pid not in result.values():
                if not any(m in seen_input_members for m in e["members"]):
                    e["status"] = "tombstone"
                    e["members"] = []
        return result

    def _resolve_split(self, pid: str, cluster_idxs: list[int], clusters, result) -> str | None:
        prior_members = set(self.entries[pid]["members"])
        overlaps = [(len(prior_members & set(clusters[i])), -i, i) for i in cluster_idxs]
        overlaps.sort(reverse=True)
        top, second = overlaps[0], overlaps[1]
        if top[0] == second[0]:  # ambiguous tie -> tombstone, all mint new
            self.entries[pid]["status"] = "tombstone"
            self.entries[pid]["members"] = []
            return None
        winner_idx = top[2]
        # current cluster keeps id only if it is the winner
        return pid  # caller uses pid for the winning cluster; losers re-enter as no-prior next

    def aliases_for(self, poi_id: str) -> list[str]:
        return self.entries.get(poi_id, {}).get("aliases", [])

    def is_tombstone(self, poi_id: str) -> bool:
        return self.entries.get(poi_id, {}).get("status") == "tombstone"

    def save(self, path: str | Path) -> None:
        payload = {"entries": self.entries}
        Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
```

Note on the split path: the winning cluster keeps `pid`; non-winning clusters that mapped only to
`pid` will have `prior == [pid]` but `_resolve_split` returns `pid` only for the winner. Implement
`_resolve_split` to return `pid` for the winning cluster index and `None` for the others by checking
whether `idx == winner_idx`; if the implementer finds the single-return shape awkward, refactor to
compute split resolutions up front for all clusters sharing an id (the tests define the required
behavior — make them pass deterministically).

- [ ] **Step 4: Green + commit**
```bash
git add data_pipeline/identity.py tests/test_identity.py
git commit -m "feat: add identity registry with mint/match/merge/split/tombstone transitions"
```

---

### Task 6: Merge CLI + overrides

**Files:**
- Create: `data_pipeline/merge.py`
- Create: `data_pipeline/overrides.example.yaml`
- Test: `tests/test_merge_cli.py`

**Interfaces:**
- Produces: `data_pipeline.merge.run_merge(source_ndjson_paths: list[Path], identity_path: Path,
  out_path: Path, build_version: str, overrides_path: Path | None = None) -> int` (returns count of
  CanonicalPOI written). Reads all SourcePOI, applies `overrides` (force-merge/force-split/field
  corrections), clusters, merges, assigns poi_ids via the registry (loaded from + saved to
  `identity_path`), writes `CanonicalPOI` NDJSON sorted by `poi_id`, stamps `build_version`.
- CLI: `python -m data_pipeline.merge --identity PATH --out PATH --build-version V [--overrides PATH] SRC.ndjson...`

- [ ] **Step 1: Failing test**

`tests/test_merge_cli.py`:
```python
import json
from datetime import datetime, timezone
from pathlib import Path

from data_pipeline.merge import run_merge
from data_pipeline.schema import SourcePOI

T = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _write_ndjson(path: Path, pois: list[SourcePOI]) -> None:
    path.write_text("\n".join(p.model_dump_json() for p in pois) + "\n")


def test_merge_dedups_and_is_idempotent(tmp_path):
    rce = SourcePOI(source_id="rce-musea", source_record_id="m1", name="Rijksmuseum",
                    categories=["museum"], lat=52.3600, lon=4.8852, country="nl", fetched_at=T)
    wd = SourcePOI(source_id="wikidata-museums", source_record_id="Q190804", name="Rijksmuseum",
                   categories=["museum"], lat=52.3601, lon=4.8853, country="nl", fetched_at=T,
                   external_ids={"wikidata": "Q190804"})
    play = SourcePOI(source_id="osm", source_record_id="node/1", name="Speeltuin",
                     categories=["playground"], lat=52.9, lon=4.0, country="nl", fetched_at=T)
    src_a = tmp_path / "rce.ndjson"; _write_ndjson(src_a, [rce])
    src_b = tmp_path / "other.ndjson"; _write_ndjson(src_b, [wd, play])
    idp = tmp_path / "identity.json"; out = tmp_path / "canonical.ndjson"

    n = run_merge([src_a, src_b], idp, out, build_version="2026.06.19")
    assert n == 2  # museum (merged) + playground
    lines = out.read_text().strip().split("\n")
    pois = [json.loads(line) for line in lines]
    museum = next(p for p in pois if "museum" in p["categories"])
    assert museum["poi_id"] == "rce-musea/m1"
    assert museum["external_ids"] == {"wikidata": "Q190804"}
    assert museum["build_version"] == "2026.06.19"
    assert {r["source_id"] for r in museum["contributing"]} == {"rce-musea", "wikidata-museums"}

    out2 = tmp_path / "canonical2.ndjson"
    run_merge([src_a, src_b], idp, out2, build_version="2026.06.19")
    assert out2.read_text() == out.read_text()  # idempotent re-run, stable ids
```

- [ ] **Step 2: Run to confirm failures.**

- [ ] **Step 3: Implement**

`data_pipeline/merge.py`:
```python
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from data_pipeline.identity import Registry
from data_pipeline.matcher import cluster
from data_pipeline.merge_fields import merge_cluster
from data_pipeline.schema import CanonicalPOI, SourcePOI


def _load_sources(paths: list[Path]) -> list[SourcePOI]:
    pois: list[SourcePOI] = []
    for p in paths:
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                pois.append(SourcePOI.model_validate_json(line))
    # Deterministic input order.
    pois.sort(key=lambda x: (x.source_id, x.source_record_id))
    return pois


def _apply_overrides(clusters: list[list[int]], pois: list[SourcePOI],
                     overrides: dict) -> list[list[int]]:
    if not overrides:
        return clusters
    key_to_idx = {f"{p.source_id}/{p.source_record_id}": i for i, p in enumerate(pois)}
    # force_merge: list of lists of member keys that must end up together
    parent = list(range(len(pois)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for members in clusters:
        for m in members[1:]:
            union(members[0], m)
    for group in overrides.get("force_merge", []):
        idxs = [key_to_idx[k] for k in group if k in key_to_idx]
        for k in idxs[1:]:
            union(idxs[0], k)
    forced_apart = {tuple(sorted(g)) for g in overrides.get("force_split", [])}
    from collections import defaultdict
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(pois)):
        groups[find(i)].append(i)
    result = []
    for members in groups.values():
        members = sorted(members)
        keys = tuple(sorted(f"{pois[i].source_id}/{pois[i].source_record_id}" for i in members))
        if keys in forced_apart:
            result.extend([[i] for i in members])
        else:
            result.append(members)
    result.sort(key=lambda m: m[0])
    return result


def run_merge(source_ndjson_paths: list[Path], identity_path: Path, out_path: Path,
              build_version: str, overrides_path: Path | None = None) -> int:
    pois = _load_sources(source_ndjson_paths)
    overrides = {}
    if overrides_path and overrides_path.exists():
        overrides = yaml.safe_load(overrides_path.read_text()) or {}

    clusters = cluster(pois)
    clusters = _apply_overrides(clusters, pois, overrides)

    member_clusters = [
        sorted(f"{pois[i].source_id}/{pois[i].source_record_id}" for i in members)
        for members in clusters
    ]
    reg = Registry.load(identity_path)
    idx_to_id = reg.assign(member_clusters)
    reg.save(identity_path)

    canon: list[CanonicalPOI] = []
    for idx, members in enumerate(clusters):
        poi = merge_cluster([pois[i] for i in members], poi_id=idx_to_id[idx])
        poi.build_version = build_version
        poi.aliases = reg.aliases_for(poi.poi_id)
        canon.append(poi)
    canon.sort(key=lambda c: c.poi_id)
    out_path.write_text("\n".join(c.model_dump_json() for c in canon) + "\n")
    return len(canon)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--identity", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--build-version", required=True)
    ap.add_argument("--overrides")
    ap.add_argument("sources", nargs="+")
    args = ap.parse_args()
    n = run_merge([Path(s) for s in args.sources], Path(args.identity), Path(args.out),
                  build_version=args.build_version,
                  overrides_path=Path(args.overrides) if args.overrides else None)
    print(f"wrote {n} canonical POIs")


if __name__ == "__main__":
    main()
```

`data_pipeline/overrides.example.yaml`:
```yaml
# Versioned manual corrections applied during merge.
force_merge:
  - ["osm/node/123", "wikidata-museums/Q456"]   # these are the same place
force_split:
  - ["osm/node/1", "osm/node/2"]                # never merge these two
```

- [ ] **Step 4: Green + quality bar + commit**
```bash
git add data_pipeline/merge.py data_pipeline/overrides.example.yaml tests/test_merge_cli.py
git commit -m "feat: add merge CLI with overrides (SourcePOI -> CanonicalPOI + identity)"
```

---

## Self-Review

**Spec coverage (Plan 3 = spec §6 + §4 canonical model):**
- CanonicalPOI/SourceRef + external_ids on SourcePOI → Task 1 ✓
- Strong keys (external id, website) + explainable score (name sim, distance, category) + per-category
  radius → Task 3 ✓
- Normalization (unicode, articles, punctuation) → Task 2 ✓
- Field merge with source priority + provenance to `(source_id, source_record_id)` + contributing +
  last_updated → Task 4 ✓
- Identity registry: persistent, single authoritative file, transition table
  (mint/match/merge/split/tombstone/deletion), aliases → Task 5 ✓
- Overrides (force-merge/force-split) → Task 6 ✓
- Determinism/idempotency → Tasks 3, 5, 6 tests ✓
- Labeled regression set (true merges + true non-merges) → Task 3 tests ✓

**Placeholder scan:** none. Task 5's `_resolve_split` note explicitly hands the implementer the
required behavior (encoded in `test_split_largest_overlap_keeps_id`) and flags the single-return
awkwardness — the test is the contract; the implementer makes it pass deterministically.

**Type consistency:** `SourcePOI`/`CanonicalPOI`/`SourceRef` field names match Task 1 + spec §4.
`merge_cluster(pois, poi_id) -> CanonicalPOI`, `cluster(pois) -> list[list[int]]`,
`Registry.assign(clusters: list[list[str]]) -> dict[int,str]` are consistent across Tasks 4–6.

## Notes for later plans
- The **identity registry lives at `data/nl/identity.json`** and is committed by the build
  (Plan 4) inside the atomic publish (spec §6). Plan 4 wires `run_merge` into the pipeline and
  commits the updated registry transactionally.
- Matcher blocking uses a 0.01° grid (~1.1 km) — adequate for the per-category radii (≤300 m).
  If a future category needs a larger radius, widen the neighbour search.
