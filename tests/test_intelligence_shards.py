#!/usr/bin/env python3
"""intelligence.json 分片契约测试（P0-1 首屏瘦身）。

分片是 intelligence.json 的**投影**：只裁剪，不重排、不重算、不改写。
这组测试锁死四条纪律：

  1. 无损 —— 源事件的每个顶层字段都必须落在索引或详情分片里，
     除了显式登记为可丢弃的字段（新增字段必须显式表态，否则测试失败）；
  2. 一致 —— version / generated_at / stats / 事件顺序 / 逐字段值必须与源相等；
  3. 可发现 —— 每个事件有且只有一个详情分块，且 detail_chunk 指向的分块正确；
  4. fail-closed —— 上面任何一处被破坏，verify() 必须报错。

以及一条目的性断言：首屏分片不得携带全量事件列表（否则分片就失去意义）。
"""
import copy
import unittest
from pathlib import Path

import intelligence_shards as shards
from benchmark import news
from claims import build_claims
from decision import ROLE_ACTIONS, build_decisions
from intelligence import build
from trust import summarize_event_trust

ROOT = Path(__file__).resolve().parent.parent

# 明确登记为「不进分片」的事件字段。
# 判定依据：前端（*.html / *.js）没有任何一处读取它们；它们只服务于
# 采集与回放等后端流程，而那些流程读的是权威产物 intelligence.json。
DROPPABLE_EVENT_FIELDS = {"event_fingerprint", "event_fingerprint_version", "article_ids"}


def synthetic_intelligence() -> dict:
    rows = [
        news({"id": "r1", "title": "Munich Re to acquire At-Bay for $575 million", "source": "Reuters",
              "published_at": "2026-08-21T10:00:00+00:00", "tags": "Munich Re,At-Bay", "topic": "capital_reinsurance"}),
        news({"id": "ij1", "title": "Munich Re agrees to buy At-Bay for $575 million", "source": "Insurance Journal",
              "published_at": "2026-08-21T11:00:00+00:00", "tags": "Munich Re,At-Bay", "topic": "capital_reinsurance"}),
        news({"id": "p1", "title": "PERILS estimates storm Goretti industry loss at EUR 468 million", "source": "Reuters",
              "published_at": "2026-08-21T12:00:00+00:00", "tags": "PERILS", "topic": "climate_catastrophe"}),
        news({"id": "p2", "title": "PERILS cuts storm Goretti industry loss estimate to EUR 480 million", "source": "Insurance Journal",
              "published_at": "2026-08-21T13:00:00+00:00", "tags": "PERILS", "topic": "climate_catastrophe"}),
        news({"id": "s1", "title": "Regulator issues new insurance AI guidance", "source": "Reuters",
              "published_at": "2026-08-21T14:00:00+00:00", "tags": "Regulator", "topic": "regulatory_change"}),
    ]
    data = build({"news": rows})
    by_id = {str(row["id"]): row for row in rows}
    for event in data["events"]:
        items = [by_id[str(i)] for i in event.get("article_ids", []) if str(i) in by_id]
        event["trust"] = summarize_event_trust(items, event)
        event["claims"] = build_claims(items, event)
    temporal = {"topic_signals": [{"topic": "capital_reinsurance", "phase": "accelerating", "signal_strength": 90}]}
    data["decisions_by_role"] = {role: build_decisions(data["events"], temporal, role)[:12] for role in ROLE_ACTIONS}
    data["decisions"] = data["decisions_by_role"]["executive"]
    return data


def built(data: dict):
    result = shards.build(data)
    return result["summary"], result["events"], result["chunks"], result["problems"]


class ShardProjectionTests(unittest.TestCase):
    def test_projection_is_lossless_for_event_fields(self):
        """源事件的每个顶层字段都必须有归属，新增字段必须显式表态。"""
        data = synthetic_intelligence()
        self.assertTrue(data["events"], "合成数据必须产生事件")
        covered = set(shards.LEAN_FIELDS) | set(shards.DETAIL_FIELDS)
        for event in data["events"]:
            unassigned = set(event) - covered - DROPPABLE_EVENT_FIELDS
            self.assertFalse(
                unassigned,
                f"事件字段 {sorted(unassigned)} 既不在索引也不在详情分片里；"
                f"请在 intelligence_shards.py 中补充归档，或登记为可丢弃",
            )

    def test_build_reports_no_consistency_problems(self):
        _, _, _, problems = built(synthetic_intelligence())
        self.assertEqual(problems, [])

    def test_summary_omits_full_event_list(self):
        """首屏分片的意义就在于不带全量事件。"""
        summary, _, _, _ = built(synthetic_intelligence())
        self.assertNotIn("events", summary)
        self.assertEqual(summary["shard"]["kind"], "summary")

    def test_summary_matches_source_header_and_stats(self):
        data = synthetic_intelligence()
        summary, _, _, _ = built(data)
        self.assertEqual(summary["version"], data["version"])
        self.assertEqual(summary["generated_at"], data["generated_at"])
        self.assertEqual(summary["stats"], data["stats"])

    def test_summary_daily_brief_carries_claims(self):
        """首屏的命题 UI 需要 claims，而 daily_brief 本身不带，必须由分片补齐。"""
        data = synthetic_intelligence()
        summary, _, _, _ = built(data)
        by_id = {str(e["event_id"]): e for e in data["events"]}
        self.assertTrue(summary["daily_brief"], "分片必须保留 daily_brief")
        for row in summary["daily_brief"]:
            self.assertEqual(row["claims"], by_id[str(row["event_id"])].get("claims") or {})

    def test_summary_decisions_by_role_is_source_prefix(self):
        data = synthetic_intelligence()
        summary, _, _, _ = built(data)
        for role, rows in data["decisions_by_role"].items():
            self.assertEqual(
                summary["decisions_by_role"][role],
                rows[: shards.SUMMARY_ROLE_LIMIT],
                f"{role} 的角色决策卡不是源的前缀",
            )

    def test_events_shard_preserves_order_and_values(self):
        data = synthetic_intelligence()
        _, events_doc, _, _ = built(data)
        lean_rows = events_doc["events"]
        self.assertEqual(len(lean_rows), len(data["events"]))
        for lean, full in zip(lean_rows, data["events"]):
            self.assertEqual(lean["event_id"], full["event_id"])
            for field in shards.LEAN_FIELDS:
                if field in full:
                    self.assertEqual(lean[field], full[field], f"{field} 与源不一致")
            self.assertEqual(lean["trust"]["level"], (full.get("trust") or {}).get("level"))
            self.assertEqual(lean["claims"]["conflicted"], (full.get("claims") or {}).get("conflicted"))

    def test_each_event_has_exactly_one_detail_chunk(self):
        data = synthetic_intelligence()
        _, events_doc, chunks, _ = built(data)
        seen = {}
        for key, bucket in chunks.items():
            for event_id in bucket:
                self.assertNotIn(event_id, seen, f"{event_id} 出现在多个分块")
                seen[event_id] = key
        self.assertEqual(set(seen), {str(e["event_id"]) for e in data["events"]})
        for i, lean in enumerate(events_doc["events"]):
            self.assertEqual(lean["detail_chunk"], shards.chunk_of(i))
            self.assertEqual(seen[str(lean["event_id"])], lean["detail_chunk"])

    def test_detail_chunks_reproduce_source_detail_fields(self):
        data = synthetic_intelligence()
        _, _, chunks, _ = built(data)
        for event in data["events"]:
            bucket = chunks[shards.chunk_of(data["events"].index(event))]
            entry = bucket[str(event["event_id"])]
            for field in shards.DETAIL_FIELDS:
                if field in event:
                    self.assertEqual(entry[field], event[field], f"{field} 与源不一致")


class ShardFailClosedTests(unittest.TestCase):
    """分片一致性门禁必须 fail-closed：任何偏差都要被 verify() 拦下。"""

    def test_stat_tampering_is_caught(self):
        data = synthetic_intelligence()
        summary, events_doc, chunks, _ = built(data)
        tampered = copy.deepcopy(summary)
        key = next(iter(tampered["stats"]))
        tampered["stats"][key] = "tampered"
        self.assertTrue(shards.verify(data, tampered, events_doc, chunks))

    def test_version_drift_is_caught(self):
        data = synthetic_intelligence()
        summary, events_doc, chunks, _ = built(data)
        tampered = copy.deepcopy(summary)
        tampered["version"] = (data["version"] or 0) + 1
        self.assertTrue(shards.verify(data, tampered, events_doc, chunks))

    def test_reordered_events_are_caught(self):
        data = synthetic_intelligence()
        summary, events_doc, chunks, _ = built(data)
        tampered = copy.deepcopy(events_doc)
        if len(tampered["events"]) >= 2:
            tampered["events"][0], tampered["events"][1] = tampered["events"][1], tampered["events"][0]
        self.assertTrue(shards.verify(data, summary, tampered, chunks))

    def test_missing_detail_chunk_is_caught(self):
        data = synthetic_intelligence()
        summary, events_doc, chunks, _ = built(data)
        tampered = copy.deepcopy(chunks)
        first = next(iter(tampered))
        if len(tampered[first]) > 1:
            tampered[first].pop(next(iter(tampered[first])))
            self.assertTrue(shards.verify(data, summary, events_doc, tampered))

    def test_dropped_event_is_caught(self):
        data = synthetic_intelligence()
        summary, events_doc, chunks, _ = built(data)
        tampered = copy.deepcopy(events_doc)
        tampered["events"].pop()
        self.assertTrue(shards.verify(data, summary, tampered, chunks))


class ShardRepoWiringTests(unittest.TestCase):
    """分片不入库、部署时生成 —— 这两条约定必须体现在仓库配置里。"""

    def test_shards_are_gitignored(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in ("intelligence.summary.json", "intelligence.events.json", "intelligence.detail.*.json"):
            self.assertIn(pattern, text, f"{pattern} 未登记进 .gitignore")

    def test_deploy_workflow_generates_shards(self):
        text = (ROOT / ".github" / "workflows" / "deploy-cloudflare.yml").read_text(encoding="utf-8")
        self.assertIn("intelligence_shards.py", text)

    def test_data_store_falls_back_without_shards(self):
        """分片缺失时必须回退全量，而不是白屏。"""
        text = (ROOT / "data-store.js").read_text(encoding="utf-8")
        self.assertIn("loadSummary", text)
        self.assertIn("loadIndex", text)
        self.assertIn("loadDetail", text)


if __name__ == "__main__":
    unittest.main()
