from __future__ import annotations

from data_pipeline.merge_config import source_rank
from data_pipeline.schema import CanonicalPOI, Image, SourcePOI, SourceRef

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
                provenance[f"/categories/{len(categories)}"] = (
                    f"{p.source_id}/{p.source_record_id}"
                )
                categories.append(c)

    external_ids: dict[str, str] = {}
    for p in ordered:
        for k, v in p.external_ids.items():
            if k not in external_ids:
                external_ids[k] = v
                provenance[f"/external_ids/{k}"] = f"{p.source_id}/{p.source_record_id}"

    tags: dict = {}
    for p in ordered:
        for key, value in p.tags.items():
            if key not in tags:
                tags[key] = value
                provenance[f"/tags/{key}"] = f"{p.source_id}/{p.source_record_id}"

    images: list[Image] = []
    for p in ordered:
        for image in p.images:
            if image not in images:
                provenance[f"/images/{len(images)}"] = f"{p.source_id}/{p.source_record_id}"
                images.append(image)

    contributing = [
        SourceRef(source_id=p.source_id, source_record_id=p.source_record_id,
                  source_url=p.source_url, source_date=p.source_date, fetched_at=p.fetched_at)
        for p in ordered
    ]
    last_updated = max((p.source_date or p.fetched_at.date()) for p in ordered)

    return CanonicalPOI(
        poi_id=poi_id,
        external_ids=external_ids,
        tags=tags,
        images=images,
        categories=categories,
        country=ordered[0].country,
        contributing=contributing,
        field_provenance=provenance,
        last_updated=last_updated,
        **{k: values[k] for k in values},
    )
