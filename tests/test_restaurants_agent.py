from datetime import datetime, timezone
from pathlib import Path

from sources.restaurants_agent.adapter import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "restaurants_curated.yaml"
FIXED = datetime(2026, 6, 19, tzinfo=timezone.utc)


def test_only_records_with_direct_signal_included():
    pois = list(normalize(FIXTURE, fetched_at=FIXED))
    assert len(pois) == 1  # "Café Zonder Bewijs" dropped (no direct signal)
    p = pois[0]
    assert p.categories == ["restaurant_kidfriendly"]
    assert p.name == "Restaurant De Speelhoek"
    assert p.source_id == "restaurants-agent"
    assert any(e["direct"] for e in p.tags["evidence"])
    assert p.website == "https://example.com/speelhoek"
    # stable id is deterministic
    assert list(normalize(FIXTURE, fetched_at=FIXED))[0].source_record_id == p.source_record_id
