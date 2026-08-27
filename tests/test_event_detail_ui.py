#!/usr/bin/env python3
"""Event Detail UI 契约测试。

ED-1（v1.5 路线图 P0-4）：intelligence.html 的事件详情必须是
"What happened → 关键 Claims → Evidence → 冲突证据 → 建议 → Human Review"
六区块决策卡片，且渲染的全部字段只来自 intelligence.json / review_queue.json，
不得引入 artifact 之外的事实。
"""
import re
import unittest
from pathlib import Path

from benchmark import news
from claims import build_claims
from decision import ROLE_ACTIONS, build_decisions
from intelligence import build
from review import build_review_queue
from trust import summarize_event_trust

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "intelligence.html"

BLOCK_ORDER = ["what-happened", "claims", "evidence", "conflicts", "recommendation", "review"]

JS_METHODS = {
    "filter", "forEach", "get", "getElementById", "indexOf", "innerHTML",
    "isArray", "join", "keys", "length", "map", "push", "set", "values",
}
STATE_FIELDS = {"data", "reviewQueue"}
# 渲染器内部构造的字段（证据合并视图），不来自 artifact
RENDERER_INTERNAL = {"spans"}

ARTIFACT_FIELDS = {
    "event_id", "title", "event_type", "topic_label", "evidence", "evidence_coverage",
    "evidence_status", "review_required", "source_count", "insight", "trust", "claims", "scores",
    "what_happened", "why_it_matters", "who_is_affected", "what_to_watch", "human_review_required",
    "signals", "coverage", "cross_checked", "conflicted",
    "claim_text", "verification_status", "confidence", "evidence_count", "independent_domains",
    "supporting_evidence", "contradicting_evidence", "context_evidence",
    "evidence_id", "source_name", "source_url", "source_tier", "published_at", "matched_span", "relation",
    "level", "conflict", "conflict_fields",
    "decisions", "decisions_by_role", "action", "urgency", "urgency_label", "guardrail", "basis",
    "context", "business_impact", "affected_functions", "potential_opportunity", "potential_risk",
    "what_to_monitor", "recommended_next_step", "label", "impact",
    "trust_level", "temporal_phase",
    "priority", "status", "reasons", "reason",
}


def renderer_body() -> str:
    text = PAGE.read_text(encoding="utf-8")
    start = text.index("/* detail-renderer:start")
    end = text.index("/* detail-renderer:end")
    body = text[start:end]
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    body = re.sub(r"//[^\n]*", "", body)
    return body.replace("...", " ")


def _synthetic_intelligence() -> dict:
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


def _collect_keys(value, collected: set) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            collected.add(str(key))
            _collect_keys(child, collected)
    elif isinstance(value, list):
        for child in value:
            _collect_keys(child, collected)


class EventDetailUiContractTests(unittest.TestCase):
    def test_six_blocks_present_in_order(self):
        text = PAGE.read_text(encoding="utf-8")
        blocks = re.findall(r'data-detail-block="([a-z-]+)"', text)
        self.assertEqual(blocks, BLOCK_ORDER)

    def test_verification_badges_cover_all_statuses(self):
        body = renderer_body()
        for status in ("cross_checked", "single_source", "conflicted", "unverified"):
            self.assertIn(status, body)
        for label in ("已交叉验证", "单一来源", "证据冲突", "待验证"):
            self.assertIn(label, body)

    def test_tier_and_relation_badges_present(self):
        text = PAGE.read_text(encoding="utf-8")
        for tier in range(1, 5):
            self.assertIn(f".tier-{tier}", text)
        for rel in ("support", "contradict", "context"):
            self.assertIn(f".rel-{rel}", text)

    def test_renderer_reads_only_whitelisted_fields(self):
        body = renderer_body()
        accessed = set(re.findall(r"\.([A-Za-z_][A-Za-z0-9_]*)", body))
        allowed = ARTIFACT_FIELDS | JS_METHODS | STATE_FIELDS | RENDERER_INTERNAL
        unexpected = accessed - allowed
        self.assertFalse(unexpected, f"detail 渲染读取了白名单之外的字段: {sorted(unexpected)}")

    def test_whitelist_is_artifact_grounded(self):
        data = _synthetic_intelligence()
        queue = build_review_queue(data)
        collected = set()
        _collect_keys(data, collected)
        _collect_keys(queue, collected)
        ungrounded = ARTIFACT_FIELDS - collected
        self.assertFalse(ungrounded, f"白名单字段未出现在合成 artifact 中: {sorted(ungrounded)}")

    def test_review_block_backed_by_review_queue_artifact(self):
        text = PAGE.read_text(encoding="utf-8")
        self.assertIn("review_queue.json", text)
        body = renderer_body()
        self.assertIn("reviewItem.reasons", body)
        self.assertIn("r.reason", body)

    def test_renderer_reads_key_ed1_fields(self):
        body = renderer_body()
        for field in (
            "what_happened", "verification_status", "source_tier", "matched_span",
            "contradicting_evidence", "guardrail", "urgency_label", "conflict_fields",
            "evidence_status", "priority",
        ):
            self.assertIn(field, body)

    def test_renderer_reads_decision_context_fields(self):
        body = renderer_body()
        for field in (
            "decisions_by_role", "affected_functions", "potential_opportunity",
            "potential_risk", "what_to_monitor", "recommended_next_step",
        ):
            self.assertIn(field, body)


if __name__ == "__main__":
    unittest.main()
