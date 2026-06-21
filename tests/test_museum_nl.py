import json
from datetime import datetime, timezone
from pathlib import Path

from sources.museum_nl.adapter import normalize

FIXTURES = Path(__file__).parent / "fixtures" / "museum_nl"
FIXED = datetime(2026, 6, 20, tzinfo=timezone.utc)


def _envelope(tmp_path: Path) -> Path:
    records = [
        {"slug": "anne-frank-huis", "url": "https://www.museum.nl/nl/anne-frank-huis",
         "html": (FIXTURES / "museum.html").read_text(encoding="utf-8")},
        {"slug": "geen-coords", "url": "https://www.museum.nl/nl/geen-coords",
         "html": (FIXTURES / "no_geo.html").read_text(encoding="utf-8")},
        {"slug": "amsterdam", "url": "https://www.museum.nl/nl/amsterdam",
         "html": (FIXTURES / "theme.html").read_text(encoding="utf-8")},
    ]
    path = tmp_path / "envelope.ndjson"
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return path


def test_normalize_maps_museum_and_skips_others(tmp_path):
    pois = list(normalize(_envelope(tmp_path), fetched_at=FIXED))
    assert len(pois) == 1  # no_geo and theme are skipped
    poi = pois[0]
    assert poi.source_id == "museum-nl"
    assert poi.source_record_id == "museum-nl:anne-frank-huis"
    assert poi.categories == ["museum"]
    assert poi.name == "Anne Frank Huis"
    assert abs(poi.lat - 52.375083) < 1e-9 and abs(poi.lon - 4.884031) < 1e-9
    assert poi.address is not None
    assert poi.address.street == "Westermarkt" and poi.address.housenumber == "20"
    assert poi.address.postcode == "1016 DK" and poi.address.city == "Amsterdam"
    assert poi.website == "https://www.annefrank.org"
    assert poi.tags["phone"] == "020 55 67 105"
    assert poi.tags["description"] == "Ruim 2 jaar zat Anne Frank ondergedoken."
    assert poi.field_provenance["name"] == "museum-nl"
    assert poi.field_provenance["address"] == "museum-nl"
    assert poi.field_provenance["website"] == "museum-nl"
    assert poi.field_provenance["tags"] == "museum-nl"
