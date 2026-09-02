#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canonical Event Registry — Event OS 主链脊柱（S1）。

设计原则（继承项目纪律）：
- 单一事实源：所有模块引用 canonical_event_id，不再各自持有 event_id / fingerprint 版本。
- 只读既有事实，不伪造身份：build 仅从已存在的 event_id 自举（1:1 初始），
  跨事件归并（merge）由 S2 Resolver 基于真实证据触发，本模块只提供安全操作原语。
- 确定性：canonical_event_id 由 event_id 稳定派生（sha256 截断），可重放。
- fail-closed：validate 对任何结构破坏（重复 id / 悬空引用 / 源未覆盖）抛错。

v1 范围：注册表数据结构 + resolve/upsert/alias/merge/split/migrate 原语 + 从
daily_brief / review_queue 自举构建。阶段（stage）与生命周期留待 S3 填充。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "canonical_events.json"
ALIASES = ROOT / "event_id_aliases.json"

VERSION = "er-v1.1"
PRINCIPLE = (
    "单一事实源：所有模块引用 canonical_event_id；跨模块统一事件身份，"
    "禁止各自持有版本。身份归并只基于真实证据，不伪造。"
)

# X2（评审修订）：event_type 分区策略 —— 先窄后宽，禁止全量通用归并。
# canonicalize=True 的类型才可自动归并；alias_only=True 的类型只做别名、不自动 merge；
# 其余一律不自动归并（防 false merge，见 canonical_annotation_set.json 质量门）。
CANONICALIZE_POLICY = {
    "acquisition":     {"canonicalize": True,  "alias_only": False},
    "regulatory":      {"canonicalize": True,  "alias_only": False},
    "product":         {"canonicalize": False, "alias_only": True},
    "personnel":       {"canonicalize": False, "alias_only": True},
    "industry_update": {"canonicalize": False, "alias_only": True},
    "other":           {"canonicalize": False, "alias_only": True},
}
MANUAL_SPLIT_REQUIRED = True

# event_type → lifecycle.domain（S3 插件化生命周期的基础；other/catastrophe 本期不自动归并）
EVENT_TYPE_DOMAIN = {
    "acquisition": "acquisition",
    "merger": "acquisition",
    "regulatory": "regulatory",
    "regulation": "regulatory",
    "catastrophe": "catastrophe",
    "catastrophe_risk": "catastrophe",
}


def event_type_domain(event_type: str) -> str:
    return EVENT_TYPE_DOMAIN.get(event_type) or "other"


def may_auto_merge(event_type: str) -> bool:
    """只有 acquisition/regulatory 可自动归并；其余（含 product/personnel/industry_update）只做别名。"""
    return bool(CANONICALIZE_POLICY.get(event_type, {}).get("canonicalize"))


def _title_jaccard(a: str, b: str) -> float:
    sa, sb = set(a.lower().split()), set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def should_merge(a: dict, b: dict) -> bool:
    """S2 自动归并的单一决策点（质量门可调）：同 event_type 且（同 key_entity 或标题 Jaccard≥0.85）。

    - 不同 event_type / alias-only 类型 → 永不自动归并（false merge 防护）；
    - key_entity 显式给出时以它为准（最稳），否则退化为高标题重叠；
    - 一方有 key_entity、另一方没有 → 不臆测合并。
    """
    ta, tb = a.get("event_type"), b.get("event_type")
    if not ta or not tb or ta != tb:
        return False
    if not may_auto_merge(ta):
        return False
    ka, kb = a.get("key_entity"), b.get("key_entity")
    if ka and kb:
        return ka == kb
    if ka or kb:
        return False
    return _title_jaccard(a.get("title", ""), b.get("title", "")) >= 0.85


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_id(event_id: str) -> str:
    """由 event_id 稳定派生 canonical_event_id（确定性、可重放）。"""
    return "cev_" + hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:12]


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _norm_event(e: dict, origin: str) -> dict:
    """把任意来源的 event 条目收敛为最小表示；缺 event_id 直接返回 None（不伪造）。"""
    eid = e.get("event_id")
    if not eid:
        return None
    return {
        "event_id": str(eid),
        "origin": origin,
        "title": e.get("title") or "",
        "topic": e.get("topic") or "",
        "event_type": e.get("event_type") or "",
        "key_entity": e.get("key_entity") or "",
        "published_at": e.get("published_at") or "",
    }


def build(events: list[dict], generated_at: str | None = None) -> dict:
    """从 (event_dict, origin) 列表自举 canonical registry。

    v1：每个 event_id 唯一 → 1:1 canonical。同一 event_id 跨来源出现时合并 sources。
    不在此做跨事件语义归并（那是 S2 Resolver 的职责）。
    """
    generated_at = generated_at or _now()
    canonical: dict[str, dict] = {}
    by_event_id: dict[str, str] = {}

    for item in events:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            # 允许直接传 event_dict（默认 origin=unknown）
            e = item if isinstance(item, dict) else None
            origin = "unknown"
        else:
            e, origin = item
        ne = _norm_event(e, origin) if isinstance(e, dict) else None
        if not ne:
            continue
        eid = ne["event_id"]
        cev = _canonical_id(eid)
        if cev not in canonical:
            canonical[cev] = {
                "canonical_event_id": cev,
                "identity_key": eid,
                "title": ne["title"],
                "topic": ne["topic"],
                "event_type": ne["event_type"],
                "domain": event_type_domain(ne["event_type"]),
                "key_entity": ne["key_entity"],
                "sources": [],
                "aliases": [],
                "merged_from": [],
                "split_into": [],
                "stage": None,
                "status": "active",
                "created_at": generated_at,
                "updated_at": generated_at,
            }
        rec = canonical[cev]
        src = {
            "event_id": eid,
            "origin": origin,
            "published_at": ne["published_at"],
        }
        if not any(s["event_id"] == eid and s["origin"] == origin for s in rec["sources"]):
            rec["sources"].append(src)
        # 用信息更完整的来源补全标题/主题
        if not rec["title"] and ne["title"]:
            rec["title"] = ne["title"]
        if not rec["topic"] and ne["topic"]:
            rec["topic"] = ne["topic"]
        if not rec["event_type"] and ne["event_type"]:
            rec["event_type"] = ne["event_type"]
        by_event_id[eid] = cev

    return {
        "version": VERSION,
        "principle": PRINCIPLE,
        "generated_at": generated_at,
        "count": len(canonical),
        "canonical_events": canonical,
        "by_event_id": by_event_id,
    }


def resolve(event_id: str, registry: dict) -> str | None:
    """任意 event_id（含别名）映射到 canonical_event_id。"""
    if not event_id:
        return None
    by = registry.get("by_event_id", {})
    if event_id in by:
        return by[event_id]
    aliases = registry.get("aliases", {})
    if event_id in aliases:
        return aliases[event_id]
    # 直接以 canonical id 查询
    if event_id in registry.get("canonical_events", {}):
        return event_id
    return None


def upsert(registry: dict, canonical_event_id: str, patch: dict) -> dict:
    """就地更新某 canonical 的允许字段（title/topic/event_type/stage/status）。"""
    ev = registry.get("canonical_events", {}).get(canonical_event_id)
    if not ev:
        raise KeyError(f"未知 canonical_event_id: {canonical_event_id}")
    allowed = {"title", "topic", "event_type", "stage", "status"}
    for k, v in patch.items():
        if k in allowed:
            ev[k] = v
    ev["updated_at"] = _now()
    return registry


def alias(registry: dict, event_id: str, canonical_event_id: str) -> dict:
    """登记一个 event_id 别名 → canonical（用于跨来源/历史 id 映射）。"""
    if canonical_event_id not in registry.get("canonical_events", {}):
        raise KeyError(f"别名目标不存在: {canonical_event_id}")
    registry.setdefault("aliases", {})[event_id] = canonical_event_id
    ev = registry["canonical_events"][canonical_event_id]
    if event_id not in ev["aliases"]:
        ev["aliases"].append(event_id)
    ev["updated_at"] = _now()
    return registry


def merge(registry: dict, target: str, source: str) -> dict:
    """把 source canonical 归并进 target：target 吸收 sources/aliases，source 标记 inactive。"""
    ce = registry.get("canonical_events", {})
    if target not in ce or source not in ce:
        raise KeyError(f"merge 需要两个已存在 canonical: {target}/{source}")
    if target == source:
        return registry
    t, s = ce[target], ce[source]
    for src in s["sources"]:
        if not any(x["event_id"] == src["event_id"] and x["origin"] == src["origin"] for x in t["sources"]):
            t["sources"].append(src)
        registry["by_event_id"][src["event_id"]] = target
    for a in s["aliases"]:
        if a not in t["aliases"]:
            t["aliases"].append(a)
        registry["aliases"][a] = target
    t.setdefault("merged_from", []).append(source)
    t["updated_at"] = _now()
    s["status"] = "merged"
    s["merged_into"] = target
    s["updated_at"] = _now()
    return registry


def split(registry: dict, canonical_event_id: str, event_ids: list[str], generated_at: str | None = None, method: str = "manual") -> str:
    """把某 canonical 下的部分 event_id 拆为新 canonical（身份分裂修正）。返回新 id。

    X2（评审修订）：split 必须人工触发（MANUAL_SPLIT_REQUIRED），禁止自动拆分——自动拆分
    会把不同现实事件"对齐"到错误剧本，比不拆更糟。
    """
    if MANUAL_SPLIT_REQUIRED and method != "manual":
        raise RuntimeError("split 必须人工触发（MANUAL_SPLIT_REQUIRED）；禁止自动拆分")
    ce = registry.get("canonical_events", {})
    if canonical_event_id not in ce:
        raise KeyError(f"split 源不存在: {canonical_event_id}")
    generated_at = generated_at or _now()
    parent = ce[canonical_event_id]
    new_id = _canonical_id(canonical_event_id + ":" + "|".join(sorted(event_ids)))
    new_rec = {
        "canonical_event_id": new_id,
        "identity_key": new_id,
        "title": parent["title"],
        "topic": parent["topic"],
        "event_type": parent["event_type"],
        "domain": parent.get("domain"),
        "key_entity": parent.get("key_entity"),
        "sources": [],
        "aliases": [],
        "merged_from": [],
        "split_into": [],
        "stage": parent.get("stage"),
        "status": "active",
        "split_method": method,
        "created_at": generated_at,
        "updated_at": generated_at,
    }
    kept = []
    for src in parent["sources"]:
        if src["event_id"] in event_ids:
            new_rec["sources"].append(src)
            registry["by_event_id"][src["event_id"]] = new_id
        else:
            kept.append(src)
    parent["sources"] = kept
    parent.setdefault("split_into", []).append(new_id)
    parent["updated_at"] = generated_at
    ce[new_id] = new_rec
    return new_id


def migrate(registry: dict, event_id: str, new_canonical: str) -> dict:
    """把单个 event_id 重新指向另一个 canonical（纠正错误归并）。"""
    ce = registry.get("canonical_events", {})
    if new_canonical not in ce:
        raise KeyError(f"migrate 目标不存在: {new_canonical}")
    old = registry.get("by_event_id", {}).pop(event_id, None)
    if old and old in ce:
        ce[old]["sources"] = [s for s in ce[old]["sources"] if s["event_id"] != event_id]
    registry["by_event_id"][event_id] = new_canonical
    if event_id in ce[new_canonical]["aliases"]:
        pass
    elif event_id not in [s["event_id"] for s in ce[new_canonical]["sources"]]:
        ce[new_canonical]["sources"].append({"event_id": event_id, "origin": "migrated", "published_at": ""})
    ce[new_canonical]["updated_at"] = _now()
    return registry


def validate(registry: dict) -> None:
    """fail-closed：任何结构破坏都抛 AssertionError。"""
    assert registry.get("version") == VERSION, f"version 不符: {registry.get('version')}"
    for key in ("principle", "generated_at", "count", "canonical_events", "by_event_id"):
        assert key in registry, f"缺关键字段: {key}"
    ce = registry["canonical_events"]
    assert isinstance(ce, dict) and ce, "canonical_events 为空"
    ids = set(ce)
    # canonical id 唯一且自洽
    for cev, rec in ce.items():
        assert cev == rec.get("canonical_event_id"), f"canonical id 不自洽: {cev}"
        assert rec.get("status") in {"active", "merged"}, f"非法 status: {rec.get('status')}"
        # merged 必须指向存在 target
        if rec.get("status") == "merged":
            assert rec.get("merged_into") in ids, f"merged_into 悬空: {rec.get('merged_into')}"
        # X2：alias-only 类型不允许被自动归并（merged_from 必须为空）
        if not may_auto_merge(rec.get("event_type", "")):
            assert not rec.get("merged_from"), f"alias-only 类型不应有 merged_from: {cev}"
        # X2：split 必须为人工触发
        if rec.get("split_method") and rec["split_method"] != "manual":
            assert False, f"split 必须为人工: {cev}"
        # by_event_id 必须覆盖所有活跃 canonical 的 sources
    for eid, cev in registry["by_event_id"].items():
        assert cev in ids, f"by_event_id 悬空: {eid}→{cev}"
    # 活跃 canonical 的 sources 必须都能被 by_event_id 解析回来
    for cev, rec in ce.items():
        if rec.get("status") != "active":
            continue
        for src in rec["sources"]:
            assert registry["by_event_id"].get(src["event_id"]) == cev, (
                f"source 未覆盖: {src['event_id']} 未指向 {cev}"
            )


def validate_against_annotations(anno_path: str | Path | None = None) -> dict:
    """质量门（每 Sprint 跑）：用 canonical_annotation_set.json 标注样例断言归并行为。

    用 should_merge 做并查集分组，断言每组事件数 == 样例声明的 expect_ce_count；
    false merge / 漏合 = 硬失败（断言抛错）。返回 {cases, passed, failed}。
    """
    anno_path = Path(anno_path) if anno_path else ROOT / "canonical_annotation_set.json"
    anno = _load(anno_path)
    results: dict[str, Any] = {"cases": 0, "passed": 0, "failed": []}
    for case in anno.get("cases", []):
        results["cases"] += 1
        events = case.get("events", [])
        parent = list(range(len(events)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            parent[find(x)] = find(y)

        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                if should_merge(events[i], events[j]):
                    union(i, j)
        groups = len({find(i) for i in range(len(events))})
        expected = case.get("expect_ce_count")
        if expected is None:
            results["failed"].append(f"{case.get('id')}: 缺 expect_ce_count")
            continue
        if groups == expected:
            results["passed"] += 1
        else:
            results["failed"].append(
                f"{case.get('id')}: 期望 {expected} CE，实得 {groups}（{case.get('note', '')}）"
            )
    if results["failed"]:
        raise AssertionError("标注质量门失败: " + "; ".join(results["failed"]))
    return results


def load_registry() -> dict:
    """加载已落盘的 canonical registry；缺失返回空 dict（不伪造）。"""
    return _load(OUTPUT)


def build_artifacts(generated_at: str | None = None) -> dict:
    """从 daily_brief + review_queue + second_brain 实体时间线自举并落盘。

    覆盖所有跨模块引用的 event_id（single source of truth）：实体时间线事件也带
    event_id / title / topic / published_at，缺失 event_id 的条目被忽略（不伪造）。
    """
    db = _load(ROOT / "p2_daily_brief.json")
    rq = _load(ROOT / "review_queue.json")
    sb = _load(ROOT / "second_brain.json")
    events: list[Any] = []
    for e in (db.get("brief") or []):
        events.append((e, "daily_brief"))
    for e in (rq.get("items") or []):
        events.append((e, "review_queue"))
    for th in (sb.get("entity_threads") or []):
        for ev in (th.get("events") or []):
            events.append((ev, "second_brain"))
    reg = build(events, generated_at)
    validate(reg)
    OUTPUT.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # 别名表独立落盘（便于 S2 resolver 增量更新，不每次重写全量）
    alias_doc = {
        "version": VERSION,
        "generated_at": reg["generated_at"],
        "aliases": reg.get("aliases", {}),
    }
    ALIASES.write_text(json.dumps(alias_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return reg


def main() -> None:
    reg = build_artifacts()
    active = sum(1 for r in reg["canonical_events"].values() if r.get("status") == "active")
    print(f"Canonical Event Registry: {reg['count']} canonical ({active} active) · {len(reg['by_event_id'])} event_id 映射")


if __name__ == "__main__":
    main()
