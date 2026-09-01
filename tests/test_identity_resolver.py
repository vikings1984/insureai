#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S2 Identity Resolver — 单测。纪律：不伪造、observation/conclusion 分离、fail-closed。"""
from __future__ import annotations

import unittest

import event_registry as er
import identity_resolver as ir


def _registry():
    events = [
        ({"event_id": "evt_a", "title": "A", "topic": "t", "event_type": "et", "published_at": "2024-01-01"}, "daily_brief"),
        ({"event_id": "evt_b", "title": "B", "topic": "t", "event_type": "et", "published_at": "2024-01-02"}, "review_queue"),
    ]
    return er.build(events)


class IdentityResolverTests(unittest.TestCase):
    def setUp(self):
        self.reg = _registry()
        self.cev_a = er._canonical_id("evt_a")
        self.cev_b = er._canonical_id("evt_b")

    def test_resolve_event_id_to_canonical(self):
        self.assertEqual(ir.resolve("evt_a", self.reg), self.cev_a)
        self.assertEqual(ir.resolve("evt_b", self.reg), self.cev_b)

    def test_resolve_unknown_returns_none(self):
        self.assertIsNone(ir.resolve("evt_zzz", self.reg))
        self.assertIsNone(ir.resolve("", self.reg))

    def test_classify_event_id_alias_canonical_unknown(self):
        self.assertEqual(ir.classify("evt_a", self.reg), "event_id")
        self.assertEqual(ir.classify(self.cev_a, self.reg), "canonical")
        er.alias(self.reg, "evt_a_legacy", self.cev_a)
        self.assertEqual(ir.classify("evt_a_legacy", self.reg), "alias")
        self.assertEqual(ir.resolve("evt_a_legacy", self.reg), self.cev_a)
        self.assertEqual(ir.classify("nope", self.reg), "unknown")

    def test_resolve_fingerprint_no_map_returns_none(self):
        # fingerprint 本身不是事件身份，无证据映射→None（不伪造）
        self.assertIsNone(ir.resolve_fingerprint("fp_abc"))
        self.assertIsNone(ir.resolve_fingerprint("fp_abc", {}))

    def test_resolve_fingerprint_via_evidence_map(self):
        fmap = {"fp_abc": self.cev_a}
        self.assertEqual(ir.resolve_fingerprint("fp_abc", fmap), self.cev_a)
        self.assertIsNone(ir.resolve_fingerprint("fp_other", fmap))

    def test_propose_merges_detects_shared_entity(self):
        threads = [
            {"entity": "阳光保险", "type": "org", "events": [{"event_id": "evt_a"}, {"event_id": "evt_b"}]},
            {"entity": "无关实体", "type": "org", "events": [{"event_id": "evt_a"}]},
        ]
        cands = ir.propose_merges_from_entity_threads(threads, self.reg)
        self.assertEqual(len(cands), 1)
        c = cands[0]
        self.assertEqual(c["entity"], "阳光保险")
        self.assertEqual(set(c["canonical_ids"]), {self.cev_a, self.cev_b})
        self.assertEqual(c["status"], "proposed")  # observation，不执行

    def test_propose_merges_skips_single_event(self):
        threads = [{"entity": "X", "type": "org", "events": [{"event_id": "evt_a"}]}]
        self.assertEqual(ir.propose_merges_from_entity_threads(threads, self.reg), [])

    def test_build_report_coverage_and_unresolved(self):
        refs = ["evt_a", "evt_b", "evt_unknown"]
        threads = [{"entity": "阳光保险", "type": "org", "events": [{"event_id": "evt_a"}, {"event_id": "evt_b"}]}]
        report = ir.build_report(entity_threads=threads, refs=refs, registry=self.reg)
        self.assertEqual(report["total_references"], 3)
        self.assertEqual(report["resolved"], 2)
        self.assertEqual(report["unresolved"], 1)
        self.assertAlmostEqual(report["unresolved_rate"], 1 / 3, places=4)
        self.assertIn("evt_unknown", report["unresolved_samples"])
        self.assertEqual(report["candidate_merges"]["count"], 1)
        self.assertEqual(report["candidate_merges"]["status"], "proposed")
        self.assertEqual(report["fingerprint_bridge"]["total_in_map"], 0)

    def test_validate_fail_closed_on_executed_status(self):
        refs = ["evt_a"]
        report = ir.build_report(refs=refs, registry=self.reg)
        report["candidate_merges"]["status"] = "executed"
        with self.assertRaises(AssertionError):
            ir.validate(report)

    def test_validate_fail_closed_on_count_mismatch(self):
        report = ir.build_report(refs=["evt_a"], registry=self.reg)
        report["unresolved"] = 99  # 破坏计数自洽
        with self.assertRaises(AssertionError):
            ir.validate(report)


if __name__ == "__main__":
    import unittest
    unittest.main()
