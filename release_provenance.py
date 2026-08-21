#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a privacy-safe release provenance record from release and audit artifacts."""
# release-provenance-v1: aggregate release, audit, and impact metadata without business content.
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "release_provenance.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_provenance(*, source_commit: str, site_url: str, root: Path = ROOT) -> dict:
    release_path = root / "release_manifest.json"
    audit_path = root / "audit_ledger.json"
    impact_path = root / "change_impact.json"
    release = _read_json(release_path)
    audit = _read_json(audit_path)
    impact = _read_json(impact_path) if impact_path.exists() else {}
    stages = audit.get("stages", [])
    return {
        "version": 1,
        "schema_version": "release-provenance-v1",
        "source_commit": source_commit or release.get("source_commit") or "unknown",
        "release_channel": release.get("release_channel", "github_pages"),
        "site_url": site_url or release.get("site_url", ""),
        "quality": {
            "status": release.get("quality_status", "unknown"),
            "audit_privacy": audit.get("privacy", "unknown"),
            "audit_stage_count": len(stages),
            "audit_artifact_count": len({row.get("artifact") for row in stages if row.get("artifact")}),
        },
        "impact": {
            "baseline_available": bool(impact.get("baseline_available", False)),
            "impacted_count": int(impact.get("impacted_count", 0)),
        },
        "deployment": {
            "status": release.get("deployment_status", "pending"),
            "verified": bool(release.get("deployment_verified", False)),
        },
        "artifacts": {
            "release_manifest_sha256": _sha256(release_path),
            "audit_ledger_sha256": _sha256(audit_path),
            "change_impact_sha256": _sha256(impact_path) if impact_path.exists() else None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    provenance = build_provenance(
        source_commit=os.environ.get("GITHUB_SHA", "unknown"),
        site_url=os.environ.get("SITE_URL", ""),
    )
    OUTPUT.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(provenance, ensure_ascii=False))


if __name__ == "__main__":
    main()
