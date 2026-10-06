"""P0-6 Quality Registry：质量档案归档与版本比较回归。

覆盖：
  - record 写入 quality/<commit>.json / latest.json / index.json
  - 同 commit 重复 record 幂等（索引只有一条）
  - load / latest / list_records 查询
  - compare：无劣化 → regression=False；劣化（macro 下降 / safety 转 False /
    false_merge 上升 / single_source_false_cross_check 上升）→ regression=True
  - 缺失档案 → error=missing_record

测试用临时目录替换 QUALITY_DIR / INDEX_PATH / LATEST_PATH，不污染仓库真实 quality/。
"""
import copy
import os
import shutil
import tempfile
import unittest

import quality_registry


def _results(macro=1.0, safety=True, false_merge=0.0, false_split=0.0,
             single_source_false=0.0, unsafe_now=0.0):
    return {
        "version": 2,
        "benchmark": "insureai_core_benchmark",
        "macro_quality": macro,
        "safety_pass": safety,
        "event": {
            "precision": 1.0, "recall": 1.0, "false_merge_rate": false_merge,
            "true_positive": 1, "false_positive": 0, "false_negative": 0,
        },
        "split": {
            "precision": 1.0, "recall": 1.0, "false_merge_rate": false_merge,
            "false_split_rate": false_split, "true_positive": 3,
            "false_positive": 0, "false_negative": 0,
        },
        "claim_evidence": {
            "cross_check_accuracy": 1.0, "single_source_state_accuracy": 1.0,
            "single_source_false_cross_check_rate": single_source_false,
            "proposition_extraction_accuracy": 1.0, "multi_source_coverage": 1.0,
        },
        "decision": {"unsafe_now_rate": unsafe_now, "human_review_recall": 1.0, "cases": []},
    }


class _TmpQuality(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (
            quality_registry.QUALITY_DIR,
            quality_registry.INDEX_PATH,
            quality_registry.LATEST_PATH,
        )
        quality_registry.QUALITY_DIR = self.tmp
        quality_registry.INDEX_PATH = os.path.join(self.tmp, "index.json")
        quality_registry.LATEST_PATH = os.path.join(self.tmp, "latest.json")

    def tearDown(self):
        (
            quality_registry.QUALITY_DIR,
            quality_registry.INDEX_PATH,
            quality_registry.LATEST_PATH,
        ) = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestRecord(_TmpQuality):
    def test_record_writes_files(self):
        commit = quality_registry.record(_results(), "aaaaaaaaaaaa", "2026-10-06T00:00:00+00:00")
        self.assertEqual(commit, "aaaaaaaaaaaa")
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "aaaaaaaaaaaa.json")))
        self.assertTrue(os.path.exists(quality_registry.LATEST_PATH))
        self.assertTrue(os.path.exists(quality_registry.INDEX_PATH))
        with open(os.path.join(self.tmp, "aaaaaaaaaaaa.json"), encoding="utf-8") as f:
            doc = __import__("json").load(f)
        self.assertEqual(doc["commit"], "aaaaaaaaaaaa")
        self.assertEqual(doc["metrics"]["macro_quality"], 1.0)
        self.assertEqual(doc["metrics"]["event.false_merge_rate"], 0.0)
        self.assertEqual(doc["metrics"]["safety_pass"], True)

    def test_record_idempotent_index(self):
        for when in ("2026-10-06T00:00:00+00:00", "2026-10-06T01:00:00+00:00"):
            quality_registry.record(_results(), "bbbbbbbbbbbb", when)
        idx = quality_registry.list_records()
        self.assertEqual(len(idx), 1)
        self.assertEqual(idx[0]["commit"], "bbbbbbbbbbbb")

    def test_list_records_sorted_and_latest(self):
        quality_registry.record(_results(), "cccccccccccc", "2026-10-06T00:00:00+00:00")
        quality_registry.record(_results(), "dddddddddddd", "2026-10-06T02:00:00+00:00")
        idx = quality_registry.list_records()
        self.assertEqual([r["commit"] for r in idx], ["cccccccccccc", "dddddddddddd"])
        self.assertEqual(quality_registry.latest()["commit"], "dddddddddddd")
        self.assertIsNotNone(quality_registry.load("cccccccccccc"))
        self.assertIsNone(quality_registry.load("zzzzzzzzzzzz"))


class TestCompare(_TmpQuality):
    def test_compare_no_regression(self):
        quality_registry.record(_results(), "111111111111", "2026-10-06T00:00:00+00:00")
        quality_registry.record(_results(), "222222222222", "2026-10-06T01:00:00+00:00")
        out = quality_registry.compare("111111111111", "222222222222")
        self.assertFalse(out.get("regression"))
        self.assertEqual(out["deltas"]["macro_quality"]["delta"], 0.0)
        self.assertEqual(out["deltas"]["macro_quality"]["worse"], False)

    def test_compare_detects_regression(self):
        quality_registry.record(_results(), "111111111111", "2026-10-06T00:00:00+00:00")
        worse = _results(macro=0.90, safety=False, false_merge=0.05,
                         false_split=0.02, single_source_false=1.0, unsafe_now=0.5)
        quality_registry.record(worse, "333333333333", "2026-10-06T01:00:00+00:00")
        out = quality_registry.compare("111111111111", "333333333333")
        self.assertTrue(out.get("regression"))
        # 越低越好的指标：上升即为劣化
        self.assertTrue(out["deltas"]["event.false_merge_rate"]["worse"])
        self.assertTrue(out["deltas"]["split.false_split_rate"]["worse"])
        self.assertTrue(out["deltas"]["claim_evidence.single_source_false_cross_check_rate"]["worse"])
        self.assertTrue(out["deltas"]["decision.unsafe_now_rate"]["worse"])
        # 越高越好的指标：下降即为劣化
        self.assertTrue(out["deltas"]["macro_quality"]["worse"])

    def test_compare_missing_record(self):
        out = quality_registry.compare("nope11111111", "nope22222222")
        self.assertEqual(out.get("error"), "missing_record")

    def test_lower_is_better_metric_set(self):
        self.assertIn("event.false_merge_rate", quality_registry._LOWER_IS_BETTER)
        self.assertIn("split.false_split_rate", quality_registry._LOWER_IS_BETTER)


if __name__ == "__main__":
    unittest.main()
