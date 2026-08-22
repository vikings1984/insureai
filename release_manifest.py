#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a truthful release manifest: quality passed != deployment verified."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from production_quality_gate import run_gate

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "release_manifest.json"
INDEX = ROOT / "index.html"


def build_release_marker(*, source_commit: str, audit_path: Path = ROOT / "audit_ledger.json") -> str:
    """Create a stable release identity from the source commit and audited lineage."""
    audit_sha = "missing-audit"
    if audit_path.exists():
        h = hashlib.sha256()
        with audit_path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        audit_sha = h.hexdigest()
    payload = f"{source_commit or 'unknown'}|{audit_sha}".encode("utf-8")
    return f"insureai-{hashlib.sha256(payload).hexdigest()[:16]}"


def build_manifest(*, source_commit: str, site_url: str, quality_passed: bool = True, release_channel: str = "cloudflare_workers", release_marker: str | None = None, production_quality_gate: dict | None = None) -> dict:
    marker = release_marker or build_release_marker(source_commit=source_commit)
    return {
        "version": 1,
        "source_commit": source_commit or "unknown",
        "release_channel": release_channel,
        "site_url": site_url,
        "release_marker": marker,
        "quality_status": "passed" if quality_passed else "failed",
        "production_quality_gate": production_quality_gate or {"status": "unknown", "failed_checks": []},
        "deployment_status": "pending",
        "deployment_verified": False,
        "deployment_note": "发布前质量门禁通过不代表生产站点已经完成部署与验收。",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def inject_release_marker(marker: str) -> None:
    """Make the release identity visible in the published HTML without exposing secrets."""
    if not INDEX.exists():
        return
    text = INDEX.read_text(encoding="utf-8")
    tag = f'<meta name="insureai-release-marker" content="{marker}">'
    pattern = re.compile(r'<meta\s+name=["\']insureai-release-marker["\'][^>]*>', re.I)
    if pattern.search(text):
        text = pattern.sub(tag, text, count=1)
    elif "</head>" in text.lower():
        match = re.search(r"</head>", text, re.I)
        assert match is not None
        text = text[: match.start()] + tag + "\n" + text[match.start() :]
    else:
        text = tag + "\n" + text
    INDEX.write_text(text, encoding="utf-8")


def main() -> None:
    source_commit = os.environ.get("GITHUB_SHA", "unknown")
    gate = run_gate(ROOT)
    marker = build_release_marker(source_commit=source_commit)
    if gate["status"] != "passed":
        raise SystemExit("Production quality gate failed: " + json.dumps(gate, ensure_ascii=False))

    manifest = build_manifest(
        source_commit=source_commit,
        site_url=os.environ.get("SITE_URL", ""),
        quality_passed=True,
        release_channel=os.environ.get("RELEASE_CHANNEL", "cloudflare_workers"),
        release_marker=marker,
        production_quality_gate=gate,
    )
    OUTPUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    inject_release_marker(marker)
    print(json.dumps({"manifest": manifest, "quality_gate": gate}, ensure_ascii=False))


if __name__ == "__main__":
    main()
