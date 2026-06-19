from datetime import datetime, timezone
from pathlib import Path

from sources.den_haag_speeltuinen.adapter import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "den_haag_response.json"
FIXED = datetime(2026, 6, 19, tzinfo=timezone.utc)


def test_point_and_polygon_centroid():
    pois = list(normalize(FIXTURE, fetched_at=FIXED))
    assert len(pois) == 2
    assert pois[0].categories == ["playground"]
    assert pois[0].source_id == "den-haag-speeltuinen"
    assert abs(pois[0].lat - 52.070) < 1e-6 and abs(pois[0].lon - 4.300) < 1e-6
    # polygon centroid ~ middle of the square
    assert abs(pois[1].lat - 52.071) < 1e-3 and abs(pois[1].lon - 4.301) < 1e-3
    # stable per-feature id derived from index when no source id field
    assert pois[0].source_record_id == "den-haag-speeltuinen:0"
