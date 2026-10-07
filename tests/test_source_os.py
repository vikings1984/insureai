#!/usr/bin/python3
"""P1-1 Source OS 单元测试：区分「未测量」与「不健康」。

第七阶段实测发现：部分源在 data.json 里只有 `{count, ok}`——availability/freshness
**键根本不存在**。此前被 `_f(None)→0.0` 归一化为"低可用/陈旧"，导致
**指标缺失被误报为源不健康**（含金融监管总局 / 财政部 / 银保监会等官方源）。

本测试锁定：
- 键缺失 → status=unmeasured / action=needs_measurement，**不得**判为不健康；
- 指标齐备且不达标 → 才是 measured 的 unhealthy/content_weak；
- 权威源受保护（action=protect），即便内容弱；
- crawl故障（有内容但抓不到）与 content 弱是**两个不同处置**。
"""
from __future__ import annotations

import unittest

import source_os


def _full(avail=1.0, fresh=1.0, quality=1.0, cover=1.0, count=3, dup=0.0, parse=1.0):
    return {"count": count, "availability": avail, "freshness": fresh,
            "content_quality": quality, "insurance_relevance": cover,
            "duplicate_ratio": dup, "parse_success": parse}


def _sparse(count=1):
    """只有 count/ok —— 指标从未计算。"""
    return {"count": count, "ok": True}


class TestSourceOS(unittest.TestCase):
    def test_unmeasured_not_judged_unhealthy(self):
        s = source_os.classify_source("某源", _sparse())
        self.assertEqual(s["status"], "unmeasured")
        self.assertEqual(s["suggested_action"], "needs_measurement")
        self.assertFalse(s["connectivity"]["measured"])

    def test_authority_unmeasured_also_not_degraded(self):
        s = source_os.classify_source("金融监管总局", _sparse())
        self.assertEqual(s["suggested_action"], "needs_measurement")

    def test_measured_healthy(self):
        s = source_os.classify_source("某源", _full())
        self.assertEqual(s["status"], "measured")
        self.assertEqual(s["suggested_action"], "keep")

    def test_authority_protected_even_if_content_weak(self):
        weak = _full(quality=0.1, cover=0.1, fresh=0.0)
        s = source_os.classify_source("最高人民法院", weak)
        self.assertEqual(s["suggested_action"], "protect")

    def test_content_weak_content_measure(self):
        s = source_os.classify_source("某源", _full(quality=0.1, cover=0.1))
        self.assertEqual(s["suggested_action"], "suggest_downweight")
        self.assertIn("内容质量低", s["reason"])

    def test_crawl_incident_is_not_downweight(self):
        # 有内容但抓不到（avail 与 parse 双低）→ 标crawl_incident，处置是修crawler而非降权
        s = source_os.classify_source("某源", _full(avail=0.0, fresh=1.0, count=5, parse=0.0))
        self.assertTrue(s["connectivity"]["crawl_incident"])
        self.assertNotEqual(s["suggested_action"], "suggest_downweight")
        self.assertIn("crawler", s["connectivity"]["note"])

    def test_build_separates_unmeasured(self):
        data = {"source_health": {"甲": _full(), "乙": _sparse()}}
        doc = source_os.build(data)
        self.assertEqual(doc["meta"]["source_count"], 2)
        self.assertEqual(doc["meta"]["measured_count"], 1)
        self.assertEqual(doc["meta"]["unmeasured_count"], 1)
        self.assertEqual(doc["unmeasured_sources"], ["乙"])
        # 缺口须进 open_questions
        gaps = [q for q in doc["open_questions"] if q["dimension"] == "未测量信源"]
        self.assertEqual(gaps[0]["status"], "data_gap")

    def test_empty_graceful(self):
        doc = source_os.build({"source_health": {}})
        self.assertFalse(doc["available"])


if __name__ == "__main__":
    unittest.main()