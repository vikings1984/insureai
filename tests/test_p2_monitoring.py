#!/usr/bin/env python3
"""P2.1 Continuous Monitoring 测试。

断言纪律（来自 P2 排序 bug 的教训）：变化/告警断言必须验证
*非零且类型正确*，不能只写 assertGreaterEqual(x, 0)。

Fixture 严格按真实引擎事件结构构造：
- `intelligence_score` 在 `scores` 字典内（引擎 `_intel_score` 读这里）；
- 实体经 `tags`（逗号串）抽取（引擎 `_entities` 读这里，而非顶层 entities）；
- 顶层 `entities` 供监控快照存储使用。
"""
import json
import unittest

from p2_monitoring import (
    build_today_map,
    resolve_canonical,
    detect_changes,
    filter_alerts,
    run_monitoring,
    DEFAULT_STORE,
)


def evt(fingerprint, intel=80, tags="", entities=None, **over):
    if entities is None:
        entities = [t.strip() for t in tags.split(",") if t.strip()] or ["A", "B"]
    over_intel = over.pop("intelligence_score", None)
    if over_intel is not None:
        intel = over_intel
    base = {
        "event_id": "evt_" + fingerprint[:12],
        "event_fingerprint": fingerprint,
        "title": over.pop("title", "故事"),
        "event_type": "industry_update",
        "entities": entities,
        "tags": tags,
        "topic": "ai_intelligent",
        "published_at": "2026-08-31T00:00:00+00:00",
        "source_count": 1,
        "article_count": 2,
        "scores": {"intelligence_score": intel, "confidence": 0.9},
        "evidence_status": "single_source",
        "review_required": False,
        "trust": {"level": "low", "conflict": False},
    }
    base.update(over)
    return base


def snapshot_in_store(fp, intel=80, tags="", entities=None, **over):
    e = evt(fp, intel=intel, tags=tags, entities=entities, **over)
    return {
        "canonical_id": fp,
        "title": e["title"],
        "event_type": e["event_type"],
        "topic": e["topic"],
        "published_at": e["published_at"],
        "article_count": e["article_count"],
        "source_count": e["source_count"],
        "intelligence_score": e["scores"]["intelligence_score"],
        "evidence_status": e["evidence_status"],
        "review_required": e["review_required"],
        "trust_level": e["trust"]["level"],
        "entities": e["entities"],
        "last_seen": "2026-08-30T00:00:00+00:00",
    }


class TestDetectChanges(unittest.TestCase):
    def test_developing_story_produces_expected_changes(self):
        fp = "fp1"
        seen = {fp: snapshot_in_store(fp, article_count=2, source_count=1,
                                      intelligence_score=80, evidence_status="single_source",
                                      entities=["A", "B"])}
        today = [evt(fp, article_count=4, source_count=2, intelligence_score=85,
                     evidence_status="multi_source", entities=["A", "B", "C"])]
        changes = detect_changes(build_today_map(today), seen, {fp: fp})
        types = {c["change_type"] for c in changes}
        # 必须有具体变化，而不是空列表或只有 NEW
        self.assertIn("NEW_EVIDENCE", types)
        self.assertIn("NEW_SOURCE", types)
        self.assertIn("SEVERITY_UP", types)
        self.assertIn("EVIDENCE_UPGRADED", types)
        self.assertIn("NEW_ENTITY", types)
        # 派生详情正确
        ev = next(c for c in changes if c["change_type"] == "NEW_ENTITY")
        self.assertEqual(ev["detail"]["added"], ["C"])
        se = next(c for c in changes if c["change_type"] == "SEVERITY_UP")
        self.assertEqual(se["detail"]["delta"], 5)

    def test_brand_new_event_is_NEW(self):
        seen = {}
        today = [evt("fp_new")]
        changes = detect_changes(build_today_map(today), seen, {"fp_new": "fp_new"})
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["change_type"], "NEW")

    def test_no_change_when_snapshot_identical(self):
        fp = "fp1"
        seen = {fp: snapshot_in_store(fp)}
        today = [evt(fp)]
        changes = detect_changes(build_today_map(today), seen, {fp: fp})
        self.assertEqual(changes, [])

    def test_severity_down_detected(self):
        fp = "fp1"
        seen = {fp: snapshot_in_store(fp, intelligence_score=90)}
        today = [evt(fp, intelligence_score=70)]
        changes = detect_changes(build_today_map(today), seen, {fp: fp})
        self.assertEqual([c["change_type"] for c in changes], ["SEVERITY_DOWN"])


class TestResolveCanonical(unittest.TestCase):
    def test_cross_month_linkage_by_anchor_and_similarity(self):
        # 上月见过的事件（不同 fingerprint，但同实体锚定、标题相似、30 天内）
        old_fp = "aug_fp"
        seen = {old_fp: snapshot_in_store(old_fp, published_at="2026-08-20T00:00:00+00:00",
                                          title="中国平安发布 AI 保险进展", entities=["平安", "AI"])}
        new_fp = "sep_fp"
        today = [evt(new_fp, published_at="2026-09-02T00:00:00+00:00",
                     title="中国平安继续推进 AI 保险", entities=["平安", "AI"])]
        mapping = resolve_canonical(build_today_map(today), seen)
        self.assertEqual(mapping[new_fp], old_fp)  # 跨月延续同一身份

    def test_no_linkage_when_anchor_differs(self):
        old_fp = "aug_fp"
        seen = {old_fp: snapshot_in_store(old_fp, title="中国平安 AI 保险", entities=["平安", "AI"])}
        new_fp = "sep_fp"
        today = [evt(new_fp, title="人保 AI 保险", entities=["人保", "AI"])]  # 不同锚定实体
        mapping = resolve_canonical(build_today_map(today), seen)
        self.assertEqual(mapping[new_fp], new_fp)  # 视为新事件


class TestFilterAlerts(unittest.TestCase):
    def test_watchlist_match_emits_alert(self):
        fp = "fp1"
        state = {"watchlists": [{"id": "ai", "name": "AI保险", "topics": ["ai_intelligent"],
                                 "keywords": [], "priority_boost": 8, "enabled": True}],
                 "monitoring": []}
        changes = [{"canonical_id": fp, "title": "x", "topic": "ai_intelligent",
                    "change_type": "NEW_EVIDENCE", "generated_at": "2026-08-31T00:00:00+00:00", "now": {"entities": ["A"], "topic": "ai_intelligent"}}]
        alerts = filter_alerts(changes, state, DEFAULT_STORE)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["watchlist_id"], "ai")
        self.assertEqual(alerts[0]["severity"], "high")

    def test_snoozed_monitor_suppresses_alert(self):
        fp = "fp1"
        state = {"watchlists": [{"id": "ai", "name": "AI保险", "topics": ["ai_intelligent"],
                                 "keywords": [], "priority_boost": 8, "enabled": True}],
                 "monitoring": [{"watchlist_id": "ai", "event_id": fp, "status": "snoozed"}]}
        changes = [{"canonical_id": fp, "title": "x", "topic": "ai_intelligent",
                    "change_type": "NEW_EVIDENCE", "generated_at": "2026-08-31T00:00:00+00:00", "now": {"entities": ["A"], "topic": "ai_intelligent"}}]
        alerts = filter_alerts(changes, state, DEFAULT_STORE)
        self.assertEqual(alerts, [])

    def test_unwatched_event_no_alert(self):
        fp = "fp_other"
        state = {"watchlists": [{"id": "ai", "name": "AI保险", "topics": ["ai_intelligent"],
                                 "keywords": [], "priority_boost": 8, "enabled": True}],
                 "monitoring": []}
        changes = [{"canonical_id": fp, "title": "x", "topic": "health_insurance",
                    "change_type": "NEW_EVIDENCE", "generated_at": "2026-08-31T00:00:00+00:00", "now": {"entities": ["Z"], "topic": "health_insurance"}}]
        alerts = filter_alerts(changes, state, DEFAULT_STORE)
        self.assertEqual(alerts, [])


class TestRunMonitoringIntegration(unittest.TestCase):
    def test_first_run_alerts_then_second_run_dedups(self):
        state = {"watchlists": [{"id": "ai", "name": "AI保险", "topics": ["ai_intelligent"],
                                 "keywords": [], "priority_boost": 8, "enabled": True}],
                 "monitoring": [], "feedback": []}
        fp = "fp1"
        store = json_copy(DEFAULT_STORE)
        # 第一次：全新事件命中关注清单 → 应产生 NEW 告警
        r1 = run_monitoring([evt(fp)], state=state, store=store, persist=False)
        self.assertGreaterEqual(r1["alert_count"], 1)
        self.assertEqual(r1["changes"][0]["change_type"], "NEW")

        # 把该事件写入 seen（模拟已持久化），再次跑同样事件 → 不应再报 NEW
        store["seen"] = {fp: snapshot_in_store(fp)}
        r2 = run_monitoring([evt(fp)], state=state, store=store, persist=False)
        self.assertEqual([c["change_type"] for c in r2["changes"]], [])  # 无变化
        self.assertEqual(r2["alert_count"], 0)  # 无重复告警

    def test_developing_story_alerts_on_evidence_growth_only_once(self):
        state = {"watchlists": [{"id": "ai", "name": "AI保险", "topics": ["ai_intelligent"],
                                 "keywords": [], "priority_boost": 8, "enabled": True}],
                 "monitoring": [], "feedback": []}
        fp = "fp1"
        store = json_copy(DEFAULT_STORE)
        store["seen"] = {fp: snapshot_in_store(fp, article_count=2, source_count=1,
                                              intelligence_score=80, evidence_status="single_source",
                                              entities=["A", "B"])}
        today = [evt(fp, article_count=5, source_count=3, intelligence_score=88,
                     evidence_status="multi_source", entities=["A", "B", "C", "D"])]
        r = run_monitoring(today, state=state, store=store, persist=False)
        types = {a["change_type"] for a in r["alerts"]}
        self.assertIn("NEW_EVIDENCE", types)
        self.assertIn("NEW_SOURCE", types)
        # 一次运行内同一事件不应重复报同类变化
        self.assertEqual(len([a for a in r["alerts"] if a["change_type"] == "NEW_EVIDENCE"]), 1)


def json_copy(d):
    return json.loads(json.dumps(d))


if __name__ == "__main__":
    unittest.main()
