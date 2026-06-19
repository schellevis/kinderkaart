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
