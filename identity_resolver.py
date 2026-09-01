#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Identity Resolver — Event OS 主脊柱 S2（全局事件身份解析层）。

把分散在各模块的"局部身份"统一解析到 canonical_event_id：
- event_id（各事件携带，contract.py 保证唯一）
- alias（event_id_aliases.json 登记的跨来源 / 历史 id）
- canonical 自身
- optimization_backlog.fingerprint（模块级质量趋势去重键）：本身不是事件身份，
  只通过"证据映射表" resolver_fingerprint_map.json 桥接到 canonical
  （证据不足 → None，不伪造）。

纪律（继承项目主线）：
- 只读既有事实；propose_* 只产出候选合并（observation），不执行合并。
  合并（event_registry.merge）需 S2 证据阈值 + 人工 review，不在本模块自动发生。
- fail-closed：validate 对任何结构破坏抛 AssertionError。
- observation/conclusion 分离：candidate_merges 标注 status="proposed"，结论待证据。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from event_registry import VERSION as REGISTRY_VERSION, resolve as _registry_resolve

ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / "canonical_events.json"
FINGERPRINT_MAP = ROOT / "resolver_fingerprint_map.json"
REPORT = ROOT / "resolver_report.json"

VERSION = "ir-v1.0"
PRINCIPLE = (
    "单一事实源：所有模块引用 canonical_event_id；resolver 只解析、不发明身份。"
    "合并与分裂由证据 + 人工 review 决定，resolver 仅产出候选。"
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_registry() -> dict:
    """加载 S1 注册表；缺失即返回空 dict（不伪造）。"""
    return _load(REGISTRY)


def resolve(ref: str, registry: dict | None = None) -> str | None:
    """任意引用（event_id / alias / canonical）→ canonical_event_id，或 None。"""
    if not ref:
        return None
    if registry is None:
        registry = load_registry()
    return _registry_resolve(ref, registry)


def classify(ref: str, registry: dict | None = None) -> str:
    """返回引用的类型：canonical / event_id / alias / unknown。"""
    if not ref:
        return "unknown"
    if registry is None:
        registry = load_registry()
    if ref in registry.get("canonical_events", {}):
        return "canonical"
    if ref in registry.get("by_event_id", {}):
        return "event_id"
    if ref in registry.get("aliases", {}):
        return "alias"
    return "unknown"


def load_fingerprint_map() -> dict:
    """加载 curated fingerprint→canonical 证据映射；缺失或结构异常返回空。"""
    raw = _load(FINGERPRINT_MAP)
    m = raw.get("map")
    return m if isinstance(m, dict) else {}


def resolve_fingerprint(fp: str, fmap: dict | None = None) -> str | None:
    """模块质量 fingerprint 桥接到 canonical；无证据 → None（不伪造）。"""
    if not fp:
        return None
    if fmap is None:
        fmap = load_fingerprint_map()
    return fmap.get(fp)


def collect_references() -> list[str]:
    """扫描既有 artifact 中所有 event_id 引用，返回去重后的有序列表。

    覆盖：p2_daily_brief.brief / review_queue.items / second_brain.entity_threads。
    """
    refs: set[str] = set()
    db = _load(ROOT / "p2_daily_brief.json")
    for e in (db.get("brief") or []):
        if e.get("event_id"):
            refs.add(str(e["event_id"]))
    rq = _load(ROOT / "review_queue.json")
    for e in (rq.get("items") or []):
        if e.get("event_id"):
            refs.add(str(e["event_id"]))
    sb = _load(ROOT / "second_brain.json")
    for th in (sb.get("entity_threads") or []):
        for ev in (th.get("events") or []):
            if ev.get("event_id"):
                refs.add(str(ev["event_id"]))
    return sorted(refs)


def resolve_references(refs: list[str], registry: dict | None = None) -> dict[str, str | None]:
    """批量解析引用 → {ref: canonical_or_None}。"""
    if registry is None:
        registry = load_registry()
    return {r: resolve(r, registry) for r in refs}


def propose_merges_from_entity_threads(
    entity_threads: list[dict], registry: dict | None = None, min_shared: int = 2
) -> list[dict]:
    """按"共享实体"提出候选合并（observation，不执行）。

    同一实体出现在 ≥min_shared 个不同 canonical event 时，记为候选合并组，
    证据 = 实体共现。结论（是否真为同一事件）需 S2 证据阈值 + 人工 review。
    """
    if registry is None:
        registry = load_registry()
    candidates: list[dict] = []
    for th in entity_threads or []:
        entity = th.get("entity")
        etype = th.get("type")
        eids = [ev.get("event_id") for ev in (th.get("events") or []) if ev.get("event_id")]
        if not entity or len(eids) < min_shared:
            continue
        cev_ids = sorted({c for c in (resolve(e, registry) for e in eids) if c})
        if len(cev_ids) < min_shared:
            continue
        candidates.append({
            "entity": entity,
            "type": etype,
            "canonical_ids": cev_ids,
            "event_ids": eids,
            "evidence": f"实体共现（{entity} 跨 {len(cev_ids)} 个 canonical event）",
            "status": "proposed",
        })
    return candidates


def build_report(
    entity_threads: list[dict] | None = None,
    refs: list[str] | None = None,
    registry: dict | None = None,
    generated_at: str | None = None,
) -> dict:
    generated_at = generated_at or _now()
    if registry is None:
        registry = load_registry()
    if refs is None:
        refs = collect_references()
    if entity_threads is None:
        entity_threads = _load(ROOT / "second_brain.json").get("entity_threads") or []

    resolved = resolve_references(refs, registry)
    unresolved = sorted(r for r, c in resolved.items() if not c)
    candidates = propose_merges_from_entity_threads(entity_threads, registry)

    fmap = load_fingerprint_map()
    # fingerprint 桥接：当前只统计 map 中已映射到 canonical 的条目（证据驱动）
    mapped = [fp for fp, cev in fmap.items() if cev in registry.get("canonical_events", {})]

    return {
        "version": VERSION,
        "registry_version": registry.get("version"),
        "generated_at": generated_at,
        "principle": PRINCIPLE,
        "total_references": len(refs),
        "resolved": len(refs) - len(unresolved),
        "unresolved": len(unresolved),
        "unresolved_rate": round(len(unresolved) / len(refs), 4) if refs else 0.0,
        "unresolved_samples": unresolved[:20],
        "candidate_merges": {
            "count": len(candidates),
            "status": "proposed",  # observation，不执行
            "items": candidates[:50],
        },
        "fingerprint_bridge": {
            "mapped": len(mapped),
            "total_in_map": len(fmap),
            "note": "fingerprint 为模块级质量趋势键，仅经证据映射桥接到 canonical；无映射→不解析（不伪造）",
        },
        "open_note": (
            "候选合并为 observation，需 S2 证据阈值 + 人工 review 方可执行 event_registry.merge；"
            "fingerprint 桥接待 review/decision 落证据后填充 resolver_fingerprint_map.json。"
        ),
    }


def validate(report: dict) -> None:
    """fail-closed：任何结构破坏抛 AssertionError。"""
    assert report.get("version") == VERSION, f"version 不符: {report.get('version')}"
    for key in ("generated_at", "total_references", "resolved", "unresolved", "candidate_merges"):
        assert key in report, f"缺关键字段: {key}"
    assert report["resolved"] + report["unresolved"] == report["total_references"], (
        f"计数不自洽: {report['resolved']}+{report['unresolved']} != {report['total_references']}"
    )
    assert report["unresolved_rate"] >= 0 and report["unresolved_rate"] <= 1, "unresolved_rate 越界"
    cm = report["candidate_merges"]
    assert cm.get("status") == "proposed", "候选合并状态必须为 proposed（不自动执行）"
    for item in cm.get("items", []):
        assert item.get("status") == "proposed", "候选合并项不得标记为已执行"


def _ensure_fingerprint_map() -> None:
    """首次运行确保证据映射表基线存在（空），便于 S2 增量填充。"""
    if not FINGERPRINT_MAP.exists():
        FINGERPRINT_MAP.write_text(
            json.dumps({"version": VERSION, "generated_at": _now(), "map": {}}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def build_artifacts(generated_at: str | None = None) -> dict:
    """扫描既有 artifact → 构建并落盘 resolver_report.json（+ 确保 fingerprint 映射基线）。"""
    _ensure_fingerprint_map()
    registry = load_registry()
    entity_threads = _load(ROOT / "second_brain.json").get("entity_threads") or []
    report = build_report(entity_threads=entity_threads, registry=registry, generated_at=generated_at)
    validate(report)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    report = build_artifacts()
    cm = report["candidate_merges"]
    print(
        f"Identity Resolver: refs={report['total_references']} resolved={report['resolved']} "
        f"unresolved={report['unresolved']} ({report['unresolved_rate']*100:.1f}%) · "
        f"candidate_merges={cm['count']} · fingerprint_mapped={report['fingerprint_bridge']['mapped']}"
    )


if __name__ == "__main__":
    main()
