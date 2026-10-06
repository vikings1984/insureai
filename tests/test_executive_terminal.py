#!/usr/bin/env python3
"""Executive Terminal 管理层视图契约测试。

P1-10：executive_terminal 必须把三条运维事实接入管理层视图：
  - P1-8 Observability  → 系统健康（status/score/critical/warning/告警）
  - P1-7 DAG            → 流水线执行（通过率/失败节点/最慢节点）
  - P1-4 复核状态机     → 复核进展（状态分布）

两条硬约束（与 observability.py 一致的容错原则）：
  - artifact 缺失或损坏时降级为 available=false，**绝不抛异常**；
  - 只汇总 artifact 已有事实，不补写未验证结论。
"""
import contextlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import executive_terminal
import executive_terminal as et

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "executive_terminal.html"

OBSERVABILITY = {
    "version": "1.0",
    "commit": "abc1234",
    "generated_at": "2026-10-06T16:10:54+00:00",
    "overall": {
        "status": "degraded", "score": 0.6,
        "critical_count": 1, "warning_count": 4,
        "reasons": ["16 个信源可用性低于 0.5", "待复核积压 100 条"],
    },
    "alerts": [
        {"code": "SOURCE_AVAILABILITY", "message": "信源可用性偏低", "severity": "warning"},
        {"code": "REVIEW_BACKLOG", "message": "复核积压", "severity": "critical"},
    ],
    "sections": {"quality": {"status": "ok"}},
}

DAG_RUN = {
    "version": "1.0",
    "run_at": "2026-10-06T16:00:00+00:00",
    "dry_run": False,
    "count": 4,
    "ok": False,
    "nodes": [
        {"id": "intelligence", "name": "情报构建", "status": "ok", "exit_code": 0, "duration_sec": 12.5},
        {"id": "claims_build", "name": "主张构建", "status": "ok", "exit_code": 0, "duration_sec": 91.2},
        {"id": "decision_build", "name": "决策构建", "status": "failed", "exit_code": 3, "duration_sec": 4.0},
        {"id": "quality_gate", "name": "质量门禁", "status": "ok", "exit_code": 0, "duration_sec": 0.0},
    ],
}

REVIEW_STATE = {
    "version": 1,
    "items": {
        "e1": {"status": "pending"},
        "e2": {"status": "pending"},
        "e3": {"status": "in_review"},
        "e4": {"status": "approved"},
        "e5": {"status": "approved"},
        "e6": {"status": "resolved"},
        "e7": {"status": "ghost_status"},
    },
}


def build_with(**artifacts) -> dict:
    """在临时目录里用合成 artifact 跑一遍 main()，返回产物。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for key, payload in artifacts.items():
            # observability_json=… → 写入 observability.json
            name = f"{key[:-5]}.json" if key.endswith("_json") else key
            (root / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        old_root, old_output = et.ROOT, et.OUTPUT
        try:
            et.ROOT = root
            et.OUTPUT = root / "executive_terminal.json"
            with open(os.devnull, "w", encoding="utf-8") as devnull:
                with contextlib.redirect_stdout(devnull):
                    et.main()
            return json.loads(et.OUTPUT.read_text(encoding="utf-8"))
        finally:
            et.ROOT, et.OUTPUT = old_root, old_output


def _nested_keys(value) -> set:
    keys, stack = set(), [value]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            keys |= {str(k) for k in cur}
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return keys


class ExecutiveTerminalTests(unittest.TestCase):
    def test_builds_from_existing_artifacts_without_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "intelligence.json").write_text(json.dumps({
                "events": [
                    {"event_id": "e1", "topic": "AI保险", "importance": 90, "evidence_coverage": 100, "trust": 82, "review_required": False, "insight": "关注"}
                ],
                "radar": {"topic_trends": [{"topic": "AI保险", "direction": "rising", "signal_strength": 88}]},
            }), encoding="utf-8")
            (root / "claims.json").write_text(json.dumps({"cross_checked_claim_count": 2, "single_source_claim_count": 1}), encoding="utf-8")
            (root / "review_queue.json").write_text(json.dumps({"items": [{"title": "监管事项", "reason": "需要人工判断"}]}), encoding="utf-8")
            (root / "daily_risk_radar.json").write_text(json.dumps({"items": [{"title": "数据新鲜度", "reason": "需关注"}]}), encoding="utf-8")
            (root / "decision_credibility.json").write_text(json.dumps({"status": "review"}), encoding="utf-8")
            (root / "deployment_verification.json").write_text(json.dumps({"status": "verified", "verified": True, "release_marker": "insureai-x", "marker_found": True}), encoding="utf-8")
            old_root, old_output = executive_terminal.ROOT, executive_terminal.OUTPUT
            executive_terminal.ROOT = root
            executive_terminal.OUTPUT = root / "executive_terminal.json"
            try:
                with patch.dict(os.environ, {"GITHUB_SHA": "abc123"}, clear=False):
                    executive_terminal.main()
                output = json.loads((root / "executive_terminal.json").read_text(encoding="utf-8"))
            finally:
                executive_terminal.ROOT, executive_terminal.OUTPUT = old_root, old_output
        self.assertEqual(output["source_commit"], "abc123")
        self.assertEqual(output["summary"]["event_count"], 1)
        self.assertEqual(output["summary"]["cross_checked_claims"], 2)
        self.assertEqual(output["summary"]["deployment_status"], "verified")
        self.assertEqual(len(output["what_is_accelerating"]), 1)

    def test_does_not_require_release_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "intelligence.json").write_text(json.dumps({"events": [], "radar": {"topic_trends": []}}), encoding="utf-8")
            old_root, old_output = executive_terminal.ROOT, executive_terminal.OUTPUT
            executive_terminal.ROOT = root
            executive_terminal.OUTPUT = root / "executive_terminal.json"
            try:
                with patch.dict(os.environ, {"GITHUB_SHA": "def456"}, clear=False):
                    executive_terminal.main()
                output = json.loads((root / "executive_terminal.json").read_text(encoding="utf-8"))
            finally:
                executive_terminal.ROOT, executive_terminal.OUTPUT = old_root, old_output
        self.assertEqual(output["source_commit"], "def456")
        self.assertEqual(output["summary"]["deployment_status"], "unknown")


class VersionAndShapeTests(unittest.TestCase):
    def test_version_bumped_to_4(self):
        self.assertEqual(build_with()["version"], 4)

    def test_three_new_sections_present(self):
        out = build_with()
        for key in ("system_health", "pipeline", "review_progress"):
            with self.subTest(section=key):
                self.assertIn(key, out)

    def test_new_artifacts_listed_in_sources(self):
        sources = build_with()["artifact_sources"]
        for name in ("observability.json", "dag_run.json", "review_state.json"):
            self.assertIn(name, sources)


class SystemHealthTests(unittest.TestCase):
    def test_maps_observability_overall(self):
        h = build_with(observability_json=OBSERVABILITY)["system_health"]
        self.assertTrue(h["available"])
        self.assertEqual(h["status"], "degraded")
        self.assertEqual(h["status_label"], "降级")
        self.assertEqual(h["score"], 0.6)
        self.assertEqual(h["critical_count"], 1)
        self.assertEqual(h["warning_count"], 4)
        self.assertEqual(h["reasons"], OBSERVABILITY["overall"]["reasons"])
        self.assertEqual(h["generated_at"], OBSERVABILITY["generated_at"])

    def test_alerts_mapped_with_severity_labels(self):
        h = build_with(observability_json=OBSERVABILITY)["system_health"]
        self.assertEqual(len(h["alerts"]), 2)
        self.assertEqual(h["alerts"][0]["severity_label"], "警告")
        self.assertEqual(h["alerts"][1]["severity_label"], "严重")
        self.assertEqual(h["alerts"][1]["code"], "REVIEW_BACKLOG")

    def test_unavailable_when_missing(self):
        h = build_with()["system_health"]
        self.assertFalse(h["available"])
        self.assertEqual(h["status"], "unavailable")
        self.assertEqual(h["status_label"], "无数据")
        self.assertEqual(h["alerts"], [])

    def test_corrupted_observability_degrades(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "observability.json").write_text("{ not json", encoding="utf-8")
            old_root, old_output = et.ROOT, et.OUTPUT
            try:
                et.ROOT = root
                et.OUTPUT = root / "executive_terminal.json"
                et.main()
                out = json.loads(et.OUTPUT.read_text(encoding="utf-8"))
            finally:
                et.ROOT, et.OUTPUT = old_root, old_output
        self.assertFalse(out["system_health"]["available"])

    def test_health_labels_cover_every_status(self):
        for status in ("healthy", "degraded", "critical", "unavailable"):
            with self.subTest(status=status):
                self.assertIn(status, et.HEALTH_LABELS)


class PipelineTests(unittest.TestCase):
    def test_maps_dag_run_nodes(self):
        p = build_with(dag_run_json=DAG_RUN)["pipeline"]
        self.assertTrue(p["available"])
        self.assertFalse(p["ok"])
        self.assertEqual(p["node_count"], 4)
        self.assertEqual(p["ok_count"], 3)
        self.assertEqual(p["failed_count"], 1)
        self.assertEqual(p["failed_nodes"], [
            {"id": "decision_build", "name": "决策构建", "exit_code": 3}
        ])

    def test_slowest_nodes_ranked_and_non_zero_only(self):
        p = build_with(dag_run_json=DAG_RUN)["pipeline"]
        ids = [n["id"] for n in p["slowest_nodes"]]
        self.assertEqual(ids[0], "claims_build")
        self.assertNotIn("quality_gate", ids)  # duration 0 不进榜

    def test_unavailable_when_missing(self):
        p = build_with()["pipeline"]
        self.assertFalse(p["available"])
        self.assertIsNone(p["ok"])
        self.assertEqual(p["node_count"], 0)

    def test_ignores_malformed_nodes(self):
        payload = dict(DAG_RUN, nodes=[{"id": "x"}, "junk", None])
        p = build_with(dag_run_json=payload)["pipeline"]
        self.assertEqual(p["node_count"], 1)
        self.assertEqual(p["ok_count"], 0)


class ReviewProgressTests(unittest.TestCase):
    def test_distribution_counts_and_order(self):
        rp = build_with(review_state_json=REVIEW_STATE)["review_progress"]
        self.assertTrue(rp["available"])
        self.assertEqual(rp["tracked"], 7)
        statuses = [row["status"] for row in rp["distribution"]]
        self.assertEqual(statuses, ["pending", "in_review", "approved", "resolved", "unknown"])
        counts = {row["status"]: row["count"] for row in rp["distribution"]}
        self.assertEqual(counts["pending"], 2)
        self.assertEqual(counts["approved"], 2)
        self.assertEqual(counts["unknown"], 1)

    def test_zero_count_statuses_omitted(self):
        rp = build_with(review_state_json=REVIEW_STATE)["review_progress"]
        for row in rp["distribution"]:
            self.assertGreater(row["count"], 0)

    def test_labels_are_chinese(self):
        rp = build_with(review_state_json=REVIEW_STATE)["review_progress"]
        labels = {row["status"]: row["label"] for row in rp["distribution"]}
        self.assertEqual(labels["pending"], "待复核")
        self.assertEqual(labels["resolved"], "已归档")

    def test_unavailable_when_missing(self):
        rp = build_with()["review_progress"]
        self.assertFalse(rp["available"])
        self.assertEqual(rp["tracked"], 0)
        self.assertEqual(rp["distribution"], [])

    def test_status_labels_cover_every_state(self):
        for status in et.REVIEW_STATUSES:
            with self.subTest(status=status):
                self.assertIn(status, et.STATUS_LABELS)

    def test_queue_size_reflects_review_queue_artifact(self):
        queue = {"items": [{"event_id": f"e{i}"} for i in range(5)]}
        rp = build_with(review_queue_json=queue)["review_progress"]
        self.assertEqual(rp["queue_size"], 5)


class SummaryTests(unittest.TestCase):
    def test_summary_carries_system_and_pipeline_status(self):
        out = build_with(observability_json=OBSERVABILITY, dag_run_json=DAG_RUN)
        self.assertEqual(out["summary"]["system_status"], "降级")
        self.assertEqual(out["summary"]["pipeline_status"], "有失败节点")

    def test_pipeline_status_unrun_when_missing(self):
        out = build_with(observability_json=OBSERVABILITY)
        self.assertEqual(out["summary"]["pipeline_status"], "未运行")

    def test_pipeline_status_normal_when_all_ok(self):
        payload = dict(DAG_RUN, ok=True, nodes=[n for n in DAG_RUN["nodes"] if n["status"] == "ok"])
        out = build_with(dag_run_json=payload)
        self.assertEqual(out["summary"]["pipeline_status"], "正常")


class GracefulDegradationTests(unittest.TestCase):
    def test_all_new_artifacts_missing_does_not_raise(self):
        out = build_with()
        self.assertFalse(out["system_health"]["available"])
        self.assertFalse(out["pipeline"]["available"])
        self.assertFalse(out["review_progress"]["available"])

    def test_original_sections_still_built_when_new_missing(self):
        out = build_with()
        for key in ("what_changed", "what_is_accelerating", "what_needs_attention",
                    "what_needs_human_decision", "release"):
            self.assertIn(key, out)


class HtmlContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PAGE.read_text(encoding="utf-8")
        cls.body = cls.text[cls.text.index("<script>"):]

    def test_new_sections_present(self):
        for dom_id in ("statusbar", "health", "pipeline", "reviewstate", "alerts"):
            with self.subTest(id=dom_id):
                self.assertIn(f'id="{dom_id}"', self.text)

    def test_html_reads_new_sections(self):
        for expr in ("d.system_health", "d.pipeline", "d.review_progress"):
            self.assertIn(expr, self.body)

    def test_html_escapes_artifact_text(self):
        """来自 artifact 的文本必须经 esc() 渲染后再插入 innerHTML。"""
        for expr in ("esc(h.status_label)", "esc(r)", "esc(n.name", "esc(x.label)",
                     "esc(a.message", "esc(p.run_at"):
            with self.subTest(expr=expr):
                self.assertIn(expr, self.body)

    def test_html_grounded_in_built_artifact(self):
        """P1-10 新增片段读取的字段必须都能在真实产物里找到，不引用不存在的键。"""
        out = build_with(observability_json=OBSERVABILITY, dag_run_json=DAG_RUN,
                         review_state_json=REVIEW_STATE)
        allowed = set()
        for section in ("system_health", "pipeline", "review_progress"):
            allowed |= _nested_keys(out[section])
        allowed |= {"pipeline_status", "review_queue"}  # summary 字段
        start = self.body.index("const h=d.system_health")
        end = self.body.index("const dep=d.release")
        segment = self.body[start:end]
        accessed = set()
        for prefix in ("h.", "p.", "rp.", "a.", "n.", "x."):
            accessed |= set(re.findall(rf"\b{re.escape(prefix)}([a-z_][a-z0-9_]*)", segment))
        unexpected = accessed - allowed
        self.assertFalse(unexpected, f"HTML 读取了产物中不存在的字段: {sorted(unexpected)}")


if __name__ == "__main__":
    unittest.main()
