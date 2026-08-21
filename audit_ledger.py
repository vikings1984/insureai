#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create a privacy-preserving lineage ledger for each intelligence build."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "audit_ledger.json"
STAGES = (
    ("collect", "data.json", "collector"),
    ("intelligence", "intelligence.json", "intelligence"),
    ("trust", "intelligence.json", "trust"),
    ("claims", "intelligence.json", "claims"),
    ("temporal", "intelligence.json", "temporal"),
    ("decision", "intelligence.json", "decision"),
    ("counterfactual", "counterfactual.json", "counterfactual"),
    ("scenario", "scenario.json", "scenario"),
    ("scenario_matrix", "scenario_matrix.json", "scenario_matrix"),
    ("action_triggers", "action_triggers.json", "action_triggers"),
    ("execution_readiness", "execution_readiness.json", "execution_readiness"),
)

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _counts(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    counts = {}
    if isinstance(data, dict):
        for key in ("news", "events", "results", "scenarios", "items"):
            value = data.get(key)
            if isinstance(value, list):
                counts[key] = len(value)
        if data.get("version") is not None:
            counts["version"] = data["version"]
    return counts

def build_ledger() -> dict:
    records = []
    for stage, filename, producer in STAGES:
        path = ROOT / filename
        if path.exists():
            records.append({
                "stage": stage,
                "producer": producer,
                "artifact": filename,
                "sha256": sha256_file(path),
                "counts": _counts(path),
            })
    return {
        "version": 1,
        "schema_version": "audit-ledger-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "privacy": "hashes_and_metadata_only",
        "stages": records,
    }

def main() -> None:
    ledger = build_ledger()
    OUTPUT.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Audit ledger: {len(ledger['stages'])} stages")

if __name__ == "__main__":
    main()
