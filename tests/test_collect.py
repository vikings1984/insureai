#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""InsureAI 采集管道单元测试（适配默认 collect.py）

覆盖：
  - is_insurance_relevant：强信号门控（正例/噪声负例）
  - STRONG_INSURANCE_TERMS：中英文信号词齐备
  - infer_topic：研究主题分类
  - score_item：评分边界
  - lev_ratio / is_dup：去重
  - clean_text / _category：清洗与分类
  - fetch_eastmoney：中文源可连通（网络可用时返回条目）
"""
import os
import sys
import unittest

# 确保能导入 collect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collect import (
    is_insurance_relevant,
    STRONG_INSURANCE_TERMS,
    RESEARCH_TOPICS,
    infer_topic,
    score_item,
    lev_ratio,
    is_dup,
    clean_text,
    _category,
    fetch_eastmoney,
    fetch_iachina,
)


class TestInsuranceRelevance(unittest.TestCase):
    """强信号门控：保险域词必须显式出现，泛词误命中须被拒。"""

    TRUE_CASES = [
        ("Reinsurance News: Treaty renewals slow in 2026", "Reinsurers face capacity pressure."),
        ("中国再保险市场迎来新机遇", "再保险合同登记交易中心落地。"),
        ("AI transforms underwriting at insurers", "Insurtech adoption rises among underwriters."),
        ("车险综改进一步深化", "保费定价更趋市场化。"),
        ("个人养老金制度扩围", "养老金融供给增加。"),
    ]

    FALSE_CASES = [
        ("Fatal Boat Capsizing Claims Three Lives", "Rescue operations continue off coast."),
        ("Microsoft Joins AI-Driven Tech Layoff Wave With 4,800 Job Cuts", "Workforce reduction announced."),
        ("Trump Ramps Up War on Regulations With 702 Cuts in Pipeline", "Red tape reduction effort."),
        ("Local Council Approves New Parking Policy", "Residents welcome the plan."),
        ("Company Reports Strong Quarterly Data", "Revenue up year over year."),
    ]

    def test_positive(self):
        for title, summary in self.TRUE_CASES:
            with self.subTest(title=title):
                self.assertTrue(is_insurance_relevant(title, summary),
                                f"应判定为保险相关: {title}")

    def test_negative_noise(self):
        for title, summary in self.FALSE_CASES:
            with self.subTest(title=title):
                self.assertFalse(is_insurance_relevant(title, summary),
                                 f"噪声应被拒: {title}")


class TestStrongTerms(unittest.TestCase):
    def test_covers_both_languages(self):
        joined = " ".join(STRONG_INSURANCE_TERMS).lower()
        for must in ["insurance", "reinsurance", "保险", "再保险", "承保", "理赔", "保费"]:
            self.assertIn(must, joined, f"STRONG_INSURANCE_TERMS 缺少关键信号词: {must}")

    def test_no_overly_generic_terms(self):
        # 这些泛词曾造成误命中，确认其本身未作为独立强信号词出现
        # （注意：policyholder/policyholders 等复合词是合法强信号，不算泛词）
        bad = ["policy", "claim", "report", "data", "product", "digital", "capital"]
        for b in bad:
            self.assertNotIn(b, STRONG_INSURANCE_TERMS, f"泛词不应作为独立强信号: {b}")


class TestInferTopic(unittest.TestCase):
    def test_maps_keywords(self):
        cases = [
            ("AI 大模型重塑智能核保", "ai_intelligent"),
            ("个人养老金第三支柱提速", "pension_finance"),
            ("UBI 车险产品创新上线", "product_innovation"),
            ("银保渠道转型加速", "channel_transformation"),
            ("巨灾债券 ILS 扩容", "capital_reinsurance"),
            ("气候巨灾保险指数化", "climate_catastrophe"),
            ("保险科技核心系统升级", "digital_transformation"),
            ("监管办法落地合规收紧", "regulatory_change"),
        ]
        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(infer_topic(title, ""), expected)

    def test_returns_none_when_no_match(self):
        self.assertIsNone(infer_topic("一条无关新闻标题", "正文也无关键词"))


class TestScoreItem(unittest.TestCase):
    def test_bounds(self):
        for title, summary, auth in [
            ("AI 承保革新", "insurtech 大模型", 84),
            ("普通公告", "无关键词内容", 60),
            ("养老 巨灾 偿付能力 突破", "reinsurance catastrophe", 95),
        ]:
            s = score_item(title, summary, auth)
            with self.subTest(title=title):
                self.assertGreaterEqual(s, 60)
                self.assertLessEqual(s, 95)


class TestDedup(unittest.TestCase):
    def test_lev_ratio_identical(self):
        self.assertAlmostEqual(lev_ratio("同一标题", "同一标题"), 1.0)

    def test_lev_ratio_different(self):
        self.assertLess(lev_ratio("完全不相关的标题A", "另一个风马牛不相及的标题B"), 0.5)

    def test_is_dup_threshold(self):
        existing = ["Reinsurance treaty renewals slow in 2026"]
        self.assertTrue(is_dup("Reinsurance treaty renewals slow in 2026", existing))
        self.assertFalse(is_dup("A brand new headline about cats", existing))


class TestCleanText(unittest.TestCase):
    def test_strips_tags(self):
        self.assertEqual(clean_text("<em>保险</em> 新闻"), "保险 新闻")

    def test_collapses_whitespace(self):
        self.assertEqual(clean_text("保险   新闻\n\t测试"), "保险 新闻 测试")


class TestCategory(unittest.TestCase):
    def test_regulation(self):
        self.assertEqual(_category("监管办法出台 合规处罚", ""), "regulation")

    def test_product(self):
        self.assertEqual(_category("新品上线 产品发布", ""), "product")

    def test_claims(self):
        self.assertEqual(_category("理赔案例 纠纷判决", ""), "claims")

    def test_default_industry(self):
        self.assertEqual(_category("行业会议如期举行", ""), "industry")


class TestFetchEastmoney(unittest.TestCase):
    """中文源连通性（网络可用时返回条目；网络不可用时返回空列表，不报错）。"""

    def test_returns_list(self):
        items = fetch_eastmoney(per_kw=2)
        self.assertIsInstance(items, list)
        for it in items:
            self.assertIn("title", it)
            self.assertIn("url", it)
            self.assertIn("published_at", it)
            self.assertTrue(is_insurance_relevant(it["title"], it.get("summary", "")),
                            f"中文源返回非保险内容: {it['title']}")


class TestFetchIachina(unittest.TestCase):
    """中国保险行业协会官网源（权威一手源，独立于东方财富聚合）。"""

    def test_returns_list_and_schema(self):
        items = fetch_iachina(per_art=3)
        self.assertIsInstance(items, list)
        for it in items:
            self.assertIn("title", it)
            self.assertIn("url", it)
            self.assertIn("published_at", it)
            self.assertEqual(it["source_name"], "中国保险行业协会")
            self.assertEqual(it["source_type"], "行业协会")
            self.assertTrue(it["url"].startswith("https://www.iachina.cn/art/"),
                            f"URL 应为协会官网文章: {it['url']}")
            self.assertTrue(is_insurance_relevant(it["title"], it.get("summary", "")),
                            f"协会源返回非保险内容: {it['title']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
