#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a module-level quality and optimization priority profile."""
from __future__ import annotations
import json
from pathlib import Path
from contract import ARTIFACT_VERSIONS
ROOT = Path(__file__).resolve().parent
ATTRIBUTION = ROOT / "feedback_attribution.json"
KG = ROOT / "knowledge_graph.json"
OUTPUT = ROOT / "module_health.json"
MODULES = ("event", "trust", "claims", "temporal", "decision", "counterfactual", "scenario", "knowledge_graph", "unknown")

def _module_rows(doc: dict):
    source = doc.get("modules", {})
    if isinstance(source, dict):
        return [{"module": k, **(v if isinstance(v, dict) else {})} for k, v in source.items()]
    return source if isinstance(source, list) else []

def build_health(doc: dict, kg_stats: dict | None = None) -> dict:
    rows = {m: {"module": m, "review_count": 0, "error_count": 0, "error_rate": 0.0, "confidence": 0.0, "health": "no_signal", "optimization_priority": 0} for m in MODULES}
    total_reviews = int(doc.get("reviewed_count") or 0)
    for src in _module_rows(doc):
        if not isinstance(src, dict):
            continue
        m = src.get("module")
        if m not in rows:
            continue
        r = rows[m]
        r["error_count"] = int(src.get("error_count") or 0)
        r["error_rate"] = float(src.get("error_rate") or 0.0)
        r["review_count"] = int(src.get("review_count") or total_reviews)
        r["confidence"] = float(src.get("confidence") or (1.0 if r["error_count"] > 0 and r["review_count"] else 0.0))
        if r["review_count"] == 0:
            r["health"] = "no_signal"
        elif r["error_rate"] >= 0.5:
            r["health"] = "critical"
        elif r["error_rate"] >= 0.25:
            r["health"] = "watch"
        else:
            r["health"] = "healthy"
        r["optimization_priority"] = min(100, round(r["error_rate"] * 70 + r["confidence"] * 20 + min(r["error_count"], 10)))
    ranked = sorted(rows.values(), key=lambda x: (x["optimization_priority"], x["error_count"]), reverse=True)
    # KG-3：知识图谱健康度来自 artifact 本体（节点/边计数），防再次静默为空。
    if kg_stats is not None:
        node_count = int(kg_stats.get("node_count") or 0)
        edge_count = int(kg_stats.get("edge_count") or 0)
        kg = rows["knowledge_graph"]
        kg["node_count"] = node_count
        kg["edge_count"] = edge_count
        kg["event_count"] = int(kg_stats.get("event_count") or 0)
        kg["latest_event_at"] = kg_stats.get("latest_event_at") or ""
        kg["review_count"] = 1
        kg["confidence"] = 1.0
        if node_count > 0 and edge_count > 0:
            kg["health"] = "healthy"
        else:
            kg["health"] = "critical"
            kg["error_count"] = 1
            kg["optimization_priority"] = 100
        ranked = sorted(rows.values(), key=lambda x: (x["optimization_priority"], x["error_count"]), reverse=True)
    return {"version": ARTIFACT_VERSIONS["module_health.json"], "principle": "先修最不稳定且证据充分的模块，而不是按直觉平均分配资源", "reviewed_count": total_reviews, "modules": list(rows.values()), "priority_order": [x["module"] for x in ranked]}

def main() -> None:
    if ATTRIBUTION.exists():
        try: doc = json.loads(ATTRIBUTION.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): doc = {"modules": []}
    else: doc = {"modules": []}
    kg_stats = None
    if KG.exists():
        try: kg_stats = (json.loads(KG.read_text(encoding="utf-8")) or {}).get("stats")
        except (OSError, json.JSONDecodeError): kg_stats = None
    OUTPUT.write_text(json.dumps(build_health(doc, kg_stats), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
