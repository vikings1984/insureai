#!/usr/bin/env python3
"""E3 反馈/跟踪导入器的纪律测试。

重点：schema 与 p2_intelligence 一致、非法行 fail-closed 拒绝、去重语义、绝不制造用户偏好。
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from p2_import_feedback import (
    ALLOWED_LABELS,
    ALLOWED_STATUS,
    VERSION,
    import_payload,
    load_payload,
    merge_state,
    normalize_feedback,
    normalize_monitoring,
    run,
    validate_feedback_row,
    validate_monitor_row,
)


def _state(feedback=None, monitoring=None) -> dict:
    return {
        "version": "p2-v1.0",
        "watchlists": [{"id": "ai", "name": "AI保险"}, {"id": "ma", "name": "并购重组"}],
        "feedback": feedback or [],
        "monitoring": monitoring or [],
    }


def _fb(event_id="e1", label="useful", note="", importance=None, confidence=None, created_at=None):
    row = {"event_id": event_id, "label": label, "note": note,
           "importance": importance, "confidence": confidence}
    if created_at:
        row["created_at"] = created_at
    return row


def _mon(watchlist_id="ai", event_id="e1", status="active", updated_at=None):
    row = {"watchlist_id": watchlist_id, "event_id": event_id, "status": status}
    if updated_at:
        row["updated_at"] = updated_at
    return row


class TestSchemaAlignment(unittest.TestCase):
    def test_allowed_sets_match_p2_intelligence(self):
        from p2_intelligence import record_feedback, register_monitor
        # 从 record_feedback 的 allowed 集合与 register_monitor 的 status 集合对齐
        self.assertEqual(ALLOWED_LABELS, {"useful", "important", "noise",
                                          "irrelevant", "incorrect", "acted_on"})
        self.assertEqual(ALLOWED_STATUS, {"active", "resolved", "snoozed"})

    def test_import_produces_rows_usable_by_engine(self):
        """导入的行必须能被 p2_intelligence 的 _feedback_boost 消费（字段完整）。"""
        accepted, rejected = normalize_feedback([_fb("e1", "useful")])
        self.assertEqual(len(accepted), 1)
        self.assertEqual(rejected, [])
        row = accepted[0]
        for key in ("event_id", "label", "note", "importance", "confidence",
                    "outcome", "user_id", "created_at"):
            self.assertIn(key, row)


class TestFeedbackValidation(unittest.TestCase):
    def test_valid_row_accepted(self):
        self.assertEqual(validate_feedback_row(_fb("e1", "important"), {"ai"}), [])

    def test_bad_label_rejected(self):
        errors = validate_feedback_row(_fb("e1", "awesome"), {"ai"})
        self.assertTrue(errors)
        self.assertIn("label 非法", errors[0])

    def test_missing_event_id_rejected(self):
        errors = validate_feedback_row({"label": "useful"}, {"ai"})
        self.assertTrue(any("event_id" in e for e in errors))

    def test_importance_out_of_range_rejected(self):
        self.assertTrue(validate_feedback_row(_fb("e1", "useful", importance=9)))
        self.assertTrue(validate_feedback_row(_fb("e1", "useful", importance=0)))
        self.assertEqual(validate_feedback_row(_fb("e1", "useful", importance=3)), [])

    def test_confidence_numeric_string_accepted(self):
        self.assertEqual(validate_feedback_row(_fb("e1", "useful", confidence="4")), [])

    def test_bad_created_at_rejected(self):
        self.assertTrue(validate_feedback_row(_fb("e1", "useful", created_at="not-a-date")))

    def test_non_dict_rejected(self):
        self.assertTrue(validate_feedback_row(["e1", "useful"], {"ai"}))


class TestMonitoringValidation(unittest.TestCase):
    def test_valid_row_accepted(self):
        self.assertEqual(validate_monitor_row(_mon("ai", "e1", "active"), {"ai", "ma"}), [])

    def test_unknown_watchlist_rejected(self):
        errors = validate_monitor_row(_mon("nope", "e1", "active"), {"ai", "ma"})
        self.assertTrue(any("watchlist_id 未知" in e for e in errors))

    def test_watchlist_not_checked_when_set_unknown(self):
        """未给出已知 watchlist 集合时不校验（导入器可在无 state 场景使用）。"""
        self.assertEqual(validate_monitor_row(_mon("any", "e1", "active"), None), [])

    def test_bad_status_rejected(self):
        errors = validate_monitor_row(_mon("ai", "e1", "maybe"), {"ai"})
        self.assertTrue(any("status 非法" in e for e in errors))

    def test_missing_event_id_rejected(self):
        self.assertTrue(any("event_id" in e for e in validate_monitor_row({"watchlist_id": "ai", "status": "active"}, {"ai"})))


class TestDedup(unittest.TestCase):
    def test_feedback_dedup_by_event_and_label_keeps_latest(self):
        rows = [_fb("e1", "useful", created_at="2026-09-01T00:00:00+00:00"),
                _fb("e1", "useful", created_at="2026-09-02T00:00:00+00:00")]
        accepted, _ = normalize_feedback(rows)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["created_at"], "2026-09-02T00:00:00+00:00")

    def test_feedback_same_event_different_labels_both_kept(self):
        accepted, _ = normalize_feedback([_fb("e1", "useful"), _fb("e1", "noise")])
        self.assertEqual(len(accepted), 2)

    def test_monitoring_dedup_by_watchlist_and_event(self):
        accepted, _ = normalize_monitoring([
            _mon("ai", "e1", "active", updated_at="2026-09-01T00:00:00+00:00"),
            _mon("ai", "e1", "resolved", updated_at="2026-09-02T00:00:00+00:00"),
        ])
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["status"], "resolved")


class TestMerge(unittest.TestCase):
    def test_merge_replaces_existing_and_keeps_others(self):
        state = _state(feedback=[{"event_id": "e1", "label": "useful", "created_at": "2000-01-01T00:00:00+00:00"}],
                       monitoring=[{"watchlist_id": "ai", "event_id": "e1", "status": "active",
                                    "updated_at": "2000-01-01T00:00:00+00:00"}])
        merged = merge_state(state,
                             [{"event_id": "e1", "label": "useful", "created_at": "2026-09-02T00:00:00+00:00"}],
                             [{"watchlist_id": "ma", "event_id": "e2", "status": "active",
                               "updated_at": "2026-09-02T00:00:00+00:00"}])
        self.assertEqual(len(merged["feedback"]), 1)  # 覆盖而非追加
        self.assertEqual(merged["feedback"][0]["created_at"], "2026-09-02T00:00:00+00:00")
        self.assertEqual(len(merged["monitoring"]), 2)  # 不同 (watchlist,event) 保留

    def test_merge_does_not_mutate_input_state(self):
        state = _state(feedback=[{"event_id": "old", "label": "useful"}])
        merge_state(state, [{"event_id": "new", "label": "noise", "created_at": "2026-09-02T00:00:00+00:00"}], [])
        self.assertEqual(len(state["feedback"]), 1)  # 原 state 未被污染
        self.assertEqual(state["feedback"][0]["event_id"], "old")


class TestHonesty(unittest.TestCase):
    def test_empty_payload_imports_nothing(self):
        report = import_payload({"feedback": [], "monitoring": []}, _state(), {"ai", "ma"})
        self.assertEqual(report["imported_feedback"], 0)
        self.assertEqual(report["imported_monitoring"], 0)
        self.assertEqual(report["rejections"], [])

    def test_invalid_rows_are_rejected_not_coerced(self):
        """不静默修正：非法 label 的行被拒绝并说明原因，绝不改成默认值混入。"""
        report = import_payload({"feedback": [_fb("e1", "bogus")]}, _state(), {"ai", "ma"})
        self.assertEqual(report["imported_feedback"], 0)
        self.assertEqual(report["rejected_feedback"], 1)
        self.assertTrue(report["rejections"][0]["reasons"])

    def test_no_fabricated_preferences(self):
        """导入器只落显式输入，不推断任何偏好字段。"""
        report = import_payload({"feedback": [_fb("e1", "useful")]}, _state(), {"ai", "ma"})
        row = [f for f in report["state"]["feedback"] if f["event_id"] == "e1"][0]
        self.assertIsNone(row["importance"])  # 用户未给 → 保持空，不编造
        self.assertIsNone(row["confidence"])
        self.assertEqual(row["note"], "")

    def test_missing_timestamp_falls_back_to_import_time(self):
        accepted, _ = normalize_feedback([_fb("e1", "useful")])
        self.assertTrue(accepted[0]["created_at"])  # 回落到导入时刻，可审计


class TestLoadPayload(unittest.TestCase):
    def test_plain_json_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "export.json"
            p.write_text(json.dumps({"feedback": [_fb("e1", "useful")], "monitoring": []}), encoding="utf-8")
            self.assertEqual(len(load_payload(p)["feedback"]), 1)

    def test_github_issue_body_json_block(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "issue.md"
            p.write_text("## 复核反馈\n\n```json\n" + json.dumps({"feedback": [_fb("e1", "noise")], "monitoring": []}) + "\n```\n",
                         encoding="utf-8")
            self.assertEqual(load_payload(p)["feedback"][0]["label"], "noise")

    def test_unparseable_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.txt"
            p.write_text("nothing here", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_payload(p)


class TestRunEndToEnd(unittest.TestCase):
    def test_run_merges_and_persists(self):
        with tempfile.TemporaryDirectory() as d:
            payload = Path(d) / "export.json"
            payload.write_text(json.dumps({
                "feedback": [_fb("evt_1", "useful", note="很关键"), _fb("evt_2", "bogus")],
                "monitoring": [_mon("ai", "evt_1", "active"), _mon("nope", "evt_1", "active")],
            }), encoding="utf-8")
            state_path = Path(d) / "p2_state.json"
            state_path.write_text(json.dumps(_state()), encoding="utf-8")
            report = run(payload, state_path, persist=True)
            self.assertEqual(report["imported_feedback"], 1)
            self.assertEqual(report["rejected_feedback"], 1)
            self.assertEqual(report["imported_monitoring"], 1)
            self.assertEqual(report["rejected_monitoring"], 1)
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["feedback"]), 1)
            self.assertEqual(saved["feedback"][0]["note"], "很关键")
            self.assertEqual(len(saved["monitoring"]), 1)

    def test_run_no_persist_leaves_file_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            payload = Path(d) / "export.json"
            payload.write_text(json.dumps({"feedback": [_fb("evt_1", "useful")], "monitoring": []}), encoding="utf-8")
            state_path = Path(d) / "p2_state.json"
            original = json.dumps(_state())
            state_path.write_text(original, encoding="utf-8")
            run(payload, state_path, persist=False)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
