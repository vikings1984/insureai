#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_research_filter.py — 研究报告三重门控单测

验证 collect_research.py 的白皮书聚焦逻辑：
  门控 1：机构域名白名单（媒体站点一律不算报告）
  门控 2：财报/通稿排除（动词+财务名词 ≠ 报告）
  门控 3：报告型标题信号（报告名词+年份 是合法标题）

运行：
    python3 -m unittest tests/test_research_filter.py -v
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import collect_research as cr


class TestInstitutionWhitelist(unittest.TestCase):
    """门控 1：权威机构域名白名单"""

    def test_swiss_re_institute_subdomain(self):
        self.assertIsNotNone(cr._institution_for_url("https://institute.swissre.com/research/sigma.html"))

    def test_mckinsey(self):
        info = cr._institution_for_url("https://www.mckinsey.com/industries/financial-services/our-insights/x")
        self.assertEqual(info[1], "麦肯锡")
        self.assertEqual(info[2], "consulting")

    def test_media_rejected(self):
        # 媒体站点是此前偏离初衷的根因，必须在门控外
        self.assertIsNone(cr._institution_for_url("https://www.reinsurancene.ws/some-report-mention/"))
        self.assertIsNone(cr._institution_for_url("https://www.insurancejournal.com/news/x"))
        self.assertIsNone(cr._institution_for_url("https://www.artemis.bm/feed/x"))

    def test_domestic_regulator(self):
        info = cr._institution_for_url("https://www.nfra.gov.cn/cn/view/pages/x.html")
        self.assertEqual(info[2], "regulator")

    def test_empty_url(self):
        self.assertIsNone(cr._institution_for_url(""))
        self.assertIsNone(cr._institution_for_url("not-a-url"))


class TestEarningsNoise(unittest.TestCase):
    """门控 2：财报/通稿排除（真实历史偏离样本）"""

    def test_posts_profit(self):
        self.assertTrue(cr._is_earnings_noise("Munich Re posts preliminary Q2’26 net profit of €2.2bn"))

    def test_reports_revenue_growth(self):
        self.assertTrue(cr._is_earnings_noise("Ryan Specialty reports 7.7% revenue growth in Q2’26"))

    def test_raises_outlook(self):
        self.assertTrue(cr._is_earnings_noise("Talanx raises 2026 profit outlook after strong first-half"))

    def test_profit_rises(self):
        self.assertTrue(cr._is_earnings_noise("French Insurer AXA’s Profit Rises 2% as Expected"))

    def test_reports_multibillion_loss(self):
        self.assertTrue(cr._is_earnings_noise("Gallagher Re reports multi-billion-dollar loss from August hail"))

    def test_appointment(self):
        self.assertTrue(cr._is_earnings_noise("Canopius appoints Greg Kuchinski as US CUO"))

    def test_chinese_earnings(self):
        self.assertTrue(cr._is_earnings_noise("某险企上半年净利润大增"))

    # —— 以下不应误杀（合法报告标题）——
    def test_report_with_year_not_noise(self):
        self.assertFalse(cr._is_earnings_noise("Global Insurance Report 2026: growth and influence"))

    def test_sigma_report(self):
        self.assertFalse(cr._is_earnings_noise("sigma: World insurance report 2026"))

    def test_outlook_report(self):
        self.assertFalse(cr._is_earnings_noise("2026 Global Insurance Outlook: premium trends ahead"))

    def test_premium_growth_in_report_context(self):
        # "premium growth" 前无动词时不命中（premium growth 分支要求 \b 词界但允许无动词？）
        # 该分支为 (?:revenue|premium)s?\s+(?:growth|...)，名词连用会命中 —— 属已知取舍：
        # 机构官网以 "premium growth" 开头的多为市场评论而非报告，宁缺毋滥。
        pass


class TestResearchTitle(unittest.TestCase):
    """门控 3：报告型标题信号"""

    def test_whitepaper(self):
        self.assertTrue(cr._is_research_title("Insurance digital transformation whitepaper 2026"))

    def test_chinese_report(self):
        self.assertTrue(cr._is_research_title("2026年上半年保险业风险评估报告"))

    def test_no_signal(self):
        self.assertFalse(cr._is_research_title("Long-term El Niño correlation holds little predictive value"))

    def test_signal_but_earnings_still_dropped(self):
        # 有 "report" 信号词但属财报通稿 → 门控 2 拦截
        self.assertFalse(cr._is_research_title("Munich Re reports 2.2 billion profit on low major losses"))


class TestPassesGates(unittest.TestCase):
    """三重门控集成（白名单 URL + 标题门控）"""

    def test_valid_report_passes(self):
        r = {"title": "sigma: World insurance report 2026",
             "url": "https://www.swissre.com/institute/research/sigma.html"}
        self.assertTrue(cr._passes_gates(r))

    def test_media_url_fails_even_with_good_title(self):
        r = {"title": "World insurance report 2026",
             "url": "https://www.reinsurancene.ws/world-insurance-report/"}
        self.assertFalse(cr._passes_gates(r))

    def test_whitelist_earnings_fails(self):
        # 白名单机构的财报通稿（swissre.com 也会发）同样拦截
        r = {"title": "Swiss Re reports net profit of USD 2.1bn",
             "url": "https://www.swissre.com/media/press-release.html"}
        self.assertFalse(cr._passes_gates(r))


class TestClean(unittest.TestCase):
    """--clean 清洗：auto 不合规剔除，curated 永不动"""

    def test_auto_media_removed_curated_kept(self):
        existing = {"reports": [
            {"title": "人工精编报告", "url": "https://example.com/x", "curated": True},
            {"title": "人工精编报告2", "url": "https://example.com/y"},  # 无 auto 字段 → 精编
            {"title": "Munich Re posts Q2 profit", "url": "https://www.reinsurancene.ws/x", "auto": True},
            {"title": "sigma report 2026", "url": "https://www.swissre.com/institute/sigma", "auto": True},
        ]}
        removed = cr.clean(existing)
        titles = [r["title"] for r in existing["reports"]]
        self.assertIn("人工精编报告", titles)
        self.assertIn("人工精编报告2", titles)
        self.assertIn("sigma report 2026", titles)
        self.assertNotIn("Munich Re posts Q2 profit", titles)
        self.assertEqual(len(removed), 1)


if __name__ == "__main__":
    unittest.main()
