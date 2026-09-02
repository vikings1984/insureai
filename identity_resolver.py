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

from event_registry import (
    VERSION as REGISTRY_VERSION,
    resolve as _registry_resolve,
    event_type_domain,
    may_auto_merge,
    load_registry as _er_load_registry,
)

ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / "canonical_events.json"
FINGERPRINT_MAP = ROOT / "resolver_fingerprint_map.json"
REPORT = ROOT / "resolver_report.json"

VERSION = "ir-v1.1"  # X2：新增分区感知解析（partition_classify / resolve_with_partition / 跨 domain 合并门 / generic_review）
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


def partition_classify(cev_id: str, registry: dict | None = None) -> dict:
    """返回某 canonical event 的分区属性（单一事实源 + 按 event_type 分区解析的落地）。

    - domain：acquisition / regulatory / catastrophe / other（来自 event_type_domain）
    - canonicalize：该 domain 是否允许自动归并（acquisition/regulatory=True，其余 alias-only=False）
    无证据（未知 CE）→ 一律返回不可解析，不伪造。
    """
    if not cev_id:
        return {"domain": None, "canonicalize": False, "event_type": None}
    if registry is None:
        registry = load_registry()
    ce = registry.get("canonical_events", {}).get(cev_id)
    if not ce:
        return {"domain": None, "canonicalize": False, "event_type": None}
    et = ce.get("event_type")
    return {
        "domain": event_type_domain(et),
        "canonicalize": may_auto_merge(et),
        "event_type": et,
    }


def resolve_with_partition(ref: str, registry: dict | None = None) -> dict:
    """分区感知解析：返回 canonical_event_id 及其 domain / canonicalize 标志。"""
    cev = resolve(ref, registry)
    if cev:
        part = partition_classify(cev, registry)
    else:
        part = {"domain": None, "canonicalize": False, "event_type": None}
    return {
        "ref": ref,
        "resolved": cev is not None,
        "canonical_event_id": cev,
        "domain": part["domain"],
        "canonicalize": part["canonicalize"],
    }


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
    """按"共享实体"提出候选合并（observation，不执行），并按 event_type 分区门过滤。

    同一实体出现在 ≥min_shared 个不同 canonical event 时，记为候选合并组，
    证据 = 实体共现。结论（是否真为同一事件）需 S2 证据阈值 + 人工 review。

    分区门（§9.9 S2）：跨 domain 的共现实体**不**提议合并——不同 event_type 的共现实体
    应各自为 CE，不得伪造跨类合并（与 should_merge 的"跨类型永不合并"一致）。同 domain
    内仍按观察提出，待证据 + 人工 review 决定。
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
        # 分区门：跨 domain 共现 → 拒绝合并（各自保留 CE）
        domains = {partition_classify(c, registry)["domain"] for c in cev_ids if c}
        if len(domains) > 1:
            continue
        candidates.append({
            "entity": entity,
            "type": etype,
            "canonical_ids": cev_ids,
            "event_ids": eids,
            "domain": sorted(domains)[0] if domains else None,
            "evidence": f"实体共现（{entity} 跨 {len(cev_ids)} 个 canonical event）",
            "status": "proposed",
        })
    return candidates


def collect_generic_only_threads(
    entity_threads: list[dict], registry: dict | None = None
) -> list[dict]:
    """收集"仅含通用实体、无具体 event_id"的线程 → 进复核队列，不进 CE（§9.9 S2）。

    generic_entities_only：实体出现了但没有依附于任何具体事件（event_id 缺失），
    不应被解析为 canonical event 身份，交由人工复核判定归属。
    """
    _ = registry  # 分区解析保持只读；此函数不依赖 registry
    out: list[dict] = []
    for th in entity_threads or []:
        evs = th.get("events") or []
        if not evs:
            continue
        if all(not ev.get("event_id") for ev in evs):
            out.append({
                "entity": th.get("entity"),
                "type": th.get("type"),
                "into_ce": False,
                "reason": "generic_entities_only（无具体 event_id）→ 进复核不进 CE",
            })
    return out


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
    generic_review = collect_generic_only_threads(entity_threads, registry)

    fmap = load_fingerprint_map()
    # fingerprint 桥接：当前只统计 map 中已映射到 canonical 的条目（证据驱动）
    mapped = [fp for fp, cev in fmap.items() if cev in registry.get("canonical_events", {})]

    # 分区统计：已解析引用按 domain 计数（acquisition / regulatory / catastrophe / other）
    partition_stats: dict[str, int] = {}
    for r in refs:
        rp = resolve_with_partition(r, registry)
        if rp["resolved"]:
            d = rp["domain"] or "other"
            partition_stats[d] = partition_stats.get(d, 0) + 1

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
        "partition_stats": partition_stats,
        "candidate_merges": {
            "count": len(candidates),
            "status": "proposed",  # observation，不执行
            "items": candidates[:50],
        },
        "generic_review": {
            "count": len(generic_review),
            "items": generic_review[:50],
        },
        "fingerprint_bridge": {
            "mapped": len(mapped),
            "total_in_map": len(fmap),
            "note": "fingerprint 为模块级质量趋势键，仅经证据映射桥接到 canonical；无映射→不解析（不伪造）",
        },
        "open_note": (
            "候选合并为 observation，需 S2 证据阈值 + 人工 review 方可执行 event_registry.merge；"
            "generic_entities_only 进复核不进 CE；fingerprint 桥接待 review/decision 落证据后填充 resolver_fingerprint_map.json。"
        ),
    }


def validate(report: dict) -> None:
    """fail-closed：任何结构破坏抛 AssertionError。"""
    assert report.get("version") == VERSION, f"version 不符: {report.get('version')}"
    for key in ("generated_at", "total_references", "resolved", "unresolved",
                "candidate_merges", "generic_review", "partition_stats"):
        assert key in report, f"缺关键字段: {key}"
    assert report["resolved"] + report["unresolved"] == report["total_references"], (
        f"计数不自洽: {report['resolved']}+{report['unresolved']} != {report['total_references']}"
    )
    assert report["unresolved_rate"] >= 0 and report["unresolved_rate"] <= 1, "unresolved_rate 越界"
    cm = report["candidate_merges"]
    assert cm.get("status") == "proposed", "候选合并状态必须为 proposed（不自动执行）"
    for item in cm.get("items", []):
        assert item.get("status") == "proposed", "候选合并项不得标记为已执行"
    gr = report["generic_review"]
    assert isinstance(gr.get("count"), int) and isinstance(gr.get("items", []), list), "generic_review 结构错"
    assert isinstance(report["partition_stats"], dict), "partition_stats 必须为 dict"


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
    ps = report["partition_stats"]
    print(
        f"Identity Resolver v{VERSION}: refs={report['total_references']} resolved={report['resolved']} "
        f"unresolved={report['unresolved']} ({report['unresolved_rate']*100:.1f}%) · "
        f"partition={ps} · candidate_merges={cm['count']} · generic_review={report['generic_review']['count']} · "
        f"fingerprint_mapped={report['fingerprint_bridge']['mapped']}"
    )


if __name__ == "__main__":
    main()
