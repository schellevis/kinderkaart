from __future__ import annotations

from pathlib import Path

from data_pipeline.manifest import load_manifest


def build_license_report(source_manifest_paths: list[Path]) -> dict:
    report = {}
    for p in sorted(source_manifest_paths):
        m = load_manifest(p)
        report[m.id] = {
            "license": m.license,
            "license_url": m.license_url,
            "attribution": m.attribution,
            "evidence_date": m.license_evidence_date.isoformat(),
            "republication_terms": m.republication_terms,
        }
    return report
