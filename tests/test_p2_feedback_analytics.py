#!/usr/bin/env python3
"""P2.2 Decision Feedback Analytics 测试。

断言纪律（延续 P2.1）：指标断言必须验证*计算值正确且类型正确*，
不能只写 assertGreaterEqual(x, 0)——那会放过把全部事件误判为噪声的回归。

指标来自评估报告的 Feedback Analytics 表：
  hit_rate  = (acted_on + important + useful) / total
  dismiss_rate = (noise + irrelevant) / total
  action_rate  = acted_on / total
  repeat_exposure_rate = 被反馈>1次的事件数 / 去重事件数
  false_positive_rate = incorrect / total
  scored_coverage = 带 importance/confidence 的比例
"""
import json
import tempfile
import unittest
from pathlib import Path

import p2_feedback_analytics as fa


def fb(event_id, label, **over):
    row = {"event_id": event_id, "label": label, "note": "",
           "importance": None, "confidence": None, "outcome": None,
           "user_id": None, "created_at": "2026-08-31T00:00:00+00:00"}
    row.update(over)
    return row


def sample_feedback():
    return [
        fb("e1", "acted_on"),                    # positive + action
        fb("e1", "important"),                   # positive, e1 第二次出现 → 重复曝光
        fb("e2", "noise"),                       # dismiss
        fb("e3", "incorrect"),                   # false positive
        fb("e4", "useful", importance=4, confidence=5),  # positive + 已评分
    ]


class TestEmptyFeedback(unittest.TestCase):
    def test_empty_returns_zero_baseline(self):
        r = fa.feedback_analytics([])
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["distinct_events"], 0)
        self.assertEqual(r["by_label"], {})
        # 零反馈时所有比率必须是 0.0（float），不是 None / 占位
        for key in ("hit_rate", "dismiss_rate", "action_rate",
                    "repeat_exposure_rate", "false_positive_rate", "scored_coverage"):
            self.assertAlmostEqual(r[key], 0.0)
            self.assertIsInstance(r[key], float)


class TestMetrics(unittest.TestCase):
    def test_totals(self):
        r = fa.feedback_analytics(sample_feedback())
        self.assertEqual(r["total"], 5)
        self.assertEqual(r["distinct_events"], 4)   # e1 重复，去重后 4
        self.assertEqual(r["by_label"], {"acted_on": 1, "important": 1,
                                          "noise": 1, "incorrect": 1, "useful": 1})

    def test_hit_rate(self):
        r = fa.feedback_analytics(sample_feedback())
        self.assertAlmostEqual(r["hit_rate"], 3 / 5)   # acted_on+important+useful = 3

    def test_dismiss_rate(self):
        r = fa.feedback_analytics(sample_feedback())
        self.assertAlmostEqual(r["dismiss_rate"], 1 / 5)  # noise = 1

    def test_action_rate(self):
        r = fa.feedback_analytics(sample_feedback())
        self.assertAlmostEqual(r["action_rate"], 1 / 5)   # acted_on = 1

    def test_false_positive_rate(self):
        r = fa.feedback_analytics(sample_feedback())
        self.assertAlmostEqual(r["false_positive_rate"], 1 / 5)  # incorrect = 1

    def test_repeat_exposure_rate(self):
        r = fa.feedback_analytics(sample_feedback())
        # 4 个去重事件，e1 出现 2 次 → repeat=1 → 1/4
        self.assertAlmostEqual(r["repeat_exposure_rate"], 1 / 4)

    def test_scored_coverage(self):
        r = fa.feedback_analytics(sample_feedback())
        self.assertAlmostEqual(r["scored_coverage"], 1 / 5)  # 仅 e4 带评分

    def test_all_rates_in_unit_interval(self):
        r = fa.feedback_analytics(sample_feedback())
        for key in ("hit_rate", "dismiss_rate", "action_rate",
                    "repeat_exposure_rate", "false_positive_rate", "scored_coverage"):
            self.assertGreaterEqual(r[key], 0.0)
            self.assertLessEqual(r[key], 1.0)


class TestRunPersist(unittest.TestCase):
    def test_run_writes_versioned_report(self):
        state = {"version": "p2-v1.0", "feedback": sample_feedback(),
                 "watchlists": [], "monitoring": []}
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "p2_feedback_analytics.json"
            fa.OUTPUT_PATH = tmp
            result = fa.run(state, persist=True)
            self.assertEqual(result["version"], "p2.2-v1.0")
            self.assertTrue(tmp.exists())
            written = json.loads(tmp.read_text(encoding="utf-8"))
            self.assertEqual(written["version"], "p2.2-v1.0")
            self.assertAlmostEqual(written["analytics"]["hit_rate"], 3 / 5)
            # 还原，避免污染模块级常量
            fa.OUTPUT_PATH = Path(__file__).resolve().parent.parent / "p2_feedback_analytics.json"

    def test_run_persist_false_does_not_write(self):
        state = {"version": "p2-v1.0", "feedback": sample_feedback()}
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "should_not_exist.json"
            fa.OUTPUT_PATH = tmp
            fa.run(state, persist=False)
            self.assertFalse(tmp.exists())
            fa.OUTPUT_PATH = Path(__file__).resolve().parent.parent / "p2_feedback_analytics.json"


if __name__ == "__main__":
    unittest.main()
