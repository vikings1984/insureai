#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Source authority tiers for claim confidence weighting.

Tier 1: 监管机构/政府/交易所/公司公告/法院等一手来源
Tier 2: Reuters/Bloomberg/FT/WSJ 等国际通讯社与财经媒体
Tier 3: 行业媒体/专业研究机构（默认层）
Tier 4: 博客/转载/聚合/社交媒体

层级语义（authority / trust_weight / label）在 contract.SOURCE_TIERS 单一定义，
本模块只负责 domain/source_type -> tier 的映射。
"""
from __future__ import annotations

from urllib.parse import urlparse

from contract import SOURCE_TIERS

TIER_LABELS = {tier: cfg["label"] for tier, cfg in SOURCE_TIERS.items()}
TIER_AUTHORITY = {tier: cfg["authority"] for tier, cfg in SOURCE_TIERS.items()}
TIER_TRUST_WEIGHTS = {tier: cfg["trust_weight"] for tier, cfg in SOURCE_TIERS.items()}

TIER1_DOMAINS = (
    "gov.cn", "gov", "sec.gov", "fca.org.uk", "eiopa.eu", "naic.org",
    "bankofengland.co.uk", "bis.org", "iahsa.org", "immf.org",
)
TIER2_DOMAINS = (
    "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "apnews.com",
    "afp.com", "caixin.com", "cn.reuters.com", "xinhuanet.com",
)
TIER4_DOMAINS = (
    "weibo.com", "zhihu.com", "medium.com", "blogspot", "wordpress.com",
    "twitter.com", "x.com", "facebook.com", "toutiao.com", "baijiahao.baidu.com",
    "sohu.com", "163.com", "qq.com",
)

TIER1_SOURCE_TYPES = {"监管数据", "监管文件", "政策公告", "公司发布", "产品发布"}
TIER2_SOURCE_TYPES = {"行业协会"}


def _domain(item: dict) -> str:
    try:
        return (urlparse(item.get("source_url") or "").netloc or "").lower()
    except Exception:
        return ""


def tier_for_item(item: dict) -> int:
    source_type = str(item.get("source_type") or "").strip()
    if source_type in TIER1_SOURCE_TYPES:
        return 1
    if source_type in TIER2_SOURCE_TYPES:
        return 2
    domain = _domain(item)
    if not domain:
        return 3
    if _matches(domain, TIER1_DOMAINS):
        return 1
    if _matches(domain, TIER2_DOMAINS):
        return 2
    if _matches(domain, TIER4_DOMAINS):
        return 4
    return 3


def _matches(domain: str, patterns: tuple[str, ...]) -> bool:
    return any(domain == pattern or domain.endswith("." + pattern) for pattern in patterns)
