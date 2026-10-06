#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2 §7.1 Source Group：cross_checked 必须基于独立信源组，而不是 URL/域名数量。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import claims
import source_registry
from source_registry import (
    independent_source_groups,
    registrable_domain,
    source_group,
    source_group_ids,
)


def _item(id_, title, source, domain, published_at="2026-08-21T10:00:00+00:00", **extra):
    row = {
        "id": id_,
        "title": title,
        "tags": "Munich Re,At-Bay",
        "source_name": source,
        "source_url": f"https://{domain}/example",
        "published_at": published_at,
        "date_verified": True,
    }
    row.update(extra)
    return row


class TestRegistrableDomain(unittest.TestCase):
    def test_strips_www_and_subdomain(self):
        self.assertEqual(registrable_domain("https://www.reuters.com/a/b"), "reuters.com")
        self.assertEqual(registrable_domain("reuters.com"), "reuters.com")

    def test_multipart_suffix_keeps_three_labels(self):
        # 只取两段会变成 com.cn —— 多段后缀必须保留三段
        self.assertEqual(registrable_domain("https://news.sina.com.cn/x"), "sina.com.cn")
        self.assertEqual(registrable_domain("https://finance.sina.com.cn/x"), "sina.com.cn")
        self.assertEqual(registrable_domain("https://www.bbc.co.uk/news"), "bbc.co.uk")

    def test_port_userinfo_and_case_are_normalized(self):
        self.assertEqual(registrable_domain("https://user@WWW.Example.COM:8443/a"), "example.com")

    def test_empty_input(self):
        self.assertEqual(registrable_domain(""), "")
        self.assertEqual(registrable_domain(None), "")


class TestSourceGroup(unittest.TestCase):
    def test_same_portal_channels_collapse_to_one_group(self):
        a = _item("1", "t", "新浪财经", "finance.sina.com.cn")
        b = _item("2", "t", "新浪新闻", "news.sina.com.cn")
        self.assertEqual(source_group(a), source_group(b))
        self.assertEqual(independent_source_groups([a, b]), 1)

    def test_www_and_bare_domain_collapse(self):
        a = _item("1", "t", "X", "x.com")
        b = _item("2", "t", "X", "www.x.com")
        self.assertEqual(source_group(a), source_group(b))

    def test_unknown_domains_are_not_merged(self):
        # 未知来源必须"互不合并"，宁可少判 cross_checked 也不误判
        a = _item("1", "t", "A", "alpha-unknown.io")
        b = _item("2", "t", "B", "beta-unknown.io")
        self.assertEqual(independent_source_groups([a, b]), 2)

    def test_explicit_source_group_is_respected(self):
        row = _item("1", "t", "公众号转载", "mp.weixin.qq.com", source_group="grp:xinhua")
        self.assertEqual(source_group(row), "grp:xinhua")

    def test_group_ids_sorted_and_deduplicated(self):
        rows = [
            _item("1", "t", "a", "news.sina.com.cn"),
            _item("2", "t", "b", "finance.sina.com.cn"),
            _item("3", "t", "c", "www.reuters.com"),
        ]
        # reuters 在归并表里，故是 grp:reuters；未知域才是 dom:<eTLD+1>
        self.assertEqual(source_group_ids(rows), ["grp:reuters", "grp:sina"])


class TestCrossCheckedRequiresIndependentGroups(unittest.TestCase):
    """这是 §7.1 的核心回归：单一信源的转载/多频道不得被标成已交叉验证。"""

    def _claim(self, items, claim_type="transaction_amount"):
        event = {"event_id": "evt_1", "title": "Munich Re 收购 At-Bay", "event_type": "acquisition"}
        result = claims.build_claims(items, event)
        return next(c for c in result["claims"] if c["claim_type"] == claim_type)

    def test_two_channels_of_one_portal_is_single_source_not_cross_checked(self):
        items = [
            _item("1", "Munich Re to acquire At-Bay for $575 million", "新浪财经", "finance.sina.com.cn"),
            _item("2", "Munich Re agrees to buy At-Bay for $575 million", "新浪新闻", "news.sina.com.cn", "2026-08-21T11:00:00+00:00"),
        ]
        claim = self._claim(items)
        # 域名仍是 2（兼容展示），但信源组只有 1 → 不能 cross_checked
        self.assertEqual(claim["independent_domains"], 2)
        self.assertEqual(claim["independent_source_groups"], 1)
        self.assertEqual(claim["verification_status"], "single_source")
        self.assertLessEqual(claim["confidence"], 65)

    def test_www_duplicate_of_one_domain_is_single_source(self):
        items = [
            _item("1", "Munich Re to acquire At-Bay for $575 million", "Reuters", "www.reuters.com"),
            _item("2", "Munich Re agrees to buy At-Bay for $575 million", "Reuters", "reuters.com", "2026-08-21T11:00:00+00:00"),
        ]
        claim = self._claim(items)
        self.assertEqual(claim["independent_source_groups"], 1)
        self.assertEqual(claim["verification_status"], "single_source")

    def test_genuinely_independent_sources_still_cross_checked(self):
        items = [
            _item("1", "Munich Re to acquire At-Bay for $575 million", "Reuters", "www.reuters.com"),
            _item("2", "Munich Re agrees to buy At-Bay for $575 million", "Insurance Journal", "www.insurancejournal.com", "2026-08-21T11:00:00+00:00"),
        ]
        claim = self._claim(items)
        self.assertEqual(claim["independent_source_groups"], 2)
        self.assertEqual(claim["verification_status"], "cross_checked")

    def test_syndicated_third_copy_does_not_create_independence(self):
        """同一集团三条 URL（含转载平台）依旧只有一个独立信源组。"""
        items = [
            _item("1", "Munich Re to acquire At-Bay for $575 million", "腾讯新闻", "news.qq.com"),
            _item("2", "Munich Re agrees to buy At-Bay for $575 million", "微信", "mp.weixin.qq.com", "2026-08-21T11:00:00+00:00"),
            _item("3", "Munich Re 拟收购 At-Bay", "腾讯财经", "finance.qq.com", "2026-08-21T12:00:00+00:00"),
        ]
        claim = self._claim(items)
        self.assertEqual(claim["independent_source_groups"], 1)
        self.assertEqual(claim["verification_status"], "single_source")


class TestExternalRegistryLoading(unittest.TestCase):
    """V2 P1-1 回归：归并表已外置到 sources/registry.yaml，模块启动时必须正确载入。"""

    def test_registry_yaml_is_loaded_at_import(self):
        # 归并表来自 YAML，而非硬编码字面量（非空即说明从磁盘载入成功）
        self.assertGreater(len(source_registry.SOURCE_GROUPS), 0)
        self.assertGreater(len(source_registry.MULTIPART_SUFFIXES), 0)

    def test_known_domains_resolve_to_yaml_groups(self):
        # 这些域都定义在 sources/registry.yaml 的 sources[*].domains 里
        self.assertEqual(source_registry.SOURCE_GROUPS["sina.com.cn"], "grp:sina")
        self.assertEqual(source_registry.SOURCE_GROUPS["reuters.com"], "grp:reuters")
        self.assertEqual(source_registry.SOURCE_GROUPS["eastmoney.com"], "grp:eastmoney")

    def test_multipart_suffix_from_yaml_includes_china_multisegment(self):
        # 多段后缀必须含 com.cn / co.uk，否则 registrable_domain 会截断成两段
        self.assertIn("com.cn", source_registry.MULTIPART_SUFFIXES)
        self.assertIn("co.uk", source_registry.MULTIPART_SUFFIXES)

    def test_source_group_func_uses_yaml_registry(self):
        # 经 source_group() 走归并表，确认 YAML 来源被归到正确组
        a = _item("1", "t", "新浪财经", "finance.sina.com.cn")
        b = _item("2", "t", "路透", "www.reuters.com")
        self.assertEqual(source_group(a), "grp:sina")
        self.assertEqual(source_group(b), "grp:reuters")

    def test_syndication_platforms_loaded_from_yaml(self):
        # SYNDICATION_PLATFORMS 是原死代码，随外置忠实保留；至少含一个组
        self.assertIn("grp:sohu", source_registry.SYNDICATION_PLATFORMS)


if __name__ == "__main__":
    unittest.main()
