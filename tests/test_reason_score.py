#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import collect as C


class TestReasonAndScore(unittest.TestCase):
    def test_rating_reason(self):
        label, _ = C._match_theme(
            "AM Best upgrades Kinsale’s Issuer Credit Ratings",
            "Long-Term Issuer Credit Rating",
        )
        self.assertEqual(label, "评级与信用观察")
        r = C.auto_reason(
            "AM Best upgrades Kinsale’s Issuer Credit Ratings",
            "Issuer Credit Rating affirmed",
            "Reinsurance News", "媒体", "industry", 82,
        )
        self.assertIn("评级", r)

    def test_appoint_not_rating(self):
        label, _ = C._match_theme(
            "Vantage appoints Lucy Fato as General Counsel",
            "specialty re/insurance business",
        )
        self.assertEqual(label, "人事与组织")
        r = C.auto_reason(
            "Vantage appoints Lucy Fato as General Counsel",
            "specialty re/insurance",
            "Reinsurance News", "媒体", "industry", 70,
        )
        self.assertIn("人事", r)
        self.assertNotIn("评级", r)
        self.assertNotIn("地缘", r)

    def test_ai_not_rating(self):
        label, clause = C._match_theme(
            "Viewpoint: If AI Compute Is an Investable Asset, AI Agency Must Become Insurable",
            "NVIDIA generative AI insurance",
        )
        # 应走 AI/科技或低置信兜底，不能是评级
        self.assertNotEqual(label, "评级与信用观察")
        r = C.auto_reason(
            "Viewpoint: If AI Compute Is an Investable Asset, AI Agency Must Become Insurable",
            "NVIDIA AI factory compute insurability",
            "Insurance Journal", "媒体", "industry", 90,
        )
        self.assertNotIn("评级", r)

    def test_hr_score_capped(self):
        sc = C.score_item(
            "Adam Fox to lead Stonybrook’s international growth",
            "appointed as CEO of International reinsurance",
            84,
        )
        self.assertLessEqual(sc, 78)

    def test_rating_topic(self):
        t = C.infer_topic(
            "AM Best upgrades Kinsale’s Issuer Credit Ratings",
            "Financial Strength Rating",
        )
        self.assertEqual(t, "capital_reinsurance")

    def test_infer_topic_none_ok(self):
        t = C.infer_topic("Random weather note", "no insurance keywords here at all xyz")
        self.assertIsNone(t)


if __name__ == "__main__":
    unittest.main()