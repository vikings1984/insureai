#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-3 Atomic Publish.

Pipeline (plan §十一 / §二十一 P0-3)::

    BUILD -> staging/ -> Quality Gate -> Manifest -> Hash Check -> Atomic Publish

Only when the *whole* Release Bundle passes the final quality gate is it allowed
to become the production version. If any module fails, the previously published
production state is **never** partially overwritten.

Why this matters
----------------
The previous pipeline committed ``data.json`` in the ``collect`` job and only
committed derived intelligence artifacts at the very end of ``analyze``. When a
later stage (e.g. the test gate) failed, production was left with a *new*
``data.json`` paired with *stale* intelligence — exactly the cross-version
mix the plan calls out. Atomic Publish fixes this by:

1. Building every production artifact into ``staging/`` (with provenance stamps).
2. Running the fail-closed quality gate against ``staging/`` (not root).
3. Writing a ``manifest.json`` enumerating every bundled artifact with its sha256.
4. Swapping ``staging/`` -> root **only** after the gate and manifest hashes agree,
   with a full rollback so a crash mid-swap never leaves a half-written production.

The git commit in CI remains the final atomic boundary; this module guarantees
that what gets committed is a self-consistent, gate-passed bundle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from contract import SCHEMA_VERSIONS
from production_quality_gate import run_gate
from run import Run, create_run, stamp_provenance

ROOT = Path(__file__).resolve().parent
STAGING = ROOT / "staging"
MANIFEST_NAME = "manifest.json"

# The complete set of artifacts that constitutes one production release bundle.
# ``data.json`` is intentionally included so raw input and derived intelligence are
# always published together (no new-data + stale-intelligence mix).
PRODUCTION_ARTIFACTS = (
    "data.json",
    "intelligence.json",
    "claims.json",
    "calibration.json",
    "counterfactual.json",
    "scenario.json",
    "scenario_matrix.json",
    "action_triggers.json",
    "execution_readiness.json",
    "audit_ledger.json",
    "change_impact.json",
    "review_queue.json",
    "feedback_attribution.json",
    "module_health.json",
    "module_health_history.json",
    "module_health_trend.json",
    "trend_attribution.json",
    "radar.json",
    "optimization_backlog.json",
    "optimization_backlog_history.json",
    "decision_stability.json",
    "decision_history.json",
    "decision_credibility.json",
    "daily_risk_radar.json",
    "owner_risk_view.json",
    "freshness.json",
    "evidence_availability.json",
    "executive_terminal.json",
    "knowledge_graph.json",
    "p2_daily_brief.json",
    "release_manifest.json",
    "release_provenance.json",
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _restamp_release_manifest(staging: Path, run: Run) -> None:
    """把**本轮** run_id 盖到站点发布清单上，并同步 release_provenance 里记录的清单哈希。

    为什么必须在这里补一刀
    ----------------------
    daily-collect 的 ``Restamp final release manifest`` 步骤跑在 ``atomic_publish.py
    release`` **之前**；那一刻 ``run.json`` 还没被 ``publish()`` 写出，工作区里的产物
    还是上一次 checkout 的旧版，所以 ``release_manifest.py`` 只能取到**上一轮**的
    run_id（2026-10-01 生产实跑：release_manifest.run_id = run_20261001_082256_5ea0eb，
    而同轮 run.json / claims.json / manifest._provenance 全是 run_20261001_122353_f4e1e4）。

    这里在 build 阶段（stamp 之后、build_manifest 算包内哈希之前）把顶层 ``run_id``
    换成当前 run，并把 ``release_provenance.json`` 里记录的
    ``artifacts.release_manifest_sha256`` 同步为新清单的哈希——否则包内两份文件会
    自相矛盾，部署验证比对比对会失败。
    """
    manifest_path = staging / "release_manifest.json"
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(manifest, dict) or manifest.get("run_id") == run.run_id:
        return
    manifest["run_id"] = run.run_id
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    prov_path = staging / "release_provenance.json"
    if not prov_path.exists():
        return
    try:
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    artifacts = prov.get("artifacts") if isinstance(prov, dict) else None
    if isinstance(artifacts, dict) and "release_manifest_sha256" in artifacts:
        artifacts["release_manifest_sha256"] = _sha256_file(manifest_path)
        prov_path.write_text(json.dumps(prov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_staging(*, root: Path = ROOT, staging: Path = STAGING, run: Run | None = None) -> Run:
    """Copy the production artifact set into ``staging/``, stamping provenance.

    Optional artifacts that are missing on disk are skipped silently; presence is
    enforced later by the quality gate, not here.
    """
    run = run or create_run(root=root)
    staging.mkdir(parents=True, exist_ok=True)
    for name in PRODUCTION_ARTIFACTS:
        src = root / name
        if not src.exists():
            continue
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Copy non-JSON / unreadable artifacts verbatim so the bundle stays complete.
            shutil.copy2(src, staging / name)
            continue
        if isinstance(data, dict):
            stamp_provenance(data, run)
        (staging / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # 清单在 daily-collect 里生成时拿不到本轮 run_id（见 _restamp_release_manifest 的说明），
    # 这里补盖，且必须在 run.save(staging) 与 build_manifest() 之前，保证包内自洽。
    _restamp_release_manifest(staging, run)
    run.save(staging)
    return run


def build_manifest(*, staging: Path = STAGING) -> dict:
    """Compute per-artifact sha256 + quality-gate summary into ``staging/manifest.json``."""
    run = Run.load(staging)
    if run is None:
        raise ValueError("no run found in staging; run build_staging first")
    gate = run_gate(staging)
    entries = []
    for name in PRODUCTION_ARTIFACTS:
        p = staging / name
        if p.exists():
            entries.append({"path": name, "sha256": _sha256_file(p), "bytes": p.stat().st_size})
    manifest = {
        "version": SCHEMA_VERSIONS.get("release_manifest", 1),
        "kind": "release_bundle",
        "run_id": run.run_id,
        "build_sha": run.build_sha,
        "schema_version": run.schema_version,
        "engine_version": run.engine_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quality_gate": {"status": gate["status"], "failed_checks": gate.get("failed_checks", [])},
        "artifacts": entries,
        "artifact_count": len(entries),
    }
    (staging / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def validate_bundle(*, staging: Path = STAGING) -> dict:
    """Fail-closed bundle check: quality gate must pass AND every manifest hash must match.

    Raises ``ValueError`` on any violation.
    """
    run = Run.load(staging)
    if run is None:
        raise ValueError("no run found in staging; run build_staging first")
    gate = run_gate(staging)
    if gate["status"] != "passed":
        raise ValueError("quality gate failed: " + json.dumps(gate.get("failed_checks"), ensure_ascii=False))
    manifest_path = staging / MANIFEST_NAME
    if not manifest_path.exists():
        raise ValueError("manifest missing; run build_manifest first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("run_id") != run.run_id:
        raise ValueError("manifest run_id does not match current staging run")
    for entry in manifest["artifacts"]:
        p = staging / entry["path"]
        if not p.exists() or _sha256_file(p) != entry["sha256"]:
            raise ValueError(f"manifest hash mismatch for {entry['path']}")
    return gate


def publish(*, staging: Path = STAGING, root: Path = ROOT) -> dict:
    """Atomically swap ``staging/`` -> ``root`` after validation.

    Guarantees: either the full bundle lands in root, or root is left exactly as it
    was before (rollback). Returns a summary on success.
    """
    run = Run.load(staging)
    if run is None:
        raise ValueError("no run found in staging; run build_staging first")
    validate_bundle(staging=staging)

    targets = [p.name for p in staging.glob("*.json")]
    backup_dir = Path(tempfile.mkdtemp(prefix="insureai_publish_rollback_"))
    # Back up every target that already exists in root BEFORE touching anything.
    pre_existing = {name for name in targets if (root / name).exists()}
    try:
        for name in pre_existing:
            shutil.copy2(root / name, backup_dir / name)
    except Exception as exc:
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise RuntimeError(f"atomic publish aborted while snapshotting root: {exc}") from exc

    try:
        for name in targets:
            shutil.copy2(staging / name, root / name)
    except Exception as exc:  # rollback: restore root to its pre-publish state
        for name in pre_existing:
            bk = backup_dir / name
            if bk.exists():
                shutil.copy2(bk, root / name)
        for name in (set(targets) - pre_existing):
            if (root / name).exists():
                (root / name).unlink()
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise RuntimeError(f"atomic publish aborted, root restored: {exc}") from exc

    shutil.rmtree(backup_dir, ignore_errors=True)
    run.ended_at = datetime.now(timezone.utc).isoformat()
    run.status = "passed"
    run.save(root)
    return {"status": "published", "run_id": run.run_id, "artifact_count": len(targets)}


def release(*, root: Path = ROOT, staging: Path = STAGING) -> dict:
    """One-shot: build -> manifest -> validate -> publish."""
    run = create_run(root=root)
    build_staging(root=root, staging=staging, run=run)
    build_manifest(staging=staging)
    return publish(staging=staging, root=root)


def _cli() -> None:
    ap = argparse.ArgumentParser(description="InsureAI Atomic Publish")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--staging", default=str(STAGING))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("manifest")
    sub.add_parser("validate")
    sub.add_parser("publish")
    sub.add_parser("verify")
    sub.add_parser("release")
    args = ap.parse_args()
    root = Path(args.root)
    staging = Path(args.staging)
    if args.cmd == "build":
        run = build_staging(root=root, staging=staging)
        print(json.dumps({"status": "staged", "run_id": run.run_id}, ensure_ascii=False))
    elif args.cmd == "manifest":
        manifest = build_manifest(staging=staging)
        print(json.dumps(manifest, ensure_ascii=False))
    elif args.cmd == "validate":
        gate = validate_bundle(staging=staging)
        print(json.dumps({"status": "valid", "gate": gate["status"]}, ensure_ascii=False))
    elif args.cmd == "publish":
        out = publish(staging=staging, root=root)
        print(json.dumps(out, ensure_ascii=False))
    elif args.cmd == "verify":
        run = build_staging(root=root, staging=staging)
        build_manifest(staging=staging)
        gate = validate_bundle(staging=staging)
        print(json.dumps({"status": "verified", "run_id": run.run_id, "gate": gate["status"], "artifacts": len(PRODUCTION_ARTIFACTS)}, ensure_ascii=False))
    elif args.cmd == "release":
        out = release(root=root, staging=staging)
        print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    _cli()
