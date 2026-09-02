#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S3 Acquisition Lifecycle — 单测。纪律：阶段源自 Claim+Evidence；不伪造；fail-closed。"""
from __future__ import annotations

import unittest

import event_registry as er
import acquisition_lifecycle as lc


def _claims(text: str, claim_type: str = "acquisition_intent", tier: int = 3) -> list[dict]:
    return [{
        "claim_type": claim_type,
        "claim_text": text,
        "supporting_evidence": [{"evidence_id": "ev1", "matched_span": text, "source_tier": tier}],
    }]


class AcquisitionLifecycleTests(unittest.TestCase):
    def test_is_acquisition_event_true(self):
        self.assertTrue(lc.is_acquisition_event(_claims("A 拟收购 B")))

    def test_is_acquisition_event_false(self):
        self.assertFalse(lc.is_acquisition_event([{"claim_type": "event_summary", "claim_text": "公司发布季报"}]))

    def test_derive_stage_rumor_from_intent(self):
        res = lc.derive_stage(_claims("A 拟收购 B"))
        self.assertEqual(res["stage"], "rumor")
        self.assertGreater(res["confidence"], 0)

    def test_derive_stage_agreement_from_signed(self):
        res = lc.derive_stage(_claims("A 签署收购协议 B"))
        self.assertEqual(res["stage"], "agreement")

    def test_derive_stage_closing_from_completed(self):
        res = lc.derive_stage(_claims("A 完成交割 B"))
        self.assertEqual(res["stage"], "closing")

    def test_derive_stage_closing_from_buys(self):
        res = lc.derive_stage(_claims("Verisk Buys McKenzie Intelligence"))
        self.assertEqual(res["stage"], "closing")

    def test_derive_stage_takes_max_progression(self):
        # 同时含 rumor + closing 信号 → 取最高阶段 closing
        claims = [{
            "claim_type": "acquisition_intent",
            "claim_text": "A 拟收购 B 并于近日完成交割",
            "supporting_evidence": [{"evidence_id": "ev1", "matched_span": "A 拟收购 B 并于近日完成交割", "source_tier": 2}],
        }]
        res = lc.derive_stage(claims)
        self.assertEqual(res["stage"], "closing")

    def test_derive_stage_non_ma_is_na(self):
        res = lc.derive_stage([{"claim_type": "event_summary", "claim_text": "公司发布季报"}])
        self.assertEqual(res["stage"], "n/a")
        self.assertEqual(res["confidence"], 0.0)

    def test_enrich_registry_populates_stage(self):
        registry = er.build([({"event_id": "evt_a", "title": "A", "published_at": "2024-01-01"}, "daily_brief")])
        lc.enrich_registry(registry, {"evt_a": _claims("A 拟收购 B")})
        cev = er._canonical_id("evt_a")
        self.assertEqual(registry["canonical_events"][cev]["stage"], "rumor")
        self.assertIn("lifecycle", registry["canonical_events"][cev])

    def test_build_report_counts_consistent(self):
        registry = er.build([
            ({"event_id": "evt_a", "title": "A", "published_at": "2024-01-01"}, "daily_brief"),
            ({"event_id": "evt_b", "title": "B 季报", "published_at": "2024-01-02"}, "daily_brief"),
        ])
        # evt_a = M&A(rumor), evt_b = non-M&A(n/a)
        report = lc.build_report(registry, {"evt_a": _claims("A 拟收购 B"), "evt_b": [{"claim_type": "event_summary", "claim_text": "B 季报"}]})
        self.assertEqual(report["total_canonical"], 2)
        self.assertEqual(report["acquisition_events"], 1)
        self.assertEqual(sum(report["stage_counts"].values()), 2)
        self.assertEqual(report["stage_counts"]["rumor"], 1)
        self.assertEqual(report["stage_counts"]["n/a"], 1)

    def test_validate_fail_closed_on_bad_stage(self):
        registry = er.build([({"event_id": "evt_a", "title": "A", "published_at": "2024-01-01"}, "daily_brief")])
        report = lc.build_report(registry, {"evt_a": _claims("A 拟收购 B")})
        report["entries"][0]["stage"] = "bogus"
        with self.assertRaises(AssertionError):
            lc.validate(report)


class DomainPluginTests(unittest.TestCase):
    """lc-v1.1：生命周期按 domain 插件化，禁止把收购六段默默通用化。"""

    def test_domain_of_prefers_registry_domain(self):
        self.assertEqual(lc.domain_of({"domain": "regulatory"}, []), "regulatory")
        self.assertEqual(lc.domain_of({"domain": "acquisition"}, []), "acquisition")

    def test_domain_of_falls_back_to_claims_when_other(self):
        # Registry domain=other 但 Claim 文本是收购 → 回退推断为 acquisition
        self.assertEqual(lc.domain_of({"domain": "other"}, _claims("A 拟收购 B")), "acquisition")
        # 既非注册 domain 也非收购 Claim → other
        self.assertEqual(lc.domain_of({"domain": "other"}, [{"claim_type": "event_summary", "claim_text": "季报"}]), "other")

    def test_derive_stage_regulatory_returns_status_not_stage(self):
        res = lc.derive_stage(_claims("银保监会发布车险费率新规", claim_type="regulatory"), domain="regulatory")
        self.assertEqual(res["stage"], "n/a")          # regulatory 无 stage 演进
        self.assertEqual(res["status"], "issued")       # 命中「发布」
        self.assertEqual(res["domain"], "regulatory")

    def test_derive_stage_regulatory_effective_with_date(self):
        res = lc.derive_stage(
            _claims("新规自 2026-01-15 起生效", claim_type="regulatory"), domain="regulatory"
        )
        self.assertEqual(res["stage"], "n/a")
        self.assertEqual(res["status"], "effective")
        self.assertEqual(res["effective"], "2026-01-15")

    def test_derive_stage_regulatory_unknown_without_signal(self):
        res = lc.derive_stage(_claims("行业动态", claim_type="regulatory"), domain="regulatory")
        self.assertEqual(res["stage"], "n/a")
        self.assertEqual(res["status"], "unknown")
        self.assertEqual(res["confidence"], 0.0)

    def test_derive_stage_catastrophe_is_na(self):
        res = lc.derive_stage(_claims("台风红色预警", claim_type="catastrophe"), domain="catastrophe")
        self.assertEqual(res["stage"], "n/a")
        self.assertEqual(res["domain"], "catastrophe")

    def test_derive_stage_other_is_na(self):
        res = lc.derive_stage([{"claim_type": "event_summary", "claim_text": "公司发布季报"}], domain="other")
        self.assertEqual(res["stage"], "n/a")
        self.assertIsNone(res["status"])

    def test_build_report_regulatory_entry_carries_status_and_na_stage(self):
        registry = er.build([({"event_id": "evt_r", "title": "R", "published_at": "2024-02-01", "event_type": "regulatory"}, "daily_brief")])
        report = lc.build_report(registry, {"evt_r": _claims("协会发布行业自律指引", claim_type="regulatory")})
        self.assertEqual(report["domain_counts"]["regulatory"], 1)
        ent = report["entries"][0]
        self.assertEqual(ent["domain"], "regulatory")
        self.assertEqual(ent["stage"], "n/a")
        self.assertEqual(ent["status"], "issued")

    def test_validate_rejects_regulatory_with_stage(self):
        """regulatory 域禁止误写 stage（X2 评审硬约束）。"""
        report = {
            "version": lc.VERSION, "generated_at": "2024", "total_canonical": 1,
            "acquisition_events": 0,
            "stage_counts": {"rumor": 0, "negotiation": 0, "agreement": 0, "regulatory": 0, "closing": 0, "integration": 0, "n/a": 1},
            "domain_counts": {"acquisition": 0, "regulatory": 1, "catastrophe": 0, "other": 0},
            "entries": [{"canonical_event_id": "cev_r", "domain": "regulatory", "stage": "rumor",
                         "status": "issued", "confidence": 0.5, "evidence_refs": [], "reason": "x"}],
        }
        with self.assertRaises(AssertionError):
            lc.validate(report)


if __name__ == "__main__":
    unittest.main()
