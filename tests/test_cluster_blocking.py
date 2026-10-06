"""P0-5 Event Candidate Blocking：聚类候选召回正确性回归。

验证 _cluster 的「倒排索引候选召回 + 精排」实现：
  - 共享实体的多条报道被合并（候选召回经 entity 索引命中代表）
  - 无共享信号的独立报道保持分群（不被误合）
  - 相同输入产出稳定分组（确定性）
  - 空输入安全返回空 dict
等价性（与旧 O(n²) 完全一致）由 benchmark.py 的 event / split 安全门守卫
（false_merge_rate==0.0 && false_split_rate==0.0）。
"""
import unittest

import intelligence


def _item(i, title, tags, url, pub):
    return {
        "id": i,
        "title": title,
        "summary": title,
        "tags": tags,
        "source_url": url,
        "published_at": pub,
        "research_topic": "product_innovation",
    }


class TestClusterBlocking(unittest.TestCase):
    def test_entity_recall_merges(self):
        # 两条共享「收购标的」子实体（超出 anchor 公司）的报道应合并为 1 个事件
        # （候选召回经 entity 索引命中代表；anchor_match + same_type + specific_shared 触发 accept）
        items = [
            _item(1, "Acme 保险 宣布 收购 标的 Y 集团", "acme保险,标的Y集团", "https://a.com/1", "2026-08-01T10:00:00Z"),
            _item(2, "Acme 保险 完成 对 标的 Y 集团 的 并购", "acme保险,标的Y集团", "https://b.com/2", "2026-08-02T10:00:00Z"),
            _item(3, "标的 Y 集团 回应 收购 事宜", "acme保险,标的Y集团", "https://c.com/3", "2026-08-03T10:00:00Z"),
        ]
        groups = intelligence._cluster(items)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(list(groups.values())[0]), 3)

    def test_separation_no_shared_signal(self):
        # 三条互不共享实体/标题 token 的独立报道应保持分群
        items = [
            _item(1, "Foo 公司 发布 年报", "foo公司", "https://a.com/1", "2026-08-01T10:00:00Z"),
            _item(2, "Bar 集团 完成 增资", "bar集团", "https://b.com/2", "2026-08-02T10:00:00Z"),
            _item(3, "Baz 保险 换帅", "baz保险", "https://c.com/3", "2026-08-03T10:00:00Z"),
        ]
        groups = intelligence._cluster(items)
        self.assertEqual(len(groups), 3)

    def test_deterministic(self):
        items = [
            _item(1, "Acme 保险 上调 重疾 理赔 额度", "acme保险", "https://a.com/1", "2026-08-01T10:00:00Z"),
            _item(2, "Acme 保险 推出 新款 医疗 险 产品", "acme保险", "https://b.com/2", "2026-08-02T10:00:00Z"),
            _item(3, "Foo 公司 发布 年报", "foo公司", "https://c.com/3", "2026-08-03T10:00:00Z"),
        ]
        g1 = intelligence._cluster(items)
        g2 = intelligence._cluster(items)
        self.assertEqual(list(g1.keys()), list(g2.keys()))
        self.assertEqual(
            [len(v) for v in g1.values()], [len(v) for v in g2.values()]
        )

    def test_empty_input(self):
        self.assertEqual(intelligence._cluster([]), {})


if __name__ == "__main__":
    unittest.main()
