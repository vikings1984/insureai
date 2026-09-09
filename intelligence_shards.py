#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""InsureAI intelligence.json 分片（P0-1 首屏瘦身）。

背景
----
contract.py 把 claims / decisions_by_role / temporal 内联进 intelligence.json 之后，
单文件从 5.29 MB 涨到 13 MB 量级；而 index.html 首屏只用到其中约 90 KB。
为首屏下载 13 MB 是不可接受的。

产物（都是 intelligence.json 的**投影**，不是新事实源）
------------------------------------------------------
  intelligence.summary.json      ~90 KB   index.html 首屏（5 个 UI 模块）
  intelligence.events.json       ~1.1 MB  intelligence.html / event-intelligence.html
  intelligence.detail.<k>.json   ~180 KB  单事件详情，按排名分块、点击时按需拉取

  intelligence.json 仍是权威全量产物（契约 / CI / API 消费方），前端默认不再下载它。

为什么不在仓库里提交分片
------------------------
分片体积合计约 7.5 MB，而它们完全可以从已提交的 intelligence.json 重新生成。
提交进去只会让仓库每天再膨胀 7.5 MB，与 P1「清理生成物」的方向相反。
因此分片由 deploy-cloudflare.yml 在**部署时**生成（wrangler 上传、不入库），
并用 .gitignore 兜底防止 daily-collect 误提交。前端在分片缺失时自动回退到全量文件。

一致性纪律（fail-closed）
------------------------
分片只做裁剪，不做重排、重算或改写：
  * version / generated_at 必须与源完全一致；
  * stats 必须逐键相等（这是首屏 KPI 的唯一来源）；
  * events 分片的事件数量、顺序、逐事件字段值必须与源一致；
  * 每个源事件必须有且只有一个详情分块承载其详情。
任一条不满足即在写盘前抛错，绝不产出半套分片。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INTEL = ROOT / "intelligence.json"
SUMMARY_PATH = ROOT / "intelligence.summary.json"
EVENTS_PATH = ROOT / "intelligence.events.json"
DETAIL_PREFIX = "intelligence.detail."
DETAIL_SUFFIX = ".json"

# 首屏裁剪上限：UI 实际渲染多少，分片就带多少。
SUMMARY_BRIEF_LIMIT = 5           # intelligence-ui.js: data.daily_brief.slice(0,5)
SUMMARY_ROLE_LIMIT = 6            # decision-ui.js:    rows.slice(0,6)
SUMMARY_TOPIC_SIGNALS = 12        # temporal-ui.js 取前 6，留一倍余量
SUMMARY_ENTITY_MOMENTUM = 20      # 同上

# 详情分块大小。按**排名**分块而不是按哈希：事件列表按情报分排序，
# 用户点开的多半是前列事件，按排名分块能让前 50 名共用一次拉取。
DETAIL_CHUNK = 50

# 事件索引保留字段：列表渲染 + 定位详情分块所需的最小集合。
LEAN_FIELDS = (
    "event_id", "canonical_event_id", "title", "event_type", "entities",
    "topic", "topic_label", "published_at", "source_count", "article_count",
    "scores", "evidence_coverage", "evidence_status", "review_required",
)
# 事件详情保留字段：只有点开某个事件时才需要。
DETAIL_FIELDS = ("insight", "trust", "claims", "evidence")

SHARED_FIELDS = (
    "version", "generated_at", "principle", "model", "stats", "trust_stats",
    "claim_stats", "decision_stats", "data_contract", "radar",
)


def _write(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _shared(data: dict) -> dict:
    return {k: data[k] for k in SHARED_FIELDS if k in data}


def lean_event(event: dict, chunk: int) -> dict:
    """事件索引条目：列表要什么给什么，详情留给 detail 分块。"""
    row = {k: event[k] for k in LEAN_FIELDS if k in event}
    trust = event.get("trust") or {}
    if trust:
        # 列表只渲染 trust.level；完整 trust 由 detail 分块提供。
        row["trust"] = {"level": trust.get("level", "low")}
    claims = event.get("claims") or {}
    if claims:
        # 列表只渲染冲突计数；coverage / cross_checked 供详情占位。
        row["claims"] = {
            "coverage": claims.get("coverage", 0),
            "cross_checked": claims.get("cross_checked", 0),
            "conflicted": claims.get("conflicted", 0),
        }
    row["detail_chunk"] = chunk
    return row


def chunk_of(index: int) -> int:
    return index // DETAIL_CHUNK


def build_summary(data: dict) -> dict:
    events = data.get("events") or []
    by_id = {str(e.get("event_id")): e for e in events}
    brief = []
    for row in (data.get("daily_brief") or [])[:SUMMARY_BRIEF_LIMIT]:
        item = dict(row)
        # daily_brief 自带 trust/insight/evidence，唯独不带 claims；
        # 而首屏的 claim-evidence UI 需要命题，故从源事件补齐。
        item["claims"] = (by_id.get(str(row.get("event_id"))) or {}).get("claims") or {}
        brief.append(item)
    temporal = data.get("temporal") or {}
    doc = _shared(data)
    doc["temporal"] = {
        "version": temporal.get("version"),
        "principle": temporal.get("principle"),
        "topic_signals": (temporal.get("topic_signals") or [])[:SUMMARY_TOPIC_SIGNALS],
        "entity_momentum": (temporal.get("entity_momentum") or [])[:SUMMARY_ENTITY_MOMENTUM],
    }
    doc["daily_brief"] = brief
    doc["decisions"] = data.get("decisions") or []
    doc["decisions_by_role"] = {
        role: (rows or [])[:SUMMARY_ROLE_LIMIT]
        for role, rows in (data.get("decisions_by_role") or {}).items()
    }
    doc["shard"] = {"kind": "summary", "event_count": len(events)}
    return doc


def build_events(data: dict, chunk_count: int) -> dict:
    events = data.get("events") or []
    doc = _shared(data)
    doc["temporal"] = data.get("temporal") or {}
    doc["daily_brief"] = data.get("daily_brief") or []
    doc["decisions"] = data.get("decisions") or []
    doc["decisions_by_role"] = data.get("decisions_by_role") or {}
    doc["events"] = [lean_event(e, chunk_of(i)) for i, e in enumerate(events)]
    doc["shard"] = {
        "kind": "events",
        "event_count": len(events),
        "chunk_size": DETAIL_CHUNK,
        "chunk_count": chunk_count,
    }
    return doc


def build_details(data: dict) -> dict:
    events = data.get("events") or []
    chunks: dict[int, dict] = {}
    for i, event in enumerate(events):
        entry = {k: event[k] for k in DETAIL_FIELDS if k in event}
        chunks.setdefault(chunk_of(i), {})[str(event.get("event_id"))] = entry
    return chunks


def verify(data: dict, summary: dict, events_doc: dict, chunks: dict) -> list:
    """分片一致性门禁：任何一条不满足即视为不可发布。"""
    problems: list[str] = []
    source_events = data.get("events") or []

    for name, doc in (("summary", summary), ("events", events_doc)):
        for key in ("version", "generated_at"):
            if doc.get(key) != data.get(key):
                problems.append(f"{name}.{key} 与源不一致: {doc.get(key)!r} != {data.get(key)!r}")

    src_stats = data.get("stats") or {}
    for name, doc in (("summary", summary), ("events", events_doc)):
        got = doc.get("stats") or {}
        if set(got) != set(src_stats):
            problems.append(f"{name}.stats 键集合与源不一致: {sorted(set(got) ^ set(src_stats))}")
        for key, value in src_stats.items():
            if got.get(key) != value:
                problems.append(f"{name}.stats.{key} 与源不一致: {got.get(key)!r} != {value!r}")

    lean_rows = events_doc.get("events") or []
    if len(lean_rows) != len(source_events):
        problems.append(f"events 分片事件数不一致: {len(lean_rows)} != {len(source_events)}")
    for i, (lean, full) in enumerate(zip(lean_rows, source_events)):
        if str(lean.get("event_id")) != str(full.get("event_id")):
            problems.append(f"events 分片第 {i} 项顺序错位: {lean.get('event_id')!r} != {full.get('event_id')!r}")
            break
        for field in LEAN_FIELDS:
            if field in full and lean.get(field) != full[field]:
                problems.append(f"events[{i}].{field} 与源不一致")
        if (full.get("trust") or {}).get("level") != (lean.get("trust") or {}).get("level"):
            problems.append(f"events[{i}].trust.level 与源不一致")
        if (full.get("claims") or {}).get("conflicted") != (lean.get("claims") or {}).get("conflicted"):
            problems.append(f"events[{i}].claims.conflicted 与源不一致")

    covered: dict[str, int] = {}
    for key, bucket in chunks.items():
        for event_id in bucket:
            if event_id in covered:
                problems.append(f"事件 {event_id} 同时出现在分块 {covered[event_id]} 与 {key}")
            covered[event_id] = key
    for i, event in enumerate(source_events):
        event_id = str(event.get("event_id"))
        if event_id not in covered:
            problems.append(f"事件 {event_id} 没有详情分块")
        elif chunk_of(i) != covered[event_id]:
            problems.append(f"事件 {event_id} 的 detail_chunk 指向的分块与实际不符")

    by_id = {str(e.get("event_id")): e for e in source_events}
    for i, row in enumerate(summary.get("daily_brief") or []):
        src = by_id.get(str(row.get("event_id")))
        if src is None:
            problems.append(f"summary.daily_brief[{i}] 的 event_id 在源中不存在: {row.get('event_id')!r}")
        elif row.get("claims") != (src.get("claims") or {}):
            problems.append(f"summary.daily_brief[{i}].claims 与源事件不一致")
    return problems


def build(data: dict) -> dict:
    """生成三套分片（不写盘），返回一致性校验结果。"""
    chunks = build_details(data)
    summary = build_summary(data)
    events_doc = build_events(data, len(chunks))
    problems = verify(data, summary, events_doc, chunks)
    return {
        "summary": summary,
        "events": events_doc,
        "chunks": chunks,
        "problems": problems,
    }


def write_all(result: dict) -> list:
    _write(SUMMARY_PATH, result["summary"])
    _write(EVENTS_PATH, result["events"])
    written = [SUMMARY_PATH.name, EVENTS_PATH.name]
    for key in sorted(result["chunks"]):
        name = f"{DETAIL_PREFIX}{key}{DETAIL_SUFFIX}"
        _write(ROOT / name, {"shard": {"kind": "detail", "chunk": key}, "events": result["chunks"][key]})
        written.append(name)
    return written


def clean() -> int:
    removed = 0
    for path in (SUMMARY_PATH, EVENTS_PATH):
        if path.exists():
            path.unlink()
            removed += 1
    for path in ROOT.glob(f"{DETAIL_PREFIX}*{DETAIL_SUFFIX}"):
        path.unlink()
        removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="intelligence.json 分片生成 / 校验")
    parser.add_argument("--check", action="store_true", help="只校验不写盘（分片不存在时按源重建后校验）")
    parser.add_argument("--clean", action="store_true", help="删除已生成的分片")
    args = parser.parse_args()

    if args.clean:
        print(f"removed {clean()} shard file(s)")
        return 0

    if not INTEL.exists():
        print(f"intelligence.json 不存在，跳过分片: {INTEL}", file=sys.stderr)
        return 0

    data = json.loads(INTEL.read_text(encoding="utf-8"))
    result = build(data)
    if result["problems"]:
        for problem in result["problems"][:20]:
            print(f"CONSISTENCY: {problem}", file=sys.stderr)
        print(f"分片一致性校验失败，共 {len(result['problems'])} 处问题；未写盘", file=sys.stderr)
        return 1

    if args.check:
        print(f"分片一致性校验通过: events={len(data.get('events') or [])} chunks={len(result['chunks'])}")
        return 0

    written = write_all(result)
    summary_kb = SUMMARY_PATH.stat().st_size / 1024
    events_kb = EVENTS_PATH.stat().st_size / 1024
    print(
        f"分片生成完成: {len(written)} 个文件 | "
        f"summary={summary_kb:.1f} KB events={events_kb:.1f} KB "
        f"chunks={len(result['chunks'])} | events={len(data.get('events') or [])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
