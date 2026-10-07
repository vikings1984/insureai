#!/usr/bin/python3
"""P0-C 下游 CE 联动审计（observability.section_ce_linkage）单元测试。

不依赖生产产物：用临时目录写入合成 fixture，并 monkeypatch observability.HERE，
断言 review / monitoring / decision 三类下游表面的 CE 联动比例与告警行为。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

import observability


def _write(d: str, name: str, obj) -> None:
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


class TestCeLinkage(unittest.TestCase):
    def _setup(self, fixtures: dict) -> str:
        d = tempfile.mkdtemp()
        for name, obj in fixtures.items():
            _write(d, name, obj)
        self._orig_here = observability.HERE
        observability.HERE = d
        return d

    def tearDown(self):
        if hasattr(self, "_orig_here"):
            observability.HERE = self._orig_here

    def test_healthy_when_all_linked(self):
        d = self._setup({
            "canonical_events.json": {
                "canonical_events": {"cev_a": {}, "cev_b": {}},
                "by_event_id": {"evt_1": "cev_a", "evt_2": "cev_b"},
            },
            "decisions_pending.json": {
                "funnel": {"now": [{"canonical_event_id": "cev_a"}],
                           "soon": [{"canonical_event_id": "cev_b"}], "watch": []},
            },
            "p2_alerts.json": {"semantic_alerts": [{"ceid": "cev_a"}]},
            "review_queue.json": {"items": [{"event_id": "evt_1"},
                                            {"event_id": "evt_2"}]},
        })
        alerts: list[dict] = []
        sec = observability.section_ce_linkage(alerts)
        self.assertEqual(sec["status"], "healthy")
        self.assertEqual(sec["ce_pool_size"], 2)
        self.assertEqual(sec["unresolved_review_event_ids"], 0)
        for name in ("decision", "monitoring", "review"):
            self.assertEqual(sec["surfaces"][name]["ratio"], 1.0)
        self.assertFalse([a for a in alerts if a["code"] == "CE_LINKAGE_GAP"])

    def test_gap_detected_and_warned(self):
        d = self._setup({
            "canonical_events.json": {
                "canonical_events": {"cev_a": {}, "cev_b": {}},
                "by_event_id": {"evt_1": "cev_a", "evt_2": "cev_b"},
            },
            # 1 条决策项 canonical_event_id 缺失
            "decisions_pending.json": {
                "funnel": {"now": [{"canonical_event_id": "cev_a"}],
                           "soon": [{"canonical_event_id": "MISSING"}],
                           "watch": [{"canonical_event_id": "cev_b"}]},
            },
            # 1 条 monitoring 告警 ceid 缺失
            "p2_alerts.json": {"semantic_alerts": [{"ceid": "cev_a"},
                                                   {"ceid": "MISSING"}]},
            # 1 条 review event_id 无法解析到 CE 池
            "review_queue.json": {"items": [{"event_id": "evt_1"},
                                            {"event_id": "evt_unknown"}]},
        })
        alerts: list[dict] = []
        sec = observability.section_ce_linkage(alerts)
        self.assertEqual(sec["status"], "degraded")
        self.assertEqual(sec["surfaces"]["decision"],
                         {"total": 3, "linked": 2, "ratio": 0.6667})
        self.assertEqual(sec["surfaces"]["monitoring"],
                         {"total": 2, "linked": 1, "ratio": 0.5})
        self.assertEqual(sec["surfaces"]["review"],
                         {"total": 2, "linked": 1, "ratio": 0.5})
        self.assertEqual(sec["unresolved_review_event_ids"], 1)
        self.assertTrue([a for a in alerts if a["code"] == "CE_LINKAGE_GAP"])
        # 告警级别为 warning（不破坏 fail-closed 安全门）
        self.assertTrue(all(a["severity"] == "warning"
                            for a in alerts if a["code"] == "CE_LINKAGE_GAP"))

    def test_empty_monitoring_is_vacuously_healthy(self):
        d = self._setup({
            "canonical_events.json": {
                "canonical_events": {"cev_a": {}},
                "by_event_id": {"evt_1": "cev_a"},
            },
            "decisions_pending.json": {
                "funnel": {"now": [{"canonical_event_id": "cev_a"}],
                           "soon": [], "watch": []},
            },
            "p2_alerts.json": {"semantic_alerts": []},  # 无告警
            "review_queue.json": {"items": [{"event_id": "evt_1"}]},
        })
        alerts: list[dict] = []
        sec = observability.section_ce_linkage(alerts)
        self.assertEqual(sec["surfaces"]["monitoring"]["ratio"], 1.0)
        self.assertEqual(sec["status"], "healthy")

    def test_unavailable_when_pool_missing(self):
        d = self._setup({
            "decisions_pending.json": {"funnel": {"now": [], "soon": [], "watch": []}},
            "p2_alerts.json": {"semantic_alerts": []},
            "review_queue.json": {"items": []},
        })
        alerts: list[dict] = []
        sec = observability.section_ce_linkage(alerts)
        self.assertEqual(sec["status"], "unavailable")
        self.assertTrue([a for a in alerts if a["code"] == "CE_LINKAGE_UNAVAILABLE"])


if __name__ == "__main__":
    unittest.main()
