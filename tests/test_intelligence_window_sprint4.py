"""Sprint 4 (方案C) 回归：_within_window 96h→720h + 超时软门 0.70。

锁住 false_split 修复（P1-4.1 收尾）：持续性事件（合作 / 会议 / 系列 webinar）
跨周报道应合并；不同事件同主体不误合；超时(>720h)且低相似度(<0.70)不合并。
fixture 复用真实三对的标题 / 标签 / 时间间隔，hermetic 不依赖 data.json。
"""
import unittest
import sys

sys.path.insert(0, ".")

from intelligence import build


def _art(i, title_zh, title, tags, pub):
    return {
        "id": i,
        "title_zh": title_zh,
        "title": title,
        "tags": tags,
        "published_at": pub,
        "source_name": f"src{i}",
        "source_url": f"https://x.com/{i}",
        "research_topic": "capital_reinsurance",
        "ai_score": 80,
        "summary": title_zh,
    }


def _event_count(news):
    return len(build({"news": news})["events"])


class Sprint4WindowRegressionTest(unittest.TestCase):
    def test_same_deal_across_15d_merges(self):
        # swiss re / SAS：间隔 358h（<720h），sim 0.725 → 合并
        news = [
            _art(1, "瑞士再保险和 SAS 合作通过人工智能驱动的风险情报为保险公司提供支持",
                 "Swiss Re and SAS partner to support insurers with AI-driven risk",
                 "swiss re,sas,ai-driven", "2026-07-29T15:00:52Z"),
            _art(2, "瑞士再保险和 SAS 合作通过人工智能驱动的风险情报增强保险公司的抵御能力",
                 "Swiss Re and SAS partner to strengthen insurers resilience through AI",
                 "swiss re,sas,ai-driven", "2026-08-13T13:30:52Z"),
        ]
        self.assertEqual(_event_count(news), 1)

    def test_meeting_series_across_16d_merges(self):
        # artemis london：间隔 386h（<720h），sim 0.533 → 合并
        news = [
            _art(3, "2026 年伦敦阿尔忒弥斯：目前有 120 多个组织参加。你能见到谁？",
                 "Artemis London 2026: 120+ organisations now attending. Who can you meet?",
                 "artemis london", "2026-08-04T07:45:31Z"),
            _art(4, "2026 年伦敦阿尔忒弥斯：已有 90 多个组织注册。你能见到谁？",
                 "Artemis London 2026: Over 90 organisations already registered. Who can you meet?",
                 "artemis london", "2026-08-20T10:30:22Z"),
        ]
        self.assertEqual(_event_count(news), 1)

    def test_long_gap_low_similarity_stays_split(self):
        # risky future：间隔 1160h（>720h），sim 0.333（<0.70）→ 不合并
        news = [
            _art(5, "注册： 8月26日保险业务流程外包和咨询风险未来人工智能工具 Demo Day",
                 "Register: Risky Future AI Tools for Insurance BPO & Consulting Demo Day",
                 "register,risky future ai tools", "2026-07-07T05:38:21Z"),
            _art(6, "注册：用于承保 7 月 8 日 Demo Day 的风险未来人工智能工具",
                 "Register: Risky Future AI Tools for Underwriting Demo Day",
                 "register,risky future ai tools", "2026-08-24T14:01:53Z"),
        ]
        self.assertEqual(_event_count(news), 2)

    def test_same_company_diff_event_no_false_merge(self):
        # Munich Re 财报 vs 任命 CFO：同主体不同事件，间隔 240h（<720h），sim 低 → 不误合
        news = [
            _art(7, "慕尼黑再保险公布第二季度财报，净利润同比增长",
                 "Munich Re reports Q2 results, net income up", "munich re,earnings", "2026-08-01T10:00:00Z"),
            _art(8, "慕尼黑再保险任命新首席财务官",
                 "Munich Re appoints new CFO", "munich re,personnel", "2026-08-11T10:00:00Z"),
        ]
        self.assertEqual(_event_count(news), 2)


if __name__ == "__main__":
    unittest.main()
