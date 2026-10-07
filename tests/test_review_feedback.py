#!/usr/bin/python3
"""第八阶段 Human OS 三件套单元测试：反馈通道 / 阈值校准。

核心纪律：
- **反馈只记录人怎么判**，绝不改 review item 状态；
- `auto_action_enabled` 恒 False（本阶段只出校准报告，不放开自动化）；
- 未登记 = 未知，不推断；样本 < MIN_SAMPLE 不 concluded；
- 校准的「提案资格」需同时满足三门（接受率/否决率/样本）。
"""
from __future__ import annotations

import unittest

import review_feedback as rfb
import review_threshold_calibration as cal


def _decision(items_by_tier: dict[str, list[str]]) -> dict:
    """构造 review_decision.json 形状的建议。"""
    labels = {"decision_required": "需人工裁决", "material_change": "复核实质变化",
              "relevant": "一般关注", "noise": "建议归档"}
    pres = []
    for tier, ids in items_by_tier.items():
        pres.append({
            "tier": tier, "label": labels[tier], "count": len(ids),
            "default_collapsed": tier == "noise",
            "items": [{"event_id": i, "tier": tier,
                       "suggested_action": f"act_{tier}", "auto_executable": False}
                      for i in ids],
        })
    return {"version": "d", "presentation": pres}


class TestReviewFeedback(unittest.TestCase):
    def test_no_feedback_is_honest(self):
        doc = rfb.build(decision_doc=_decision({"noise": ["a", "b"]}),
                        feedback={"registrations": []})
        self.assertEqual(doc["meta"]["feedback_matched"], 0)
        self.assertFalse(doc["meta"]["concluded"])
        self.assertEqual(doc["by_tier"], {})

    def test_record_and_accept_rate(self):
        fb = {"registrations": []}
        rfb.record(fb, "a", "accept", reason="ok")
        rfb.record(fb, "b", "reject", reason="low value")
        rfb.record(fb, "c", "modify", modified_action="act_x")
        rfb.record(fb, "d", "defer")
        doc = rfb.build(decision_doc=_decision({"noise": ["a", "b", "c", "d"]}),
                        feedback=fb)
        s = doc["by_tier"]["noise"]
        self.assertEqual(s["total"], 4)
        self.assertEqual(s["accept"], 1)
        self.assertEqual(s["accept_rate"], 0.25)
        self.assertFalse(s["concluded"])

    def test_record_updates_same_event(self):
        fb = {"registrations": []}
        rfb.record(fb, "a", "accept")
        rfb.record(fb, "a", "reject")          # 同事件以最新为准
        self.assertEqual(len(fb["registrations"]), 1)
        self.assertEqual(fb["registrations"][0]["decision"], "reject")

    def test_invalid_decision_rejected(self):
        with self.assertRaises(ValueError):
            rfb.record({"registrations": []}, "a", "maybe")

    def test_unmatched_feedback_not_counted(self):
        fb = {"registrations": [{"event_id": "zzz", "decision": "accept"}]}
        doc = rfb.build(decision_doc=_decision({"noise": ["a"]}), feedback=fb)
        self.assertEqual(doc["meta"]["feedback_matched"], 0)
        self.assertEqual(doc["meta"]["unmatched_feedback"], 1)

    def test_does_not_mutate_decision_items(self):
        d = _decision({"noise": ["a"]})
        before = d["presentation"][0]["items"][0]["auto_executable"]
        rfb.build(decision_doc=d, feedback={"registrations": [{"event_id": "a", "decision": "accept"}]})
        self.assertEqual(d["presentation"][0]["items"][0]["auto_executable"], before)

    def test_validate_rejects_auto_action(self):
        doc = rfb.build(decision_doc=_decision({"noise": ["a"]}),
                        feedback={"registrations": []})
        rfb.validate(doc)
        doc["meta"]["auto_action_enabled"] = True
        with self.assertRaises(ValueError):
            rfb.validate(doc)


class TestThresholdCalibration(unittest.TestCase):
    def _summary(self, n, accept, tier="noise"):
        return {"meta": {"feedback_matched": n},
                "by_tier": {tier: {"total": n, "accept": accept,
                                   "reject": n - accept, "modify": 0, "defer": 0,
                                   "accept_rate": round(accept / n, 4) if n else None,
                                   "concluded": n >= 30}}}

    def test_insufficient_sample_blocks(self):
        doc = cal.build(self._summary(10, 10))
        row = doc["tiers"][0]
        self.assertFalse(row["sample_sufficient"])
        self.assertFalse(row["eligible_for_proposal"])
        self.assertTrue(any("样本不足" in b for b in row["blockers"]))

    def test_high_accept_but_small_sample_still_blocks(self):
        doc = cal.build(self._summary(5, 5))   # 100% 接受但样本不足
        self.assertFalse(doc["tiers"][0]["eligible_for_proposal"])

    def test_all_gates_met_yields_proposal_only(self):
        doc = cal.build(self._summary(30, 30))  # 样本足、接受率 1.0、否决 0
        row = doc["tiers"][0]
        self.assertTrue(row["eligible_for_proposal"])
        # 关键：即使满足三门，也绝不自动执行
        self.assertFalse(row["auto_action_enabled"])
        self.assertFalse(doc["meta"]["auto_action_enabled"])

    def test_low_accept_blocks(self):
        doc = cal.build(self._summary(30, 10))  # 接受率 33%
        self.assertFalse(doc["tiers"][0]["eligible_for_proposal"])

    def test_empty_data_graceful(self):
        doc = cal.build({"meta": {"feedback_matched": 0}, "by_tier": {}})
        self.assertFalse(doc["meta"]["data_sufficient"])
        self.assertFalse(doc["meta"]["any_tier_eligible"])


if __name__ == "__main__":
    unittest.main()