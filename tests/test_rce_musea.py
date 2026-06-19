from datetime import datetime, timezone
from pathlib import Path

from sources.rce_musea.adapter import MANIFEST, normalize

FIXTURE = Path(__file__).parent / "fixtures" / "rce_musea_response.json"
FIXED = datetime(2026, 6, 19, tzinfo=timezone.utc)


def test_normalize_reprojects_and_maps():
    pois = list(normalize(FIXTURE, fetched_at=FIXED))
    assert len(pois) == 2
    p = pois[0]
    assert p.source_id == "rce-musea"
    assert p.source_record_id == "overzichtmusea.1"
    assert p.name == "Rijksmuseum"
    assert p.categories == ["museum"]
    assert p.country == "nl"
    # RD (121687, 487462) ~ Amsterdam centre
    assert abs(p.lat - 52.36) < 0.05
    assert abs(p.lon - 4.89) < 0.05
    assert p.address == {"city": "Amsterdam", "postcode": "1071 ZC"}
    assert p.field_provenance["lat"] == "rce-musea"


def test_manifest_country_and_id():
    assert MANIFEST.id == "rce-musea"
