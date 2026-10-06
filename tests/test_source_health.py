"""P1-2 Source Health：_ingest 记账 + _merge_source_health 六项指标计算。

覆盖：
  - _ingest 在 dup / 噪声 / 非保险 / 正常收录 四种路径下正确累加 source_stats
  - _merge_source_health 计算 availability / freshness / parse_success /
    content_quality / duplicate_ratio / insurance_relevance 六项指标
  - fetch 失败 → availability=0；末轮无新条目 → 不做事负面判定
  - freshness 衰减窗口按信源 update_freq 分档（声明 → 观测 → 默认），且只放宽不收紧
"""
import unittest
from datetime import datetime, timedelta

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


class TestObservedPublishGap(unittest.TestCase):
    """观测层：从存量发布日估计该信源的典型更新间隔。"""

    def test_sample_insufficient_returns_none(self):
        self.assertIsNone(collect.observed_publish_gap_days(["2026-01-01", "2026-01-08"]))

    def test_empty_returns_none(self):
        self.assertIsNone(collect.observed_publish_gap_days([]))
        self.assertIsNone(collect.observed_publish_gap_days(None))

    def test_median_of_gaps(self):
        days = ["2026-01-01", "2026-01-08", "2026-01-15", "2026-01-22"]
        self.assertEqual(collect.observed_publish_gap_days(days), 7.0)

    def test_duplicate_days_collapsed(self):
        """同一天多条不应算作 0 天间隔，否则会低估真实节奏。"""
        days = ["2026-01-01", "2026-01-01", "2026-01-01",
                "2026-01-08", "2026-01-15"]
        self.assertEqual(collect.observed_publish_gap_days(days), 7.0)

    def test_all_same_day_returns_none(self):
        self.assertIsNone(collect.observed_publish_gap_days(["2026-01-01"] * 5))

    def test_invalid_days_ignored(self):
        days = ["2026-01-01", "", None, "garbage", "2026-01-08", "2026-01-15"]
        self.assertEqual(collect.observed_publish_gap_days(days), 7.0)

    def test_uses_recent_dates_only(self):
        """很久以前是日更、最近变成月更 —— 应按最近节奏而非历史平均。"""
        old = [f"2020-01-{d:02d}" for d in range(1, 11)]          # 日更
        recent = ["2026-01-01", "2026-02-01", "2026-03-01"]        # 月更
        # 2020→2026 的断档被识别为停更，只按 2026 这一段估计：31 / 28 → 中位 29.5
        self.assertEqual(collect.observed_publish_gap_days(old + recent), 29.5)

    def test_long_break_shortens_sample_to_none(self):
        """断档之后只剩 2 个发布日 → 样本不足，回退默认窗口而非硬算。"""
        days = ["2020-01-01", "2020-01-02", "2026-01-01", "2026-02-01"]
        self.assertIsNone(collect.observed_publish_gap_days(days))


class TestFreshnessWindow(unittest.TestCase):
    """窗口分档：声明 → 观测 → 默认，取最大值，只放宽不收紧。"""

    def test_default_window(self):
        self.assertEqual(collect.freshness_window_days(), collect.DEFAULT_FRESHNESS_WINDOW_DAYS)
        self.assertEqual(collect.freshness_window_days("不定期"), collect.DEFAULT_FRESHNESS_WINDOW_DAYS)

    def test_declared_monthly_and_quarterly_are_wider(self):
        self.assertEqual(collect.freshness_window_days("每月"), 60)
        self.assertEqual(collect.freshness_window_days("每季"), 120)

    def test_declared_daily_not_narrower_than_default(self):
        """硬约束：不得因分档把任何信源的窗口压到默认以下。"""
        self.assertEqual(collect.freshness_window_days("每日"), collect.DEFAULT_FRESHNESS_WINDOW_DAYS)
        self.assertEqual(collect.freshness_window_days("每周"), collect.DEFAULT_FRESHNESS_WINDOW_DAYS)

    def test_observed_gap_widens_window(self):
        # 中位间隔 20 天 × 2 = 40
        self.assertEqual(collect.freshness_window_days("不定期", 20.0), 40)

    def test_observed_window_clamped_to_max(self):
        # 中位间隔 365 天 × 2 = 730 → clamp 到 180
        self.assertEqual(collect.freshness_window_days(None, 365.0), collect.OBSERVED_WINDOW_MAX_DAYS)

    def test_observed_window_never_below_default(self):
        # 中位间隔 1 天 × 2 = 2 → 下限抬回默认，绝不收紧
        self.assertEqual(collect.freshness_window_days(None, 1.0), collect.DEFAULT_FRESHNESS_WINDOW_DAYS)

    def test_declared_and_observed_take_max(self):
        # 声明每月 60，观测给出 90 → 取 90
        self.assertEqual(collect.freshness_window_days("每月", 45.0), 90)

    def test_every_declared_window_is_not_narrower_than_default(self):
        """不变量：分档表里的每个窗口都必须 >= 默认，保证零回归。"""
        for freq, window in collect.FRESHNESS_WINDOW_BY_FREQ.items():
            with self.subTest(freq=freq):
                self.assertGreaterEqual(window, collect.DEFAULT_FRESHNESS_WINDOW_DAYS)


class TestFreshnessUsesDeclaredFreq(unittest.TestCase):
    """_merge_source_health 必须真正读取 sources[].update_freq 来分档。"""

    def _run(self, update_freq, days_ago, extra_days=()):
        # 用当天零点作基准，保证 (now - published).days 精确等于 days_ago
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        published = [(midnight - timedelta(days=days_ago)).strftime("%Y-%m-%dT00:00:00Z")]
        published += list(extra_days)
        data = {
            "news": [],
            "source_health": {},
            "sources": [{"name": "低频权威源", "type": "监管", "update_freq": update_freq}],
        }
        news = [{"source_name": "低频权威源", "published_at": p, "ai_score": 80} for p in published]
        collect._merge_source_health(data, {}, news, {})
        return data["source_health"]["低频权威源"]

    def test_monthly_source_not_flagged_as_stale(self):
        """回归用例：每月更新、45 天前发过稿的源，旧口径 30 天窗口会判 0，分档后应为正。"""
        rec = self._run("每月", 45)
        self.assertEqual(rec["freshness_window"], 60)
        self.assertAlmostEqual(rec["freshness"], 1.0 - 45 / 60.0, places=3)
        self.assertGreater(rec["freshness"], 0.2)

    def test_unknown_freq_uses_default(self):
        rec = self._run("不定期", 10)
        self.assertEqual(rec["freshness_window"], collect.DEFAULT_FRESHNESS_WINDOW_DAYS)

    def test_window_recorded_for_troubleshooting(self):
        rec = self._run("每季", 30)
        self.assertEqual(rec["freshness_window"], 120)
        self.assertAlmostEqual(rec["freshness"], 1.0 - 30 / 120.0, places=3)

    def test_no_regression_for_any_window(self):
        """不变量：任何分档下 freshness 都 >= 旧口径（30 天窗口）的取值。"""
        for freq in (None, "不定期", "每日", "每周", "每月", "每季"):
            for days_ago in (0, 5, 25, 45, 100):
                with self.subTest(freq=freq, days=days_ago):
                    rec = self._run(freq, days_ago)
                    legacy = max(0.0, 1.0 - days_ago / 30.0)
                    # 容差 1e-4：产物里 freshness 保留 4 位小数，round 误差上限 5e-5
                    self.assertGreaterEqual(rec["freshness"] + 1e-4, legacy)


if __name__ == "__main__":
    unittest.main()
