"""P1-2 Source Health：_ingest 记账 + _merge_source_health 六项指标计算。

覆盖：
  - _ingest 在 dup / 噪声 / 非保险 / 正常收录 四种路径下正确累加 source_stats
  - _merge_source_health 计算 availability / freshness / parse_success /
    content_quality / duplicate_ratio / insurance_relevance 六项指标
  - fetch 失败 → availability=0；末轮无新条目 → 不做事负面判定
"""
import unittest

import collect


class TestIngestStats(unittest.TestCase):
    def _fresh(self):
        return [], [], {}

    def test_ingested_bump(self):
        existing_titles, collected, stats = self._fresh()
        collect._ingest(
            "某保险公司发布新条款", "某保险公司发布新条款，扩展保障范围",
            "http://x.com/1", "测试源", "媒体", 80, "2026-01-15T08:00:00Z",
            existing_titles, collected, stats=stats,
        )
        self.assertEqual(stats["测试源"]["ingested"], 1)
        self.assertEqual(len(collected), 1)

    def test_dup_bump(self):
        existing_titles, collected, stats = self._fresh()
        collect._ingest(
            "重复标题", "摘要", "http://x.com/2", "测试源", "媒体", 80,
            "2026-01-15T08:00:00Z", ["重复标题"], collected, stats=stats,
        )
        self.assertEqual(stats["测试源"]["dup"], 1)
        self.assertEqual(len(collected), 0)

    def test_noise_bump(self):
        existing_titles, collected, stats = self._fresh()
        collect._ingest(
            "午后保险板块异动拉升", "三大险企个股联袂上涨", "http://x.com/3",
            "测试源", "媒体", 80, "2026-01-15T08:00:00Z",
            existing_titles, collected, stats=stats,
        )
        self.assertEqual(stats["测试源"]["noise"], 1)
        self.assertEqual(len(collected), 0)

    def test_non_relevant_bump(self):
        existing_titles, collected, stats = self._fresh()
        collect._ingest(
            "今日天气晴转多云", "生活资讯早知道", "http://x.com/4",
            "测试源", "媒体", 80, "2026-01-15T08:00:00Z",
            existing_titles, collected, stats=stats, require_topic=True,
        )
        self.assertEqual(stats["测试源"]["non_relevant"], 1)
        self.assertEqual(len(collected), 0)

    def test_stats_none_is_noop(self):
        existing_titles, collected = [], []
        # stats=None 时不应抛错，也不应累加
        collect._ingest(
            "某保险公司发布新条款", "某保险公司发布新条款，扩展保障范围",
            "http://x.com/5", "测试源", "媒体", 80, "2026-01-15T08:00:00Z",
            existing_titles, collected,
        )
        self.assertEqual(len(collected), 1)


class TestMergeSourceHealth(unittest.TestCase):
    SIX = ("availability", "freshness", "parse_success", "content_quality",
           "duplicate_ratio", "insurance_relevance")

    def _base(self):
        data = {"news": [], "source_health": {}}
        fetched = {"RSS源A": {"count": 5, "ok": True}}
        news = [
            {"source_name": "RSS源A", "published_at": "2026-01-15T08:00:00Z", "ai_score": 90},
            {"source_name": "RSS源A", "published_at": "2026-01-10T08:00:00Z", "ai_score": 70},
        ]
        source_stats = {"RSS源A": {"ingested": 2, "dup": 1, "noise": 0, "non_relevant": 0}}
        return data, fetched, news, source_stats

    def test_six_metrics_present(self):
        data, fetched, news, source_stats = self._base()
        collect._merge_source_health(data, fetched, news, source_stats)
        rec = data["source_health"]["RSS源A"]
        for k in self.SIX:
            self.assertIn(k, rec)
        # 向后兼容字段保留
        self.assertIn("count", rec)
        self.assertIn("ok", rec)

    def test_metrics_values(self):
        data, fetched, news, source_stats = self._base()
        collect._merge_source_health(data, fetched, news, source_stats)
        rec = data["source_health"]["RSS源A"]
        self.assertEqual(rec["availability"], 1.0)
        # parse_success = ingested/attempted = 2/(2+1) = 2/3
        self.assertAlmostEqual(rec["parse_success"], 2 / 3, places=3)
        # duplicate_ratio = dup/attempted = 1/3
        self.assertAlmostEqual(rec["duplicate_ratio"], 1 / 3, places=3)
        # insurance_relevance = ingested/(ingested+non_relevant) = 1.0
        self.assertEqual(rec["insurance_relevance"], 1.0)
        # content_quality = (90+70)/2/100 = 0.8
        self.assertAlmostEqual(rec["content_quality"], 0.8, places=3)
        # freshness 为 [0,1] 之间的浮点
        self.assertGreaterEqual(rec["freshness"], 0.0)
        self.assertLessEqual(rec["freshness"], 1.0)
        # count = merged 中该源条数
        self.assertEqual(rec["count"], 2)

    def test_fetch_failure_availability_zero(self):
        data = {"news": [], "source_health": {}}
        fetched = {"坏源": {"count": 0, "ok": False}}
        collect._merge_source_health(data, fetched, [], {})
        rec = data["source_health"]["坏源"]
        self.assertEqual(rec["availability"], 0.0)
        self.assertEqual(rec["ok"], False)

    def test_no_activity_source_no_negative(self):
        # 末轮无新条目但有存量：parse_success / insurance_relevance 不做事负面判定
        data = {"news": [], "source_health": {}}
        news = [{"source_name": "存量源", "published_at": "2026-01-01T08:00:00Z", "ai_score": 60}]
        collect._merge_source_health(data, {}, news, {})
        rec = data["source_health"]["存量源"]
        self.assertEqual(rec["parse_success"], 1.0)
        self.assertEqual(rec["insurance_relevance"], 1.0)
        self.assertAlmostEqual(rec["content_quality"], 0.6, places=3)

    def test_backward_compat_old_signature(self):
        # 旧调用（无 source_stats）不应报错
        data = {"news": [], "source_health": {}}
        news = [{"source_name": "X", "published_at": "2026-01-01T08:00:00Z", "ai_score": 50}]
        collect._merge_source_health(data, {"X": {"count": 1, "ok": True}}, news)
        self.assertIn("X", data["source_health"])


if __name__ == "__main__":
    unittest.main()
