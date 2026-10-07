#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1-1 Source OS：把「抓不到」与「不活跃」分开（Event OS 第七阶段）。

问题（外部复核指出，实测已确认）：当前 `source_health` 把连通性与内容质量压成一个
`availability`，于是：

- 一个**官方源**（如最高人民法院 / 金融监管总局 / 财政部）因 crawler 不可达被标为
  "低可用 / 陈旧"→ 被误认为"源本身没价值"；
- 实测证据：16 个低可用源**全部 `count>0`（内容存在）**，即它们的低可用是
  **抓取侧问题**，不是"源不活跃"。

这会误导后续 degrade 建议（可能建议降权/停源一个其实很有价值的源）。

本模块把Source Health 拆成两个正交维度，并给出各自的处置口径：

    connectivity（连通性，抓得到吗）
      ├─ crawl_health            抓取成功率（availability / parse_success）
      └─ crawl_incident         连通性故障（availability 低但有内容）
    content（内容层，值不值得留）
      ├─ content_health          内容质量（content_quality / duplicate_ratio）
      ├─ publication_frequency   发布节奏（freshness）
      └─ business_coverage       业务相关度（insurance_relevance）

**处置纪律（关键）**：
- **degrade 建议只依据 content 维度**（quality/coverage），
  **不以crawl 失败为由**——crawler 故障应走"修抓取"，不是"降权源"；
- 只读聚合，不改data.json、不自动降权/停源（与 P2 台账一致）；
- 权威源清单显式声明（`AUTHORITY_SOURCES`），便于人工确认。

用法::

    python3 source_os.py           # 生成 source_os.json 并打印摘要
    python3 source_os.py --json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data.json")
OUTPUT = os.path.join(HERE, "source_os.json")

VERSION = "source-os-v1.0"

CRAWL_HEALTH_MIN = 0.5
CONTENT_QUALITY_MIN = 0.6
FRESHNESS_MIN = 0.2
COVERAGE_MIN = 0.5

# 权威源（保险/监管/金融官方）——显式声明，便于人工复核；degrade 永不对其生效。
AUTHORITY_SOURCES = {
    "最高人民法院", "金融监管总局", "银保监会", "财政部", "中国人民银行", "央行",
    "国家金融监督管理总局", "新华社", "新华网", "中国人民保险", "中国人保", "中国人寿",
    "中国再保险", "瑞士再保险", "国家统计局", "国务院", "国资委", "证监会",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path: str):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _f(v, d=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def classify_source(name: str, v: dict) -> dict:
    """把单个源拆成 connectivity / content 两组指标 + 处置建议。

    **关键区分（第七阶段实测发现）**：部分源在 data.json 里只有 `{count, ok}`——
    `availability` / `freshness` / `content_quality` 等指标**从未被计算**（键缺失）。
    这类源此前被 `_f(None)→0.0` 归一化成"低可用 / 陈旧"，于是**指标缺失被误报为源不健康**
    （实测 16 个源属此类，含金融监管总局 / 财政部 / 银保监会等官方源）。
    故本模块显式区分三态：
        measured   —— 指标齐备，可判健康
        unmeasured —— 指标缺失（数据缺口，须补采），**不可判为不健康**
        unhealthy  —— 指标齐备且确实不达标
    """
    count = _f(v.get("count"))
    has_content = count > 0

    # 指标是否齐备（键存在且非 None）
    has_avail = v.get("availability") is not None
    has_fresh = v.get("freshness") is not None
    measured = has_avail and has_fresh

    if not measured:
        # —— 未测量：数据缺口，不是源不健康 ——
        return {
            "source": name,
            "status": "unmeasured",
            "is_authority": name in AUTHORITY_SOURCES,
            "has_content": has_content,
            "connectivity": {"measured": False,
                             "note": "availability/freshness 指标缺失（从未计算），"
                                     "不可据此判断源不健康——应补采"},
            "content": {"measured": False},
            "suggested_action": "needs_measurement",
            "reason": "指标缺失（键不存在），属采集/计算缺口而非源失效",
        }

    avail = _f(v.get("availability"))
    parse = _f(v.get("parse_success"), 1.0)
    quality = _f(v.get("content_quality"), 1.0)
    dup = _f(v.get("duplicate_ratio"))
    fresh = _f(v.get("freshness"))
    cover = _f(v.get("insurance_relevance"))

    # —— connectivity（抓得到吗）——
    crawl_health = round((avail + parse) / 2, 4)
    # 抓取故障：有内容却抓不到 → connectivity 问题，不是源没价值
    crawl_incident = crawl_health < CRAWL_HEALTH_MIN and has_content

    # —— content（值不值得留）——
    content_health = round((quality + max(0.0, 1.0 - dup)) / 2, 4)
    is_authority = name in AUTHORITY_SOURCES

    # —— 处置建议：只依据 content 维度 ——
    if is_authority:
        action, why = "protect", "权威源，不建议降权/停源"
    elif content_health < CONTENT_QUALITY_MIN:
        action, why = "suggest_downweight", f"内容质量低（{content_health}）"
    elif cover < COVERAGE_MIN:
        action, why = "suggest_downweight", f"业务相关度低（{cover}）"
    elif fresh < FRESHNESS_MIN:
        action, why = "watch_content", f"新鲜度低（{fresh}）但内容/覆盖尚可"
    else:
        action, why = "keep", "内容与覆盖正常"

    crawl_note = None
    if crawl_incident:
        crawl_note = "有内容但抓取受限 → 应排查 crawler/网络，而非降权该源"

    return {
        "source": name,
        "status": "measured",
        "is_authority": is_authority,
        "has_content": has_content,
        "connectivity": {
            "measured": True,
            "crawl_health": crawl_health,
            "availability": avail,
            "parse_success": parse,
            "crawl_incident": crawl_incident,
            "note": crawl_note,
        },
        "content": {
            "measured": True,
            "content_health": content_health,
            "content_quality": quality,
            "duplicate_ratio": dup,
            "publication_frequency": fresh,
            "business_coverage": cover,
        },
        "suggested_action": action,
        "reason": why,
    }


def build(data: dict | None = None) -> dict:
    data = data if data is not None else (_read(DATA) or {})
    sh = (data or {}).get("source_health") or {}
    if not isinstance(sh, dict) or not sh:
        return {"available": False, "version": VERSION,
                "note": "data.json 无 source_health"}

    sources = [classify_source(n, v) for n, v in sh.items() if isinstance(v, dict)]

    measured = [s for s in sources if s["status"] == "measured"]
    unmeasured = [s for s in sources if s["status"] == "unmeasured"]
    crawl_incidents = [s for s in measured if s["connectivity"].get("crawl_incident")]
    content_weak = [s for s in measured
                     if s["suggested_action"] == "suggest_downweight"]
    watch = [s for s in measured if s["suggested_action"] == "watch_content"]

    return {
        "available": True,
        "version": VERSION,
        "generated_at": _now(),
        "principle": "connectivity 与 content 正交；且区分 measured / unmeasured —— "
                     "指标缺失≠源不健康。degrade 只依据 content，权威源受保护；只读，不改权重。",
        "thresholds": {
            "crawl_health_min": CRAWL_HEALTH_MIN,
            "content_quality_min": CONTENT_QUALITY_MIN,
            "freshness_min": FRESHNESS_MIN,
            "coverage_min": COVERAGE_MIN,
        },
        "meta": {
            "source_count": len(sources),
            "measured_count": len(measured),
            "unmeasured_count": len(unmeasured),
            "authority_count": sum(1 for s in sources if s["is_authority"]),
            "crawl_incident_count": len(crawl_incidents),   # 抓取故障（修 crawler）
            "content_weak_count": len(content_weak),       # 内容弱（才可建议降权）
            "watch_content_count": len(watch),
        },
        "unmeasured_sources": [s["source"] for s in unmeasured],
        "crawl_incidents": [s["source"] for s in crawl_incidents],
        "content_weak": [s["source"] for s in content_weak],
        "sources": sources,
        "open_questions": [{
            "dimension": "未测量信源",
            "status": "data_gap" if unmeasured else "ok",
            "reason": f"{len(unmeasured)} 个源缺 availability/freshness 指标（从未计算），"
                      f"含官方源；此前被误报为低可用/陈旧"
                      if unmeasured else "全部源指标齐备",
            "unblock": "在 source_health 计算环节补齐这些源的指标（采集侧修复）",
        }, {
            "dimension": "authority 清单完备性",
            "status": "needs_human_review",
            "reason": "权威源清单为显式枚举，可能不完备",
            "unblock": "业务侧确认并扩充 AUTHORITY_SOURCES",
        }],
    }


def main(argv: list[str]) -> int:
    doc = build()
    if "--json" in argv:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0
    if not doc.get("available"):
        print(f"[source_os] {doc.get('note')}")
        return 0
    m = doc["meta"]
    print(f"[source_os] sources={m['source_count']} measured={m['measured_count']} "
          f"unmeasured={m['unmeasured_count']} authority={m['authority_count']} "
          f"crawl_incidents={m['crawl_incident_count']} content_weak={m['content_weak_count']} "
          f"watch={m['watch_content_count']}")
    if doc["unmeasured_sources"]:
        print(f"  未测量(补采, 非不健康) {doc['meta']['unmeasured_count']} 个:",
              ", ".join(doc["unmeasured_sources"][:5]))
    if doc["crawl_incidents"]:
        print("  抓取故障(修crawler, 非降权):", ", ".join(doc["crawl_incidents"][:5]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))