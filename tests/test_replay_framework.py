"""P1-5 Replay Framework：重放结果压平、基线存档与回归对比。

不执行真实重放（production_replay 会跑两遍 build，很慢），全部用注入的假 result，
结果完全确定。

覆盖：
  - flatten 正确压平嵌套结构，且对缺失/None 容错
  - compare：稳定 → regression=False
  - compare：replay_stability / article_coverage 下降 → 劣化
  - compare：duplicate_* 上升 → 劣化
  - compare：信息类指标（event_count 等）变化**不**判劣化（避免数据量波动产生假告警）
  - compare：status 由 ok 退化为 unavailable → status_regressed（最严重档）
  - compare：缺文档 → error=missing_document
  - save_result / save_baseline / load_* 往返
"""
import json
import os
import shutil
import tempfile
import unittest

import replay_framework


def _result(status="ok", stability=1.0, coverage=0.95, dup_events=0, dup_articles=0,
            event_count=120, sample_count=500, diversity=40, top_share=0.08):
    return {
        "status": status,
        "input_count": 3000,
        "sample_count": sample_count,
        "event_count": event_count,
        "quality": {
            "replay_stability": stability,
            "event_integrity": {
                "duplicate_event_ids": dup_events,
                "duplicate_article_assignments": dup_articles,
                "article_coverage": coverage,
            },
            "source_diversity": diversity,
            "top_source_share": top_share,
        },
    }


def _doc(**kw):
    return {
        "version": "1.0",
        "generated_at": "2026-10-07T00:00:00+00:00",
        "commit": "abc123",
        "metrics": replay_framework.flatten(_result(**kw)),
        "result": _result(**kw),
    }


class TestFlatten(unittest.TestCase):
    def test_flatten_nested(self):
        m = replay_framework.flatten(_result(stability=0.98, coverage=0.9,
                                             dup_events=2, dup_articles=3))
        self.assertEqual(m["status"], "ok")
        self.assertEqual(m["replay_stability"], 0.98)
        self.assertEqual(m["article_coverage"], 0.9)
        self.assertEqual(m["duplicate_event_ids"], 2)
        self.assertEqual(m["duplicate_article_assignments"], 3)
        self.assertEqual(m["event_count"], 120)
        self.assertEqual(m["source_diversity"], 40)

    def test_flatten_tolerates_empty_and_none(self):
        m = replay_framework.flatten({})
        self.assertEqual(m["status"], "unknown")
        self.assertEqual(m["replay_stability"], 0.0)
        m2 = replay_framework.flatten(None)
        self.assertEqual(m2["article_coverage"], 0.0)
        m3 = replay_framework.flatten({"status": "unavailable", "quality": None})
        self.assertEqual(m3["status"], "unavailable")
        self.assertEqual(m3["duplicate_event_ids"], 0.0)


class TestCompare(unittest.TestCase):
    def test_identical_has_no_regression(self):
        out = replay_framework.compare(_doc(), _doc())
        self.assertFalse(out["regression"])
        self.assertFalse(out["status_regressed"])
        for k in replay_framework.REGRESSION_METRICS:
            self.assertFalse(out["deltas"][k]["worse"])

    def test_stability_drop_is_regression(self):
        out = replay_framework.compare(_doc(stability=0.90), _doc(stability=1.0))
        self.assertTrue(out["deltas"]["replay_stability"]["worse"])
        self.assertTrue(out["regression"])

    def test_coverage_drop_is_regression(self):
        out = replay_framework.compare(_doc(coverage=0.80), _doc(coverage=0.95))
        self.assertTrue(out["deltas"]["article_coverage"]["worse"])
        self.assertTrue(out["regression"])

    def test_duplicates_rising_is_regression(self):
        out = replay_framework.compare(_doc(dup_events=5, dup_articles=7),
                                       _doc(dup_events=0, dup_articles=0))
        self.assertTrue(out["deltas"]["duplicate_event_ids"]["worse"])
        self.assertTrue(out["deltas"]["duplicate_article_assignments"]["worse"])
        self.assertTrue(out["regression"])

    def test_informational_changes_do_not_regress(self):
        """event_count 等只记录 delta，不判回归（数据量自然波动不该产生假告警）。"""
        out = replay_framework.compare(_doc(event_count=90, sample_count=400, diversity=30),
                                       _doc(event_count=120, sample_count=500, diversity=40))
        self.assertFalse(out["regression"])
        for k in replay_framework.INFORMATIONAL_METRICS:
            self.assertFalse(out["deltas"][k]["worse"])
            self.assertTrue(out["deltas"][k]["informational"])
        self.assertEqual(out["deltas"]["event_count"]["delta"], -30)

    def test_status_degrades_is_critical_regression(self):
        out = replay_framework.compare(_doc(status="unavailable"), _doc(status="ok"))
        self.assertTrue(out["status_regressed"])
        self.assertTrue(out["regression"])

    def test_missing_document(self):
        out = replay_framework.compare(None, _doc())
        self.assertEqual(out["error"], "missing_document")
        self.assertFalse(out["has_current"])
        out2 = replay_framework.compare(_doc(), None)
        self.assertEqual(out2["error"], "missing_document")
        self.assertFalse(out2["has_baseline"])

    def test_compare_reports_commits(self):
        cur = _doc()
        cur["commit"] = "newsha"
        out = replay_framework.compare(cur, _doc())
        self.assertEqual(out["current"]["commit"], "newsha")
        self.assertEqual(out["baseline"]["commit"], "abc123")


class TestPersist(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_and_load_roundtrip(self):
        path = os.path.join(self.tmp, "r.json")
        doc = _doc(stability=0.97)
        replay_framework.save_result(doc, path)
        back = replay_framework.load_document(path)
        self.assertEqual(back["metrics"]["replay_stability"], 0.97)
        self.assertEqual(back["commit"], "abc123")

    def test_save_baseline_and_load_baseline(self):
        path = os.path.join(self.tmp, "b.json")
        replay_framework.save_baseline(_doc(dup_events=1), path)
        base = replay_framework.load_baseline(path)
        self.assertEqual(base["metrics"]["duplicate_event_ids"], 1)

    def test_load_missing_returns_none(self):
        self.assertIsNone(replay_framework.load_document(os.path.join(self.tmp, "nope.json")))

    def test_load_corrupt_returns_none(self):
        path = os.path.join(self.tmp, "bad.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertIsNone(replay_framework.load_document(path))

    def test_build_document_has_metadata(self):
        doc = replay_framework.build_document(_result())
        self.assertEqual(doc["version"], "1.0")
        self.assertTrue(doc["generated_at"])
        self.assertTrue(doc["commit"])
        self.assertIn("replay_stability", doc["metrics"])


if __name__ == "__main__":
    unittest.main()
