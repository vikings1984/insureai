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
from contract import RELEASE_CHANNEL, SCHEMA_VERSIONS

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


def build_manifest(*, source_commit: str, site_url: str, quality_passed: bool = True, release_channel: str = RELEASE_CHANNEL, release_marker: str | None = None, production_quality_gate: dict | None = None, run_id: str | None = None) -> dict:
    marker = release_marker or build_release_marker(source_commit=source_commit)
    return {
        "version": SCHEMA_VERSIONS["release_manifest"],
        "run_id": run_id,
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


# atomic_publish.publish() 对 staging 里每个 dict 产物盖 _provenance 章，最后才 run.save(root)。
# 因此产物上的 _provenance.run_id 是比 run.json 更早可得、且同样准确的溯源来源。
_PROVENANCE_ARTIFACTS = (
    "intelligence.json",
    "data.json",
    "claims.json",
    "audit_ledger.json",
    "decisions_ledger.json",
    "executive_terminal.json",
)


def _run_id_from_artifacts(root: Path) -> str | None:
    """从已盖章的产物里取 run_id；取不到返回 None（绝不编造）。"""
    for name in _PROVENANCE_ARTIFACTS:
        path = root / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            run_id = data.get("_provenance", {}).get("run_id")
            if run_id:
                return run_id
    return None


def _read_run_id(root: Path = ROOT) -> str | None:
    """取当前构建快照的 run_id；确实拿不到时返回 None，而不是猜一个。

    两级来源，优先级 run.json > 产物 _provenance：
    - run.json 由 atomic_publish.publish() 在**末尾**写入（run.save(root)），
      而 daily-collect 的 "Restamp final release manifest" 排在该步骤之前，
      此刻 run.json 尚不存在；
    - 但 publish 早已把 _provenance 盖到每个产物上，其 run_id 与 run.json 同源同值。
      2026-10-01 生产实跑即因此出现 release_manifest.run_id 恒为 null
      （manifest generated_at 00:07:29.633 < run.json started_at 00:07:29.851）。
      加此回退层后，取值不再依赖步骤顺序，门禁语义不变。

    注意：本函数跑在 publish 之前，取到的必然是**上一轮**的 run_id（2026-10-01 实测
    082256 vs 本轮 122353）。最终正确的 run_id 由 atomic_publish.build_staging() 在
    build 阶段补盖（_restamp_release_manifest），并同步重算 release_provenance 里记录的
    release_manifest_sha256——所以这里只负责"不留空值"，不负责"一定是本轮"。
    """
    run_path = root / "run.json"
    if run_path.exists():
        try:
            run_id = json.loads(run_path.read_text(encoding="utf-8")).get("run_id")
            if run_id:
                return run_id
        except (OSError, json.JSONDecodeError):
            pass
    return _run_id_from_artifacts(root)


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
        release_channel=os.environ.get("RELEASE_CHANNEL", RELEASE_CHANNEL),
        release_marker=marker,
        production_quality_gate=gate,
        run_id=_read_run_id(ROOT),
    )
    OUTPUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    inject_release_marker(marker)
    print(json.dumps({"manifest": manifest, "quality_gate": gate}, ensure_ascii=False))


if __name__ == "__main__":
    main()
