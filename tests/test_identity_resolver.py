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


def _registry_two_domains():
    """一个 acquisition + 一个 regulatory，便于验证跨 domain 合并门。"""
    events = [
        ({"event_id": "evt_acq1", "title": "Munich Re 收购 At-Bay", "topic": "t", "event_type": "acquisition", "published_at": "2024-01-01"}, "daily_brief"),
        ({"event_id": "evt_acq2", "title": "Munich Re agrees to buy At-Bay", "topic": "t", "event_type": "acquisition", "published_at": "2024-01-02"}, "review_queue"),
        ({"event_id": "evt_reg1", "title": "Regulator issues AI guidance", "topic": "t", "event_type": "regulatory", "published_at": "2024-01-03"}, "review_queue"),
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

    # ---- X2（评审修订）：按 event_type 分区解析 ----

    def test_partition_classify_returns_domain_and_canonicalize(self):
        cev = er._canonical_id("evt_a")
        part = ir.partition_classify(cev, self.reg)
        # 测试用 event_type="et" → domain=other，alias-only（不可自动归并）
        self.assertEqual(part["domain"], "other")
        self.assertFalse(part["canonicalize"])
        self.assertEqual(part["event_type"], "et")
        # 未知 CE → 一律不可解析
        none_part = ir.partition_classify("cev_unknown", self.reg)
        self.assertEqual(none_part, {"domain": None, "canonicalize": False, "event_type": None})

    def test_resolve_with_partition_shape(self):
        rp = ir.resolve_with_partition("evt_a", self.reg)
        self.assertTrue(rp["resolved"])
        self.assertEqual(rp["canonical_event_id"], self.cev_a)
        self.assertEqual(rp["domain"], "other")
        self.assertFalse(rp["canonicalize"])
        # 未知引用 → resolved=False，不伪造
        rp_none = ir.resolve_with_partition("evt_zzz", self.reg)
        self.assertFalse(rp_none["resolved"])
        self.assertIsNone(rp_none["canonical_event_id"])

    def test_propose_merges_rejects_cross_domain_entity(self):
        reg = _registry_two_domains()
        # 同一实体跨 acquisition 与 regulatory 两个 domain → 不得提议合并
        cross = [{"entity": "阳光保险", "type": "org",
                  "events": [{"event_id": "evt_acq1"}, {"event_id": "evt_reg1"}]}]
        self.assertEqual(ir.propose_merges_from_entity_threads(cross, reg), [])
        # 同 domain 内（既有 test_propose_merges_detects_shared_entity 已覆盖）仍按观察提出

    def test_generic_only_threads_flagged_review_not_ce(self):
        threads = [
            {"entity": "某通用实体", "type": "org", "events": [{"note": "无 event_id"}]},
            {"entity": "有事件实体", "type": "org", "events": [{"event_id": "evt_a"}]},
        ]
        gen = ir.collect_generic_only_threads(threads, self.reg)
        self.assertEqual(len(gen), 1)
        self.assertEqual(gen[0]["entity"], "某通用实体")
        self.assertFalse(gen[0]["into_ce"])
        self.assertIn("generic_entities_only", gen[0]["reason"])

    def test_build_report_includes_partition_stats_and_generic_review(self):
        # 显式传 entity_threads=[] 使 generic_review 仅取决于本测试输入（hermetic），
        # 不依赖真实 second_brain.json 的 generic-only 实体数（Sprint 3 重建后为 20）。
        report = ir.build_report(refs=["evt_a"], registry=self.reg, entity_threads=[])
        self.assertIn("partition_stats", report)
        self.assertIn("generic_review", report)
        self.assertIsInstance(report["partition_stats"], dict)
        self.assertEqual(report["partition_stats"].get("other"), 1)
        self.assertEqual(report["generic_review"]["count"], 0)
        ir.validate(report)  # 新增字段必须过 fail-closed


if __name__ == "__main__":
    import unittest
    unittest.main()
