"""P1-8 Observability Dashboard：指标收敛与健康分级回归。

测试用注入的假数据源（替换 _read_json），不依赖真实产物，结果完全确定。

覆盖：
  - 全绿 → healthy / score=1.0 / 无告警
  - 质量域劣化（macro 低 / safety Fail / false_merge / false_split）→ critical
  - 流水线域节点失败 → critical；慢节点 → warning
  - 源缺失 → 对应 section unavailable + warning（不因观测自身失败而崩）
  - 信源低可用 / 陈旧、复核积压 → warning（degraded）
  - overall.score 有下限 0，不出现负值
  - main() 写文件；--fail-on-critical 在存在 critical 时返回 1
"""
import json
import os
import shutil
import tempfile
import unittest

import observability


def _green_sources():
    return {
        "quality/latest.json": {
            "commit": "c1", "when": "2026-10-06T00:00:00+00:00",
            "metrics": {
                "macro_quality": 1.0, "safety_pass": True,
                "event.false_merge_rate": 0.0, "split.false_split_rate": 0.0,
                "claim_evidence.single_source_false_cross_check_rate": 0.0,
            },
        },
        "quality/index.json": [{"commit": "c1"}],
        "dag_run.json": {
            "ok": True, "run_at": "2026-10-06T00:00:00+00:00",
            "nodes": [{"id": "a", "status": "ok", "duration_sec": 1.0},
                      {"id": "b", "status": "ok", "duration_sec": 2.0}],
        },
        "run.json": {"run_id": "r1", "status": "passed", "build_sha": "abc",
                     "engine_version": "4.2", "failed_stage": None},
        "data.json": {"source_health": {
            "src_a": {"availability": 1.0, "freshness": 1.0},
            "src_b": {"availability": 0.9, "freshness": 0.8},
        }},
        "module_health.json": {"modules": [
            {"module": "event", "error_rate": 0.0, "health": "healthy"},
            {"module": "claim", "error_rate": 0.0, "health": "healthy"},
        ]},
        "review_queue.json": {"generated_count": 2, "items": [
            {"event_id": "e1", "status": "pending"},
            {"event_id": "e2", "status": "approved"},
        ]},
        "review_state.json": {"items": {"e1": {"status": "pending"},
                                        "e2": {"status": "approved"}}},
        # 全绿系统应同时具备 CE 池及其下游联动（否则 ce_linkage 段会如实告警）
        "canonical_events.json": {
            "canonical_events": {"cev1": {}, "cev2": {}},
            "by_event_id": {"e1": "cev1", "e2": "cev2"},
        },
        "decisions_pending.json": {
            "funnel": {"now": [{"canonical_event_id": "cev1"}],
                       "soon": [], "watch": []},
        },
        "p2_alerts.json": {"semantic_alerts": [{"ceid": "cev1"}]},
    }


class _FakeSources(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sources = _green_sources()
        self._orig_read = observability._read_json
        self._orig_commit = observability._commit_sha
        self._orig_out = observability.OUTPUT_PATH
        observability._read_json = lambda name: self.sources.get(name)
        observability._commit_sha = lambda: "testcommit123"
        observability.OUTPUT_PATH = os.path.join(self.tmp, "observability.json")

    def tearDown(self):
        observability._read_json = self._orig_read
        observability._commit_sha = self._orig_commit
        observability.OUTPUT_PATH = self._orig_out
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _codes(self, doc, severity=None):
        return [a["code"] for a in doc["alerts"]
                if severity is None or a["severity"] == severity]


class TestHealthy(_FakeSources):
    def test_all_green_is_healthy(self):
        doc = observability.build()
        self.assertEqual(doc["overall"]["status"], "healthy")
        self.assertEqual(doc["overall"]["score"], 1.0)
        self.assertEqual(doc["alerts"], [])
        self.assertEqual(doc["commit"], "testcommit123")
        # 六个域都在
        for k in ("quality", "pipeline", "run", "sources", "modules", "review"):
            self.assertIn(k, doc["sections"])

    def test_sections_carry_expected_fields(self):
        doc = observability.build()
        self.assertEqual(doc["sections"]["pipeline"]["node_count"], 2)
        self.assertEqual(doc["sections"]["sources"]["source_count"], 2)
        self.assertEqual(doc["sections"]["modules"]["module_count"], 2)
        self.assertEqual(doc["sections"]["review"]["pending"], 1)
        self.assertEqual(doc["sections"]["quality"]["macro_quality"], 1.0)


class TestCritical(_FakeSources):
    def test_low_macro_and_safety_fail(self):
        self.sources["quality/latest.json"]["metrics"].update(
            {"macro_quality": 0.90, "safety_pass": False})
        doc = observability.build()
        self.assertEqual(doc["overall"]["status"], "critical")
        codes = self._codes(doc, "critical")
        self.assertIn("QUALITY_MACRO_LOW", codes)
        self.assertIn("QUALITY_SAFETY_FAIL", codes)

    def test_false_merge_and_split_are_critical(self):
        self.sources["quality/latest.json"]["metrics"].update(
            {"event.false_merge_rate": 0.05, "split.false_split_rate": 0.02})
        doc = observability.build()
        codes = self._codes(doc, "critical")
        self.assertIn("QUALITY_FALSE_MERGE", codes)
        self.assertIn("QUALITY_FALSE_SPLIT", codes)

    def test_pipeline_node_failed(self):
        self.sources["dag_run.json"] = {
            "ok": False,
            "nodes": [{"id": "a", "status": "ok", "duration_sec": 1.0},
                      {"id": "b", "status": "failed", "exit_code": 3, "duration_sec": 1.0}],
        }
        doc = observability.build()
        self.assertEqual(doc["overall"]["status"], "critical")
        self.assertIn("PIPELINE_NODE_FAILED", self._codes(doc, "critical"))
        self.assertEqual(doc["sections"]["pipeline"]["failed_nodes"], ["b"])

    def test_run_failed(self):
        self.sources["run.json"]["status"] = "failed"
        self.sources["run.json"]["failed_stage"] = "analyze"
        doc = observability.build()
        self.assertIn("RUN_FAILED", self._codes(doc, "critical"))

    def test_score_has_floor(self):
        # 制造大量 critical，score 不得为负
        m = self.sources["quality/latest.json"]["metrics"]
        m.update({"macro_quality": 0.1, "safety_pass": False,
                  "event.false_merge_rate": 0.9, "split.false_split_rate": 0.9,
                  "claim_evidence.single_source_false_cross_check_rate": 1.0})
        self.sources["dag_run.json"]["nodes"].append(
            {"id": "c", "status": "failed", "duration_sec": 1.0})
        self.sources["run.json"]["status"] = "failed"
        doc = observability.build()
        self.assertGreaterEqual(doc["overall"]["score"], 0.0)
        self.assertEqual(doc["overall"]["status"], "critical")


class TestWarnings(_FakeSources):
    def test_missing_quality_is_warning_not_critical(self):
        del self.sources["quality/latest.json"]
        doc = observability.build()
        self.assertEqual(doc["sections"]["quality"]["status"], "unavailable")
        self.assertIn("QUALITY_UNAVAILABLE", self._codes(doc, "warning"))
        self.assertEqual(doc["overall"]["status"], "degraded")

    def test_missing_pipeline_is_warning(self):
        del self.sources["dag_run.json"]
        doc = observability.build()
        self.assertEqual(doc["sections"]["pipeline"]["status"], "unavailable")
        self.assertIn("PIPELINE_UNAVAILABLE", self._codes(doc, "warning"))

    def test_corrupt_file_treated_as_missing(self):
        self.sources["run.json"] = None
        doc = observability.build()
        self.assertEqual(doc["sections"]["run"]["status"], "unavailable")

    def test_low_availability_and_stale_sources(self):
        self.sources["data.json"] = {"source_health": {
            "bad": {"availability": 0.1, "freshness": 0.05},
        }}
        doc = observability.build()
        codes = self._codes(doc, "warning")
        self.assertIn("SOURCE_LOW_AVAILABILITY", codes)
        self.assertIn("SOURCE_STALE", codes)
        self.assertEqual(doc["sections"]["sources"]["status"], "degraded")

    def test_slow_node_warning(self):
        self.sources["dag_run.json"]["nodes"].append(
            {"id": "slow", "status": "ok", "duration_sec": 999.0})
        doc = observability.build()
        self.assertIn("PIPELINE_SLOW_NODE", self._codes(doc, "warning"))

    def test_high_module_error_rate(self):
        self.sources["module_health.json"]["modules"].append(
            {"module": "decision", "error_rate": 0.5, "health": "degraded"})
        doc = observability.build()
        self.assertIn("MODULE_ERROR_RATE", self._codes(doc, "warning"))

    def test_review_backlog(self):
        self.sources["review_queue.json"]["items"] = [
            {"event_id": f"e{i}", "status": "pending"} for i in range(60)
        ]
        doc = observability.build()
        self.assertIn("REVIEW_BACKLOG", self._codes(doc, "warning"))
        self.assertEqual(doc["sections"]["review"]["pending"], 60)


class TestMain(_FakeSources):
    def test_main_writes_output(self):
        rc = observability.main([])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(observability.OUTPUT_PATH))
        with open(observability.OUTPUT_PATH, encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(doc["overall"]["status"], "healthy")

    def test_fail_on_critical_exit_code(self):
        self.sources["quality/latest.json"]["metrics"]["safety_pass"] = False
        self.assertEqual(observability.main(["--fail-on-critical"]), 1)

    def test_json_to_stdout_does_not_write(self):
        rc = observability.main(["--json"])
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(observability.OUTPUT_PATH))


if __name__ == "__main__":
    unittest.main()
