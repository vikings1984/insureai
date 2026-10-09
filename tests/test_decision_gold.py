#!/usr/bin/python3
"""B：一次人力两产出（outcome 登记顺带产出 Decision Gold）单元测试。

核心纪律：
- gold 标签**只来自人工登记**，未填=未知，**不推断、不填充**；
- 一次登记同时产出 outcome（反馈链）+ decision gold（精度基准），即「一次人力两产出」；
- 样本 < MIN_SAMPLE 不concluded；**绝不**放开自动化（auto_action_enabled 恒False）；
- 本模块不改任何 review/decision 状态。
"""
from __future__ import annotations

import unittest

import decision_gold as dg


def _ledger(n=3):
    return {"entries": [{"event_id": f"e{i}", "role": "executive", "urgency": "now",
                         "action": f"act{i}", "decided_at": "2026-10-01T00:00:00Z"}
                        for i in range(n)]}


def _reg(eid, **kw):
    return {"event_id": eid, **kw}


class TestDecisionGold(unittest.TestCase):
    def test_no_labels_is_honest(self):
        """没有 gold 标注 → 样本 0，指标为 None（不推断）。"""
        out = dg.build(input_doc={"registrations": [_reg("e0", outcome="x")]},
                       ledger=_ledger())
        self.assertEqual(out["meta"]["labeled_samples"], 0)
        self.assertIsNone(out["metrics"]["decision_precision"])
        self.assertFalse(out["meta"]["concluded"])

    def test_only_labeled_rows_counted(self):
        inp = {"registrations": [
            _reg("e0", decision_was_right="yes", action_was_right="yes", urgency_regret="none"),
            _reg("e1", outcome="未填 gold 标签"),
        ]}
        out = dg.build(input_doc=inp, ledger=_ledger(2))
        self.assertEqual(out["meta"]["labeled_samples"], 1)   # e1 不计
        self.assertEqual(out["items"][0]["event_id"], "e0")

    def test_decision_and_action_precision(self):
        inp = {"registrations": [
            _reg("e0", decision_was_right="yes", action_was_right="yes"),
            _reg("e1", decision_was_right="yes", action_was_right="no"),
            _reg("e2", decision_was_right="no", action_was_right="yes"),
        ]}
        out = dg.build(input_doc=inp, ledger=_ledger(3))
        self.assertAlmostEqual(out["metrics"]["decision_precision"], 2 / 3, places=3)
        self.assertAlmostEqual(out["metrics"]["action_precision"], 2 / 3, places=3)

    def test_partial_not_counted_as_correct(self):
        inp = {"registrations": [
            _reg("e0", decision_was_right="partial"),
            _reg("e1", decision_was_right="yes"),
        ]}
        out = dg.build(input_doc=inp, ledger=_ledger(2))
        # partial 不计入分子 → 1/2
        self.assertAlmostEqual(out["metrics"]["decision_precision"], 0.5, places=3)

    def test_urgency_regret_distribution(self):
        inp = {"registrations": [
            _reg("e0", urgency_regret="too_late"),
            _reg("e1", urgency_regret="too_late"),
            _reg("e2", urgency_regret="none"),
        ]}
        out = dg.build(input_doc=inp, ledger=_ledger(3))
        self.assertEqual(out["metrics"]["urgency_regret_counts"]["too_late"], 2)
        self.assertEqual(out["metrics"]["urgency_regret_counts"]["none"], 1)

    def test_auto_action_never_enabled(self):
        out = dg.build(input_doc={"registrations": []}, ledger=_ledger())
        self.assertFalse(out["meta"]["auto_action_enabled"])
        dg.validate(out)   # 不抛

    def test_validate_rejects_auto_action(self):
        out = dg.build(input_doc={"registrations": []}, ledger=_ledger())
        out["meta"]["auto_action_enabled"] = True
        with self.assertRaises(ValueError):
            dg.validate(out)

    def test_validate_rejects_illegal_value(self):
        inp = {"registrations": [_reg("e0", decision_was_right="maybe")]}
        out = dg.build(input_doc=inp, ledger=_ledger(1))
        # 非法值不会被 build 收录（因不 in GOLD_FIELDS 集合）
        self.assertEqual(out["meta"]["labeled_samples"], 0)


if __name__ == "__main__":
    unittest.main()