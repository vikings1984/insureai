#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Acquisition Lifecycle — Event OS 主脊柱 S3（生命周期引擎，lc-v1.1 domain 插件）。

X2（评审修订）：生命周期按 domain 插件化，禁止把收购六段默默通用化到所有事件类型。
- acquisition：六段 stage = rumor → negotiation → agreement → regulatory → closing → integration（阶段严格来自 Claim + Evidence）。
- regulatory：无 stage 演进，只用 status（issued/effective/in_review/revised/repealed）+ issued/effective 日期。
- catastrophe / other：stage = n/a（不适用阶段生命周期）。

纪律（继承主线）：
- 阶段只由证据信号推出；无进展信号时 acquisition 事件落 rumor（intent 地板），regulatory/other 不伪造 stage。
- 不伪造：证据只显示"拟收购"则 stage=rumor；regulatory 只标 status，绝不臆测阶段。
- fail-closed：validate 对结构破坏 / 非法 stage / regulatory 误写 stage 抛错。
- 富集回 canonical_events.json（单一事实源），并产出 lifecycle_report.json 供 S4/S6 复用。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from event_registry import load_registry, upsert, validate as _validate_registry

ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / "canonical_events.json"
CLAIMS = ROOT / "claims.json"
REPORT = ROOT / "lifecycle_report.json"

VERSION = "lc-v1.1"

# 生命周期 domain（与 event_registry.EVENT_TYPE_DOMAIN 对齐；X2 评审：禁止默默通用化）。
LIFECYCLE_DOMAINS = {"acquisition", "regulatory", "catastrophe", "other"}
# 仅 acquisition 使用六段 stage；其余 domain 无 stage 演进。
STAGE_DOMAINS = {"acquisition"}

# 阶段序（演进方向）；index 越大越靠后。
STAGES = ["rumor", "negotiation", "agreement", "regulatory", "closing", "integration"]
STAGE_ORDER = {s: i for i, s in enumerate(STAGES)}

# regulatory 域状态（只 status + 日期，无 stage 演进）；优先级：effective > issued > revised > repealed > in_review > unknown
REG_STATUS_PATTERNS: dict[str, list[str]] = {
    "effective": [r"生效", r"实施", r"施行", r"effective", r"in force", r"comes into force"],
    "issued": [r"发布", r"印发", r"颁布", r"出台", r"issued", r"published", r"released", r"announced"],
    "revised": [r"修订", r"修订版", r"amend", r"amendment"],
    "repealed": [r"废止", r"repeal", r"abolish"],
    "in_review": [r"征求意见", r"草案", r"征求意见稿", r"draft", r"consultation", r"exposure"],
}
REG_STATUS_PRIORITY = ["effective", "issued", "revised", "repealed", "in_review"]
_DATE_RE = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2})")

# 各阶段证据信号（中文 + 英文，来自真实 claim_text / evidence.matched_span 词汇）。
# 取"命中的最高阶段"作为最终 stage；M&A 事件无进展信号则落 rumor（intent 地板）。
STAGE_PATTERNS: dict[str, list[str]] = {
    "rumor": [
        r"拟收购", r"拟并购", r"拟", r"传闻", r"传", r"据称", r"据透露", r"市场消息",
        r"媒体称", r"报道称", r"据悉", r"考虑收购", r"计划收购", r"拟议", r"有意",
        r"rumou?red", r"reportedly", r"plans to", r"considering", r"may acquire",
        r"in talks to", r"exploring", r"said to",
    ],
    "negotiation": [
        r"谈判", r"磋商", r"洽谈", r"谅解备忘录", r"MOU", r"进入谈判", r"排他",
        r"entered talks", r"negotiating", r"advanced talks", r"exclusive",
    ],
    "agreement": [
        r"签署", r"达成.{0,6}协议", r"收购协议", r"宣布收购", r"同意收购", r"正式收购",
        r"签约", r"definitive agreement", r"signed", r"agreed", r"announced acquisition",
        r"to acquire", r"agrees to", r"agreement to",
    ],
    "regulatory": [
        r"获批", r"监管批准", r"批准", r"反垄断", r"通过审查", r"监管审批", r"过会",
        r"regulatory approval", r"approved by", r"antitrust", r"cleared", r"clearance",
    ],
    "closing": [
        r"交割", r"完成收购", r"完成交易", r"交割完成", r"完成交割", r"closed",
        r"closing", r"completes acquisition", r"completed", r"\bbuys\b", r"acquired",
    ],
    "integration": [
        r"整合", r"并表", r"完成整合", r"协同", r"integration", r"consolidated",
        r"synergies", r"merged",
    ],
}
_COMPILED = {s: [re.compile(p, re.IGNORECASE) for p in pats] for s, pats in STAGE_PATTERNS.items()}
_REG_COMPILED = {s: [re.compile(p, re.IGNORECASE) for p in pats] for s, pats in REG_STATUS_PATTERNS.items()}

ACQUISITION_CLAIM_TYPES = {"acquisition_intent", "acquisition", "merger", "merger_intent", "consolidation"}
_ACQ_TEXT_RE = re.compile(r"收购|并购|acqui|merg|consolidat|拟收购|\bbuys\b", re.IGNORECASE)


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


def is_acquisition_event(claims: list[dict]) -> bool:
    """事件是否为 M&A 类（依据 Claim 类型或 Claim/证据文本）。"""
    for cl in claims or []:
        if cl.get("claim_type") in ACQUISITION_CLAIM_TYPES:
            return True
        txt = (cl.get("claim_text") or "") + " " + " ".join(
            (e.get("matched_span") or "") for e in (cl.get("supporting_evidence") or [])
        )
        if _ACQ_TEXT_RE.search(txt):
            return True
    return False


def _claim_texts(claim: dict) -> list[str]:
    """收集 Claim 文本 + 所有 Evidence matched_span（含矛盾/上下文证据）。"""
    out: list[str] = []
    if claim.get("claim_text"):
        out.append(claim["claim_text"])
    if isinstance(claim.get("evidence"), str) and claim["evidence"]:
        out.append(claim["evidence"])
    for key in ("supporting_evidence", "contradicting_evidence", "context_evidence"):
        for ev in (claim.get(key) or []):
            if isinstance(ev, dict):
                if ev.get("matched_span"):
                    out.append(ev["matched_span"])
                if ev.get("relation"):
                    out.append(str(ev["relation"]))
    return out


def domain_of(rec: dict, claims: list[dict]) -> str:
    """确定生命周期 domain：优先用 Registry 记录的 domain（acquisition/regulatory/catastrophe），
    其余（other / 缺省）回退到 Claim 文本推断（is_acquisition_event）。"""
    d = (rec or {}).get("domain")
    if d in LIFECYCLE_DOMAINS and d != "other":
        return d
    return "acquisition" if is_acquisition_event(claims or []) else "other"


def _derive_acquisition_stage(claims: list[dict]) -> dict:
    """acquisition 六段：严格来自 Claim + Evidence 文本信号。"""
    matched_stages: set[str] = set()
    signals: list[dict] = []
    evidence_refs: list[str] = []
    max_tier = 0
    combined = []
    for cl in claims:
        for txt in _claim_texts(cl):
            combined.append(txt)
            for ev in (cl.get("supporting_evidence") or []):
                tid = ev.get("evidence_id")
                tier = ev.get("source_tier") or 0
                try:
                    tier = int(tier)
                except (TypeError, ValueError):
                    tier = 0
                max_tier = max(max_tier, tier)
                if tid and tid not in evidence_refs:
                    evidence_refs.append(tid)
    text = "\n".join(combined)
    for stage, pats in _COMPILED.items():
        for p in pats:
            m = p.search(text)
            if m:
                matched_stages.add(stage)
                signals.append({"stage": stage, "pattern": p.pattern, "match": m.group(0)})

    if matched_stages:
        stage = max(matched_stages, key=lambda s: STAGE_ORDER[s])
    else:
        stage = "rumor"  # acquisition 事件无进展信号 → intent 地板

    distinct = len({s["stage"] for s in signals})
    conf = round(min(1.0, 0.25 + 0.18 * distinct + 0.12 * (max_tier / 4.0)), 2)
    return {
        "domain": "acquisition",
        "stage": stage,
        "signals": signals[:20],
        "evidence_refs": evidence_refs[:20],
        "confidence": conf,
        "matched_stage_count": len(matched_stages),
    }


def _derive_regulatory_status(claims: list[dict]) -> dict:
    """regulatory 域：无 stage 演进，只 status + issued/effective 日期（来自 Claim + Evidence）。"""
    signals: list[dict] = []
    evidence_refs: list[str] = []
    max_tier = 0
    combined = []
    for cl in claims:
        for txt in _claim_texts(cl):
            combined.append(txt)
            for ev in (cl.get("supporting_evidence") or []):
                tid = ev.get("evidence_id")
                tier = ev.get("source_tier") or 0
                try:
                    tier = int(tier)
                except (TypeError, ValueError):
                    tier = 0
                max_tier = max(max_tier, tier)
                if tid and tid not in evidence_refs:
                    evidence_refs.append(tid)
    text = "\n".join(combined)
    hit_status: set[str] = set()
    for status, pats in _REG_COMPILED.items():
        for p in pats:
            m = p.search(text)
            if m:
                hit_status.add(status)
                signals.append({"status": status, "pattern": p.pattern, "match": m.group(0)})

    # 取最高优先级状态；无命中 → unknown（不伪造）
    status = next((s for s in REG_STATUS_PRIORITY if s in hit_status), "unknown")
    # 日期提取（issued/effective 尽力而为；证据含 YYYY-MM-DD 则取首个）
    dates = _DATE_RE.findall(text)
    issued = effective = None
    if status == "effective" and dates:
        effective = dates[0]
    elif status in ("issued", "effective") and dates:
        issued = dates[0]
        if len(dates) > 1:
            effective = dates[1]
    conf = 0.0 if status == "unknown" else round(min(1.0, 0.4 + 0.15 * len(hit_status) + 0.12 * (max_tier / 4.0)), 2)
    return {
        "domain": "regulatory",
        "stage": "n/a",  # regulatory 无 stage 演进
        "status": status,
        "issued": issued,
        "effective": effective,
        "signals": signals[:20],
        "evidence_refs": evidence_refs[:20],
        "confidence": conf,
        "reason": f"regulatory 域：status={status}（无 stage 生命周期）",
    }


def derive_stage(claims: list[dict], domain: str | None = None) -> dict:
    """按 domain 插件推导生命周期。返回含 domain 的字典。

    - acquisition：六段 stage（见 _derive_acquisition_stage）。
    - regulatory：status + issued/effective，stage 固定 n/a。
    - catastrophe / other：stage = n/a（不适用阶段生命周期），不伪造。

    domain 为 None 时回退推断（is_acquisition_event → acquisition，否则 other）。
    阶段/状态严格来自 Claim + Evidence，绝不臆测。
    """
    d = domain or ("acquisition" if is_acquisition_event(claims or []) else "other")
    if d == "acquisition":
        return _derive_acquisition_stage(claims)
    if d == "regulatory":
        return _derive_regulatory_status(claims)
    # catastrophe / other：无阶段生命周期
    return {
        "domain": d,
        "stage": "n/a",
        "status": None,
        "signals": [],
        "evidence_refs": [],
        "confidence": 0.0,
        "reason": f"{d} 域无阶段生命周期（仅 status/效力，不适用 stage）",
    }


def build_claims_index() -> dict[str, list[dict]]:
    """claims.json 按 event_id 建索引（同一事件可能有多条 claim）。"""
    c = _load(CLAIMS)
    idx: dict[str, list[dict]] = {}
    for ev in (c.get("events") or []):
        eid = ev.get("event_id")
        if not eid:
            continue
        idx.setdefault(eid, []).extend(ev.get("claims") or [])
    return idx


def enrich_registry(registry: dict, claims_idx: dict[str, list[dict]]) -> dict:
    """把每个 canonical event 的生命周期（按 domain 插件）富集回 registry（单一事实源）。"""
    for cev, rec in registry.get("canonical_events", {}).items():
        eids = [s["event_id"] for s in rec.get("sources", [])]
        claims: list[dict] = []
        for eid in eids:
            claims.extend(claims_idx.get(eid, []))
        d = domain_of(rec, claims)
        result = derive_stage(claims, d)
        upsert(registry, cev, {"stage": result["stage"]})
        rec["lifecycle"] = {
            "domain": d,
            "stage": result["stage"],
            "status": result.get("status"),
            "issued": result.get("issued"),
            "effective": result.get("effective"),
            "confidence": result["confidence"],
            "matched_stage_count": result.get("matched_stage_count", 0),
            "evidence_refs": result.get("evidence_refs", []),
            "reason": result.get("reason"),
        }
    return registry


def build_report(registry: dict, claims_idx: dict[str, list[dict]], generated_at: str | None = None) -> dict:
    generated_at = generated_at or _now()
    stage_counts: dict[str, int] = {s: 0 for s in STAGES}
    stage_counts["n/a"] = 0
    domain_counts: dict[str, int] = {d: 0 for d in LIFECYCLE_DOMAINS}
    acq_events = 0
    entries: list[dict] = []
    for cev, rec in registry.get("canonical_events", {}).items():
        eids = [s["event_id"] for s in rec.get("sources", [])]
        claims: list[dict] = []
        for eid in eids:
            claims.extend(claims_idx.get(eid, []))
        d = domain_of(rec, claims)
        res = derive_stage(claims, d)
        stage = res["stage"]
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        domain_counts[d] = domain_counts.get(d, 0) + 1
        if d == "acquisition":
            acq_events += 1
        entries.append({
            "canonical_event_id": cev,
            "identity_key": rec.get("identity_key"),
            "title": rec.get("title"),
            "domain": d,
            "stage": stage,
            "status": res.get("status"),
            "issued": res.get("issued"),
            "effective": res.get("effective"),
            "confidence": res["confidence"],
            "matched_stage_count": res.get("matched_stage_count", 0),
            "evidence_refs": res.get("evidence_refs", []),
            "reason": res.get("reason"),
        })
    return {
        "version": VERSION,
        "registry_version": registry.get("version"),
        "generated_at": generated_at,
        "total_canonical": len(registry.get("canonical_events", {})),
        "acquisition_events": acq_events,
        "stage_counts": stage_counts,
        "domain_counts": domain_counts,
        "entries": sorted(entries, key=lambda e: (e["stage"] == "n/a", -STAGE_ORDER.get(e["stage"], -1))),
    }


def validate(report: dict) -> None:
    """fail-closed：stage 非法 / 计数不自洽 / regulatory 误写 stage 即抛错。"""
    assert report.get("version") == VERSION, f"version 不符: {report.get('version')}"
    for key in ("generated_at", "total_canonical", "acquisition_events", "stage_counts", "domain_counts", "entries"):
        assert key in report, f"缺关键字段: {key}"
    allowed = set(STAGES) | {"n/a"}
    for e in report["entries"]:
        assert e.get("stage") in allowed, f"非法 stage: {e.get('stage')}"
        # X2 评审：regulatory / catastrophe / other 域禁止有 stage 演进（只 status/效力）
        if e.get("domain") in ("regulatory", "catastrophe", "other"):
            assert e.get("stage") == "n/a", (
                f"{e.get('domain')} 域不应有 stage 演进: {e.get('canonical_event_id')} → {e.get('stage')}"
            )
    sc = report["stage_counts"]
    assert sum(sc.values()) == report["total_canonical"], (
        f"stage_counts 求和 {sum(sc.values())} != total {report['total_canonical']}"
    )
    assert sc.get("n/a", 0) + report["acquisition_events"] == report["total_canonical"], (
        "n/a + acquisition_events 应等于 total_canonical"
    )


def build_artifacts(generated_at: str | None = None) -> dict:
    """富集 registry 阶段 + 产出 lifecycle_report.json，均落盘。"""
    registry = load_registry()
    claims_idx = build_claims_index()
    enrich_registry(registry, claims_idx)
    _validate_registry(registry)  # 复用 S1 校验，确保 stage 写入不破坏结构
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = build_report(registry, claims_idx, generated_at)
    validate(report)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    report = build_artifacts()
    sc = report["stage_counts"]
    dist = " · ".join(f"{s}={sc.get(s,0)}" for s in STAGES)
    dc = report["domain_counts"]
    ddist = " · ".join(f"{d}={dc.get(d,0)}" for d in sorted(LIFECYCLE_DOMAINS))
    print(
        f"Acquisition Lifecycle (lc-v1.1): canonical={report['total_canonical']} "
        f"acq={report['acquisition_events']} · stage[{dist}] · n/a={sc.get('n/a',0)} · "
        f"domain[{ddist}]"
    )


if __name__ == "__main__":
    main()
