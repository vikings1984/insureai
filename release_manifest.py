#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a truthful release manifest: quality passed != deployment verified."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "release_manifest.json"


def build_manifest(*, source_commit: str, site_url: str, quality_passed: bool = True) -> dict:
    return {
        "version": 1,
        "source_commit": source_commit or "unknown",
        "release_channel": "github_pages",
        "site_url": site_url,
        "quality_status": "passed" if quality_passed else "failed",
        "deployment_status": "pending",
        "deployment_verified": False,
        "deployment_note": "发布前质量门禁通过不代表生产站点已经完成部署与验收。",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    manifest = build_manifest(
        source_commit=os.environ.get("GITHUB_SHA", "unknown"),
        site_url=os.environ.get("SITE_URL", ""),
        quality_passed=True,
    )
    OUTPUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
