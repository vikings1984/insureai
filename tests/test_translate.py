#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_translate.py — 免费翻译模块单测（离线，无网络请求）

覆盖：语言检测 / 双端点响应解析 / 译文有效性校验 / 缓存读写 / 批量预算控制。

运行：
    python3 -m unittest tests/test_translate.py -v
"""
import sys
import os
import json
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import translate


class TestIsEnglish(unittest.TestCase):
    """英文启发式检测"""

    def test_english_title(self):
        self.assertTrue(translate.is_english("Munich Re posts preliminary Q2 net profit"))

    def test_chinese_title(self):
        self.assertFalse(translate.is_english("20省份暴雨洪涝等灾害保险赔付52.1亿元"))

    def test_mixed_mostly_chinese(self):
        self.assertFalse(translate.is_english("保险业2026年AI应用白皮书发布"))

    def test_short_text(self):
        self.assertFalse(translate.is_english("hi"))

    def test_empty(self):
        self.assertFalse(translate.is_english(""))


class TestParseGtx(unittest.TestCase):
    """Google gtx 嵌套数组响应解析"""

    def test_segments_join(self):
        # 真实 gtx 响应：所有译文片段都在 data[0] 的同一列表里
        data = [[["慕尼黑再保险", "Munich Re", None, None], ["公布", " posts", None, None]], [None]]
        self.assertEqual(translate._parse_gtx(data), "慕尼黑再保险公布")

    def test_empty(self):
        self.assertEqual(translate._parse_gtx([]), "")
        self.assertEqual(translate._parse_gtx([[]]), "")


class TestParseMymemory(unittest.TestCase):
    """MyMemory 响应解析"""

    def test_normal(self):
        data = {"responseData": {"translatedText": "瑞再研究院sigma报告"}}
        self.assertEqual(translate._parse_mymemory(data), "瑞再研究院sigma报告")

    def test_quota_warning_not_translation(self):
        data = {"responseData": {"translatedText": "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY"}}
        self.assertEqual(translate._parse_mymemory(data), "")

    def test_invalid_payload(self):
        self.assertEqual(translate._parse_mymemory("not-a-dict"), "")
        self.assertEqual(translate._parse_mymemory({}), "")


class TestLooksTranslated(unittest.TestCase):
    """译文有效性校验（防端点返回错误说明或原样英文）"""

    def test_valid_chinese(self):
        self.assertTrue(translate._looks_translated("Munich Re posts profit", "慕尼黑再保险公布利润"))

    def test_echo_rejected(self):
        self.assertFalse(translate._looks_translated("Munich Re posts profit", "Munich Re posts profit"))

    def test_empty_rejected(self):
        self.assertFalse(translate._looks_translated("some title", ""))

    def test_english_response_rejected(self):
        # 端点偶发返回英文错误说明，中文占比过低须拒绝
        self.assertFalse(translate._looks_translated("Insurance report", "Translation service error occurred"))


class TestCache(unittest.TestCase):
    """缓存持久化（临时目录）"""

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "cache.json")
            translate.save_cache({"k1": "译文一"}, p)
            self.assertEqual(translate.load_cache(p), {"k1": "译文一"})

    def test_load_missing_file(self):
        self.assertEqual(translate.load_cache("/nonexistent/path.json"), {})

    def test_load_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not json")
            path = f.name
        try:
            self.assertEqual(translate.load_cache(path), {})
        finally:
            os.unlink(path)


class TestTranslateNews(unittest.TestCase):
    """批量翻译：预算控制 + 缓存命中不计预算"""

    def test_budget_capped(self):
        news = [{"title": f"Munich Re insurance report volume {i}"} for i in range(10)]
        # 预填缓存：所有条目的译文都在缓存 → 0 次 API 调用即完成
        cache = {translate.hashlib.sha1(n["title"].encode()).hexdigest(): "缓存译文"
                 for n in news}
        n = translate.translate_news(news, budget=3, cache=cache, verbose=False)
        self.assertEqual(n, 3)          # 预算 3 → 只翻译前 3 条
        self.assertEqual(news[0]["title_zh"], "缓存译文")
        self.assertNotIn("title_zh", news[5])

    def test_all_from_cache_within_budget(self):
        news = [{"title": "Cached insurance report title"}]
        key = translate.hashlib.sha1(news[0]["title"].encode()).hexdigest()
        n = translate.translate_news(news, budget=1, cache={key: "命中译文"}, verbose=False)
        self.assertEqual(n, 1)
        self.assertEqual(news[0]["title_zh"], "命中译文")

    def test_chinese_skipped(self):
        news = [{"title": "中文保险新闻标题无需翻译"}]
        cache = {}
        n = translate.translate_news(news, budget=5, cache=cache, verbose=False)
        self.assertEqual(n, 0)
        self.assertNotIn("title_zh", news[0])

    def test_failure_leaves_item_untouched(self):
        # 两端点都不可用（网络隔离）→ 条目保持原样，不抛异常
        news = [{"title": "Munich Re insurance report for 2026"}]
        orig_gtx = translate._gtx_translate
        orig_mm = translate._mymemory_translate
        translate._gtx_translate = lambda t: (_ for _ in ()).throw(OSError("net down"))
        translate._mymemory_translate = lambda t: (_ for _ in ()).throw(OSError("net down"))
        try:
            n = translate.translate_news(news, budget=1, cache={}, verbose=False)
        finally:
            translate._gtx_translate = orig_gtx
            translate._mymemory_translate = orig_mm
        self.assertEqual(n, 0)
        self.assertNotIn("title_zh", news[0])


if __name__ == "__main__":
    unittest.main()
