#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import claims
from source_tiers import tier_for_item


def _item(id_, title, source, domain, published_at="2026-08-21T10:00:00+00:00", **extra):
    row = {
        "id": id_,
        "title": title,
        "tags": "Munich Re,At-Bay",
        "source_name": source,
        "source_url": f"https://{domain}/example",
        "published_at": published_at,
        "date_verified": True,
    }
    row.update(extra)
    return row


class TestPropositionExtraction(unittest.TestCase):
    def setUp(self):
        self.items = [
            _item("1", "Munich Re to acquire At-Bay for $575 million", "Reuters", "www.reuters.com"),
            _item("2", "Munich Re agrees to buy At-Bay for $575 million", "Insurance Journal", "www.insurancejournal.com", "2026-08-21T11:00:00+00:00"),
        ]
        self.event = {"event_id": "evt_1", "title": "Munich Re 收购 At-Bay", "event_type": "acquisition"}

    def test_acquisition_yields_three_plus_propositions(self):
        result = claims.build_claims(self.items, self.event)
        types = {c["claim_type"] for c in result["claims"]}
        self.assertIn("acquisition_intent", types)
        self.assertIn("transaction_amount", types)
        self.assertIn("transaction_scope", types)
        self.assertGreaterEqual(len(result["claims"]), 3)
        self.assertEqual(result["version"], 3)

    def test_propositions_have_schema_v3_fields(self):
        result = claims.build_claims(self.items, self.event)
        for c in result["claims"]:
            self.assertTrue(c["claim_id"])
            self.assertTrue(c["claim_text"])
            self.assertIn(c["verification_status"], claims.VERIFICATION_STATUSES)
            self.assertIn("supporting_evidence", c)
            self.assertIn("contradicting_evidence", c)
            self.assertIn("confidence", c)
            self.assertIn("first_seen", c)
            self.assertIn("last_confirmed", c)

    def test_amount_claim_is_cross_checked(self):
        result = claims.build_claims(self.items, self.event)
        amount = next(c for c in result["claims"] if c["claim_type"] == "transaction_amount")
        self.assertEqual(amount["verification_status"], "cross_checked")
        self.assertEqual(amount["independent_domains"], 2)
        self.assertEqual(amount["evidence_count"], 2)
        self.assertEqual(len(amount["contradicting_evidence"]), 0)
        self.assertEqual(amount["value"]["normalized"], 575000000.0)
        self.assertEqual(amount["first_seen"], "2026-08-21")

    def test_cross_language_amount_cross_check(self):
        items = [
            _item("1", "Munich Re to acquire At-Bay for $575 million", "Reuters", "www.reuters.com"),
            _item("2", "Munich Re 拟以5.75亿美元收购 At-Bay", "Insurance Journal", "www.insurancejournal.com", "2026-08-21T11:00:00+00:00"),
        ]
        result = claims.build_claims(items, self.event)
        amounts = [c for c in result["claims"] if c["claim_type"] == "transaction_amount"]
        self.assertEqual(len(amounts), 1)
        self.assertEqual(amounts[0]["verification_status"], "cross_checked")
        self.assertEqual(amounts[0]["independent_domains"], 2)


class TestConflictDetection(unittest.TestCase):
    def test_inconsistent_amounts_are_conflicted(self):
        items = [
            _item("1", "Munich Re to acquire At-Bay for $575 million", "Reuters", "www.reuters.com"),
            _item("2", "Munich Re agrees to buy At-Bay for $600 million", "Insurance Journal", "www.insurancejournal.com", "2026-08-21T11:00:00+00:00"),
        ]
        event = {"event_id": "evt_2", "title": "Munich Re 收购 At-Bay", "event_type": "acquisition"}
        result = claims.build_claims(items, event)
        conflicted = [c for c in result["claims"] if c["verification_status"] == "conflicted"]
        self.assertTrue(conflicted)
        amount = next(c for c in conflicted if c["claim_type"] == "transaction_amount")
        self.assertEqual(len(amount["supporting_evidence"]), 1)
        self.assertEqual(len(amount["contradicting_evidence"]), 1)
        self.assertEqual(amount["contradicting_evidence"][0]["relation"], "contradict")
        self.assertEqual(amount["contradicting_evidence"][0]["evidence_id"], "2")
        self.assertLess(amount["confidence"], 80)


class TestConfidencePolicy(unittest.TestCase):
    def test_single_source_capped_below_65(self):
        items = [_item("1", "Munich Re to acquire At-Bay for $575 million", "Reuters", "www.reuters.com")]
        event = {"event_id": "evt_3", "title": "Munich Re 收购 At-Bay", "event_type": "acquisition"}
        result = claims.build_claims(items, event)
        self.assertTrue(all(c["verification_status"] != "cross_checked" for c in result["claims"]))
        for c in result["claims"]:
            self.assertLessEqual(c["confidence"], 65)

    def test_same_domain_duplicates_do_not_inflate(self):
        items = [
            _item("1", "Munich Re to acquire At-Bay for $575 million", "Insurance Journal", "www.insurancejournal.com"),
            _item("2", "Munich Re agrees to buy At-Bay for $575 million", "Insurance Journal", "www.insurancejournal.com", "2026-08-21T11:00:00+00:00"),
        ]
        event = {"event_id": "evt_4", "title": "Munich Re 收购 At-Bay", "event_type": "acquisition"}
        result = claims.build_claims(items, event)
        for c in result["claims"]:
            self.assertEqual(c["independent_domains"], 1)
            self.assertEqual(c["verification_status"], "single_source")
            self.assertLessEqual(c["confidence"], 65)

    def test_tier_weighting_orders_confidence(self):
        event = {"event_id": "evt_5", "title": "Munich Re 收购 At-Bay", "event_type": "acquisition"}
        tier1 = claims.build_claims([_item("1", "Munich Re to acquire At-Bay for $575 million", "监管文件", "www.nfra.gov.cn")], event)
        tier4 = claims.build_claims([_item("1", "Munich Re to acquire At-Bay for $575 million", "某博客", "medium.com")], event)
        t1 = next(c for c in tier1["claims"] if c["claim_type"] == "transaction_amount")
        t4 = next(c for c in tier4["claims"] if c["claim_type"] == "transaction_amount")
        self.assertGreater(t1["confidence"], t4["confidence"])


class TestSourceTiers(unittest.TestCase):
    def test_regulator_is_tier1(self):
        self.assertEqual(tier_for_item({"source_url": "https://www.nfra.gov.cn/x", "source_type": "媒体"}), 1)

    def test_wire_service_is_tier2(self):
        self.assertEqual(tier_for_item({"source_url": "https://www.reuters.com/x", "source_type": "媒体"}), 2)

    def test_industry_media_defaults_tier3(self):
        self.assertEqual(tier_for_item({"source_url": "https://www.insurancejournal.com/x", "source_type": "媒体"}), 3)

    def test_blog_is_tier4(self):
        self.assertEqual(tier_for_item({"source_url": "https://medium.com/x", "source_type": "媒体"}), 4)

    def test_official_source_type_is_tier1(self):
        self.assertEqual(tier_for_item({"source_url": "https://example.com/x", "source_type": "公司发布"}), 1)


class TestEvidenceDirectionality(unittest.TestCase):
    def test_keyword_hit_without_subject_is_context_not_dropped(self):
        items = [
            _item("1", "Munich Re to acquire At-Bay", "Reuters", "www.reuters.com"),
            _item("2", "慕尼黑再保险宣布收购计划", "行业媒体", "www.media.cn", "2026-08-21T11:00:00+00:00"),
        ]
        event = {"event_id": "evt_8", "title": "Munich Re 收购 At-Bay", "event_type": "acquisition"}
        result = claims.build_claims(items, event)
        intent = next(c for c in result["claims"] if c["claim_type"] == "acquisition_intent")
        relations = {x["evidence_id"]: x["relation"] for x in intent["supporting_evidence"] + intent["contradicting_evidence"] + intent["context_evidence"]}
        self.assertEqual(relations.get("1"), "support")
        self.assertEqual(relations.get("2"), "context")

    def test_context_evidence_rows_carry_tier_and_span(self):
        items = [
            _item("1", "Munich Re to acquire At-Bay", "Reuters", "www.reuters.com"),
            _item("2", "慕尼黑再保险宣布收购计划", "行业媒体", "www.media.cn", "2026-08-21T11:00:00+00:00"),
        ]
        event = {"event_id": "evt_9", "title": "Munich Re 收购 At-Bay", "event_type": "acquisition"}
        result = claims.build_claims(items, event)
        intent = next(c for c in result["claims"] if c["claim_type"] == "acquisition_intent")
        ctx = next(x for x in intent["context_evidence"])
        self.assertEqual(ctx["relation"], "context")
        self.assertTrue(ctx["matched_span"])
        self.assertIn("source_tier", ctx)

    def test_context_does_not_change_verification_status(self):
        items = [
            _item("1", "Munich Re to acquire At-Bay", "Reuters", "www.reuters.com"),
            _item("2", "慕尼黑再保险宣布收购计划", "行业媒体", "www.media.cn", "2026-08-21T11:00:00+00:00"),
        ]
        event = {"event_id": "evt_10", "title": "Munich Re 收购 At-Bay", "event_type": "acquisition"}
        result = claims.build_claims(items, event)
        for c in result["claims"]:
            if c["context_evidence"] and not c["supporting_evidence"]:
                self.assertEqual(c["verification_status"], "unverified")
            if c["supporting_evidence"]:
                self.assertIn(c["verification_status"], ("single_source", "cross_checked", "conflicted"))


class TestCategorySupport(unittest.TestCase):
    def test_unsupported_event_type_degrades_to_summary(self):
        """上游把资本话题评论误标为 capital 时，不得产出无证据的融资命题。"""
        items = [_item("1", "J.P. Morgan says reinsurance pricing unlikely to stabilise before 2027", "Reuters", "www.reuters.com")]
        event = {"event_id": "evt_11", "title": "J.P. Morgan 再保险定价评论", "event_type": "capital"}
        result = claims.build_claims(items, event)
        types = {c["claim_type"] for c in result["claims"]}
        self.assertNotIn("capital_raise", types)
        self.assertIn("event_summary", types)
        for c in result["claims"]:
            self.assertNotEqual(c["verification_status"], "unverified")

    def test_supported_event_type_still_applies_template(self):
        items = [_item("1", "InsurTech startup raises $50 million in funding round", "Reuters", "www.reuters.com", tags="InsurTech")]
        event = {"event_id": "evt_12", "title": "InsurTech 融资", "event_type": "capital"}
        result = claims.build_claims(items, event)
        types = {c["claim_type"] for c in result["claims"]}
        self.assertIn("capital_raise", types)
        for c in result["claims"]:
            self.assertNotEqual(c["verification_status"], "unverified")

    def test_keyword_evidence_can_rescue_untyped_event(self):
        items = [_item("1", "Munich Re to acquire At-Bay for $575 million", "Reuters", "www.reuters.com")]
        event = {"event_id": "evt_13", "title": "Munich Re 收购 At-Bay", "event_type": "industry_update"}
        result = claims.build_claims(items, event)
        types = {c["claim_type"] for c in result["claims"]}
        self.assertIn("acquisition_intent", types)


class TestFallbackEvents(unittest.TestCase):
    def test_generic_event_still_yields_summary_proposition(self):
        items = [_item("1", "行业观察：保险科技融资升温", "Insurance Journal", "www.insurancejournal.com")]
        event = {"event_id": "evt_6", "title": "保险科技融资升温"}
        result = claims.build_claims(items, event)
        self.assertGreaterEqual(len(result["claims"]), 1)
        self.assertTrue(all(c["claim_id"] for c in result["claims"]))

    def test_no_items_yields_empty_claims(self):
        result = claims.build_claims([], {"event_id": "evt_7", "title": "空事件", "event_type": "acquisition"})
        self.assertEqual(result["claims"], [])
        self.assertEqual(result["coverage"], 0)


if __name__ == "__main__":
    unittest.main()
