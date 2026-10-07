#!/usr/bin/python3
"""P0-1 Decision → Outcome 回流单元测试（零依赖，不伪造 outcome）。

关键纪律：
- 未登记 = 未知（None），**绝不**推断或填默认值；
- adoption_rate 仅在人工登记的 decided 样本 >= MIN_SAMPLE 时才有意义，否则 concluded=False；
- validate() fail-closed：outcome 必带 outcome_at、非法 adopted 状态拒绝、计数自洽。
"""
from __future__ import annotations

import unittest

import decision_outcome as do


def _ledger(n=3):
    return {"version": "ledger-v1.0", "entries": [
        {"event_id": f"evt_{i}", "role": "ai", "urgency": "now",
         "action": f"act_{i}", "decided_at": "2026-10-01T00:00:00Z"}
        for i in range(n)
    ]}


def _reg(eid, **kw):
    return {"event_id": eid, **kw}


class TestDecisionOutcome(unittest.TestCase):
    def test_no_registrations_all_null(self):
        doc = do.build(ledger=_ledger(3), regs={})
        self.assertEqual(doc["meta"]["adoption_registered"], 0)
        self.assertIsNone(doc["meta"]["adoption_rate"])
        self.assertFalse(doc["meta"]["concluded"])
        for it in doc["items"]:
            self.assertIsNone(it["adopted"])
            self.assertIsNone(it["outcome"])

    def test_registered_adoption_counted(self):
        regs = {
            "evt_0": _reg("evt_0", adopted="adopted", adopted_at="t", outcome="有效", outcome_at="t2"),
            "evt_1": _reg("evt_1", adopted="rejected", adopted_at="t"),
        }
        doc = do.build(ledger=_ledger(3), regs=regs)
        m = doc["meta"]
        self.assertEqual(m["adopted"], 1)
        self.assertEqual(m["rejected"], 1)
        self.assertEqual(m["decided_with_adoption"], 2)
        self.assertEqual(m["with_outcome"], 1)
        self.assertEqual(m["adoption_rate"], 0.5)

    def test_unknown_adopted_not_counted(self):
        # 非法/未登记的 adopted 值应归一为 None，不进分子
        regs = {"evt_0": _reg("evt_0", adopted="maybe")}
        doc = do.build(ledger=_ledger(2), regs=regs)
        self.assertEqual(doc["meta"]["decided_with_adoption"], 0)
        self.assertIsNone(doc["meta"]["adoption_rate"])

    def test_concluded_only_above_min_sample(self):
        # 恰好 MIN_SAMPLE 条已登记才 concluded
        big = _ledger(do.MIN_SAMPLE)
        regs = {f"evt_{i}": _reg(f"evt_{i}", adopted="adopted", adopted_at="t")
                for i in range(do.MIN_SAMPLE)}
        doc = do.build(ledger=big, regs=regs)
        self.assertTrue(doc["meta"]["concluded"])
        # 少一条则不结论
        regs2 = {k: v for k, v in list(regs.items())[:-1]}
        doc2 = do.build(ledger=big, regs=regs2)
        self.assertFalse(doc2["meta"]["concluded"])


class TestValidate(unittest.TestCase):
    def test_outcome_without_timestamp_rejected(self):
        regs = {"evt_0": _reg("evt_0", adopted="adopted", adopted_at="t", outcome="x")}
        doc = do.build(ledger=_ledger(1), regs=regs)
        with self.assertRaises(ValueError):
            do.validate(doc)  # outcome 有值但 outcome_at缺失 = 疑似伪造

    def test_valid_doc_passes(self):
        regs = {"evt_0": _reg("evt_0", adopted="adopted", adopted_at="t",
                              outcome="x", outcome_at="t2")}
        doc = do.build(ledger=_ledger(2), regs=regs)
        do.validate(doc)  # 不抛

    def test_count_self_consistency_enforced(self):
        doc = do.build(ledger=_ledger(2), regs={})
        doc["meta"]["decided_with_adoption"] = 99  # 破坏自洽
        with self.assertRaises(ValueError):
            do.validate(doc)


if __name__ == "__main__":
    unittest.main()