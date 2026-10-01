#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Source Registry / Source Group（V2 方案 §5 Source Registry + §7.1 Source Group）。

为什么需要这一层
----------------
方案 §7.1 的原话：

    3 URLs ≠ 3 independent sources
    cross_checked = true 必须基于 >= 2 independent source groups，而不是 URL 数量。

而改造前 `claims.py` 用的是 ``len({urlparse(url).netloc})``，即**原始主机名**：

    news.sina.com.cn  +  finance.sina.com.cn   →  2 个"独立域名"  →  误判 cross_checked
    www.x.com         +  x.com                 →  2 个"独立域名"  →  误判 cross_checked

这两个例子其实是**同一个信源**。对保险情报来说这是最危险的一类误判：转载链 /
同一门户的不同频道会让一条单一信源的结论被标成"已交叉验证"，直接污染
Evidence Coverage 与后续决策建议。

本模块提供两级归一化：

    URL → registrable domain（eTLD+1，正确处理 com.cn / co.uk 等多段后缀）
        → source group（同集团 / 同转载链合并）

判定规则因此从"域名个数"升级为"独立信源组个数"。
"""
from __future__ import annotations

from urllib.parse import urlparse

# 多段后缀：只取最后两段会切错（sina.com.cn → com.cn），必须保留三段。
MULTIPART_SUFFIXES = frozenset({
    "com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "ac.cn",
    "com.hk", "net.hk", "org.hk", "gov.hk",
    "com.tw", "net.tw", "org.tw",
    "co.jp", "or.jp", "ne.jp", "ac.jp", "go.jp",
    "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk",
    "com.au", "net.au", "org.au",
    "com.br", "com.sg", "co.kr", "co.in",
})

# 同集团 / 同转载链的显式归并表。
# key = registrable domain，value = source group id。
# 只有"同一家机构、不同域名/频道"才应合并；不同门户之间不合并。
SOURCE_GROUPS: dict[str, str] = {
    # 新华社系
    "xinhuanet.com": "grp:xinhua",
    "news.cn": "grp:xinhua",
    "xinhua08.com": "grp:xinhua",
    # 人民日报系
    "people.com.cn": "grp:people",
    "peopledaily.com.cn": "grp:people",
    # 中新社系
    "chinanews.com.cn": "grp:chinanews",
    "chinanews.com": "grp:chinanews",
    # 央视 / 央广
    "cctv.com": "grp:cctv",
    "cntv.cn": "grp:cctv",
    # 中国经济网 / 经济日报系
    "ce.cn": "grp:cecn",
    "ceweekly.cn": "grp:cecn",
    # 金融时报系（中国）
    "ftchinese.com": "grp:ftchinese",
    "ft.com": "grp:ft",
    # 界面 / 蓝鲸（同一集团不同域名）
    "jiemian.com": "grp:jiemian",
    "lanjingcj.com": "grp:jiemian",
    # 财新
    "caixin.com": "grp:caixin",
    "caijing.com.cn": "grp:caijing",
    # 第一财经
    "yicai.com": "grp:yicai",
    # 21 世纪经济报道系
    "21jingji.com": "grp:21jingji",
    "21cbh.com": "grp:21jingji",
    # 券商中国 / 证券时报系
    "stcn.com": "grp:stcn",
    "quanshangcn.com": "grp:stcn",
    # 东方财富系
    "eastmoney.com": "grp:eastmoney",
    "1234567.com.cn": "grp:eastmoney",
    # 同花顺系
    "10jqka.com.cn": "grp:ths",
    "hexun.com": "grp:hexun",
    # 和讯 / 金融界
    "jrj.com.cn": "grp:jrj",
    "jinrongjie.com": "grp:jrj",
    # 新浪 / 微博
    "sina.com.cn": "grp:sina",
    "sina.com": "grp:sina",
    "weibo.com": "grp:sina",
    # 网易
    "163.com": "grp:netease",
    "126.com": "grp:netease",
    # 腾讯
    "qq.com": "grp:tencent",
    "tencent.com": "grp:tencent",
    # 搜狐 / 搜狗
    "sohu.com": "grp:sohu",
    "sogou.com": "grp:sohu",
    # 凤凰
    "ifeng.com": "grp:ifeng",
    # 今日头条系
    "toutiao.com": "grp:toutiao",
    "toutiaopage.com": "grp:toutiao",
    # 百度
    "baidu.com": "grp:baidu",
    # 保险行业垂直（各自独立，仅做域名收敛）
    "iachina.cn": "grp:iachina",
    "insurancejournal.com": "grp:insurancejournal",
    "reinsurancene.ws": "grp:reinsurancene",
    "artemis.bm": "grp:artemis",
    "reuters.com": "grp:reuters",
    "bloomberg.com": "grp:bloomberg",
}

# 已知转载平台：同一稿件出现在这类平台上，不能单独构成"新增独立信源"。
SYNDICATION_PLATFORMS = frozenset({
    "grp:toutiao", "grp:baidu", "grp:sohu", "grp:163",
})


def _host(url_or_host: str) -> str:
    value = (url_or_host or "").strip()
    if not value:
        return ""
    if "://" not in value:
        host = value
    else:
        host = urlparse(value).netloc or ""
    host = host.split("@")[-1].split(":")[0].strip().lower().rstrip(".")
    return host


def registrable_domain(url_or_host: str) -> str:
    """取 eTLD+1：`news.sina.com.cn` → `sina.com.cn`，`www.reuters.com` → `reuters.com`。"""
    host = _host(url_or_host)
    if not host:
        return ""
    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return ".".join(parts)
    if ".".join(parts[-2:]) in MULTIPART_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def source_group(item_or_url) -> str:
    """归到独立信源组。

    - 优先尊重数据自带的 ``source_group`` / ``source_group_id``（采集侧已知转载关系时）；
    - 否则查 ``SOURCE_GROUPS`` 归并表；
    - 查不到就用 registrable domain 兜底（`dom:<eTLD+1>`），保证"未知来源互不合并"。
    """
    if isinstance(item_or_url, dict):
        explicit = item_or_url.get("source_group") or item_or_url.get("source_group_id")
        if explicit:
            return str(explicit)
        url = item_or_url.get("source_url") or item_or_url.get("url") or ""
        domain = item_or_url.get("domain") or registrable_domain(url)
    else:
        url = str(item_or_url or "")
        domain = registrable_domain(url)
    domain = registrable_domain(domain) or registrable_domain(url)
    if not domain:
        return "dom:unknown"
    return SOURCE_GROUPS.get(domain, f"dom:{domain}")


def independent_source_groups(items) -> int:
    """统计独立信源组数量（cross_checked 的判定依据）。"""
    return len({source_group(x) for x in items or [] if source_group(x) != "dom:unknown"})


def source_group_ids(items) -> list[str]:
    return sorted({source_group(x) for x in items or [] if source_group(x) != "dom:unknown"})
