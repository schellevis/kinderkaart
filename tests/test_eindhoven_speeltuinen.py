from datetime import datetime, timezone
import json
from pathlib import Path

from sources.eindhoven_speeltuinen.adapter import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "eindhoven_response.json"
FIXED = datetime(2026, 6, 19, tzinfo=timezone.utc)


def test_normalize():
    pois = list(normalize(FIXTURE, fetched_at=FIXED))
    assert len(pois) == 1
    assert pois[0].source_id == "eindhoven-speeltuinen"
    assert pois[0].categories == ["playground"]
    assert pois[0].name == "Speeltuin Stratum"
    assert abs(pois[0].lat - 51.441) < 1e-6 and abs(pois[0].lon - 5.478) < 1e-6


def test_normalize_skips_feature_without_coordinates(tmp_path: Path):
    path = tmp_path / "eindhoven_null_geometry.json"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": None,
                        "geo_point_2d": None,
                        "properties": {
                            "straatnaam": "Vuurpot",
                            "naam": "Speelplek zonder coordinaat",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert list(normalize(path, fetched_at=FIXED)) == []
