#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_dedup.py — InsureAI 采集管道去重逻辑单测（零依赖，仅标准库）

验证 Levenshtein 相似度与 is_dup 判定在中英文标题下均符合预期阈值（默认 0.82）。

实测结论（字符级 Levenshtein 对长标题天然偏低）：
  - 轻微改写 / 同源重复（差异 1~2 字或 1 字符）→ 相似度 0.84~0.98 → 判重 ✓
  - 话题极相似但文字差异较大（长句）→ 相似度 ~0.71 → 不误删（保守但安全）✓

运行：
    python3 -m unittest tests/test_dedup.py -v
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import collect


class TestLevRatio(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(collect.lev_ratio("同一条保险新闻标题", "同一条保险新闻标题"), 1.0)

    def test_empty(self):
        self.assertEqual(collect.lev_ratio("", "非空"), 0.0)
        self.assertEqual(collect.lev_ratio("", ""), 1.0)

    def test_english(self):
        a = "insurance market update 2026"
        b = "insurance market report 2026"
        r = collect.lev_ratio(a, b)
        self.assertGreater(r, 0.7)
        self.assertLess(r, 1.0)


class TestIsDup(unittest.TestCase):
    def test_slight_chinese_rewrite_is_dup(self):
        # 仅"发布"→"推出"一字之差，相似度 0.895，应判重
        existing = ["太保寿险发布智能核保引擎时效缩至30秒"]
        candidate = "太保寿险推出智能核保引擎时效缩至30秒"
        self.assertTrue(collect.is_dup(candidate, existing, threshold=0.82))

    def test_slight_english_rewrite_is_dup(self):
        # 仅 hits→hit 一字符之差，相似度 0.975，应判重
        existing = ["Global insurance M&A hits record in 2026"]
        candidate = "Global insurance M&A hit record in 2026"
        self.assertTrue(collect.is_dup(candidate, existing, threshold=0.82))

    def test_news_series_dup(self):
        # 同一系列仅尾部追加（回顾 vs 回顾与展望），相似度 0.842，应判重
        existing = ["保险日报：2026上半年行业回顾"]
        candidate = "保险日报：2026上半年行业回顾与展望"
        self.assertTrue(collect.is_dup(candidate, existing, threshold=0.82))

    def test_topic_similar_but_text_diff_not_dup(self):
        # 话题极相似但文字差异较大（相似度 0.71），0.82 下不误删——保守但安全
        existing = ["国家金融监管总局发布AI大模型合规应用指引"]
        candidate = "金融监管总局发布保险AI大模型合规指引"
        self.assertFalse(collect.is_dup(candidate, existing, threshold=0.82))

    def test_different_chinese_not_dup(self):
        existing = ["太保寿险发布智能核保引擎时效缩至30秒"]
        candidate = "瑞士再保险发布全球巨灾损失报告达480亿美元"
        self.assertFalse(collect.is_dup(candidate, existing, threshold=0.82))

    def test_empty_existing(self):
        self.assertFalse(collect.is_dup("任意标题", [], threshold=0.82))


if __name__ == "__main__":
    unittest.main()
