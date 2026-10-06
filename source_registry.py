#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Source Registry / Source Group（V2 方案 §5 Source Registry + §7.1 Source Group）。

为什么需要这一层
----------------
方案 §7.1 的原话：

    3 URLs ≠ 3 independent sources
    cross_checked = true 必须基于 >= 2 independent source groups，而不是 URL 数量。

而改造前 ``claims.py`` 用的是 ``len({urlparse(url).netloc})``，即**原始主机名**：

    news.sina.com.cn  +  finance.sina.com.cn   →  2 个"独立域名"  →  误判 cross_checked
    www.x.com         +  x.com                 →  2 个"独立域名"  →  误判 cross_checked

这两个例子其实是**同一个信源**。对保险情报来说这是最危险的一类误判：转载链 /
同一门户的不同频道会让一条单一信源的结论被标成"已交叉验证"，直接污染
Evidence Coverage 与后续决策建议。

本模块提供两级归一化：

    URL → registrable domain（eTLD+1，正确处理 com.cn / co.uk 等多段后缀）
        → source group（同集团 / 同转载链合并）

判定规则因此从"域名个数"升级为"独立信源组个数"。

归并表外置（V2 P1-1）
---------------------
``SOURCE_GROUPS`` / ``SYNDICATION_PLATFORMS`` / ``MULTIPART_SUFFIXES`` 原先硬编码在本文件，
现统一外置到 ``sources/registry.yaml``，由本模块启动时载入。该文件是**人工维护的单一事实源**，
新增/调整信源组只需改 YAML，不必动代码。

本仓库是零依赖工程（collect.py / intelligence.py 仅用标准库），故载入使用内置极简
YAML 子集解析器（见 ``_yaml_lite_load``）；若运行环境已安装 PyYAML 则优先复用，结果等价。
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse


def _yaml_lite_load(text: str) -> dict:
    """极简 YAML 子集解析器（零依赖，失败降级用）。

    仅支持 ``sources/registry.yaml`` 用到的构造：整行注释(#)、块映射、块序列、
    行内流序列 ``[a, b, c]``、纯量字符串。请勿在该文件使用锚点 / 多行字符串 /
    行内注释，以免超出解析能力。若已安装 PyYAML 则优先用其（更稳健、等价）。
    """
    try:
        import yaml  # 可选：有 PyYAML 时优先
        return yaml.safe_load(text) or {}
    except Exception:
        pass
    lines = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append((indent, raw.strip()))
    n = len(lines)

    def _scalar(s: str):
        s = s.strip()
        if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
            return s[1:-1]
        return s

    def _flow_seq(s: str):
        inner = s.strip()[1:-1].strip()
        return [] if not inner else [_scalar(x) for x in inner.split(",")]

    def _value(s: str):
        s = s.strip()
        return _flow_seq(s) if s.startswith("[") else _scalar(s)

    i = [0]

    def _mapping(indent: int) -> dict:
        d: dict = {}
        while i[0] < n:
            ind, content = lines[i[0]]
            if ind < indent or content.startswith("- "):
                break
            if ind > indent or ":" not in content:
                i[0] += 1
                continue
            key, _, val = content.partition(":")
            key, val = key.strip(), val.strip()
            i[0] += 1
            if val == "":
                if i[0] < n and lines[i[0]][0] > indent:
                    child = lines[i[0]][0]
                    d[key] = _sequence(child) if lines[i[0]][1].startswith("- ") else _mapping(child)
                else:
                    d[key] = None
            else:
                d[key] = _value(val)
        return d

    def _sequence(indent: int) -> list:
        seq: list = []
        while i[0] < n:
            ind, content = lines[i[0]]
            if ind != indent or not content.startswith("- "):
                break
            item = content[2:].strip()
            i[0] += 1
            if item == "":
                if i[0] < n and lines[i[0]][0] > indent:
                    child = lines[i[0]][0]
                    seq.append(_sequence(child) if lines[i[0]][1].startswith("- ") else _mapping(child))
                else:
                    seq.append(None)
            elif ":" in item and not item.startswith("["):
                m: dict = {}
                k, _, v = item.partition(":")
                k, v = k.strip(), v.strip()
                if v != "":
                    m[k] = _value(v)
                m.update(_mapping(indent + 2))
                seq.append(m)
            else:
                seq.append(_value(item))
        return seq

    return _mapping(lines[0][0]) if n else {}


def _load_registry() -> tuple[frozenset, dict, frozenset]:
    """从 sources/registry.yaml 载入归并表（零依赖）。"""
    path = Path(__file__).resolve().parent / "sources" / "registry.yaml"
    data = _yaml_lite_load(path.read_text(encoding="utf-8"))
    multipart = frozenset(data.get("multipart_suffixes", []))
    groups: dict[str, str] = {}
    for s in data.get("sources", []):
        for dom in s.get("domains", []):
            groups[dom] = s["group"]
    syndication = frozenset(data.get("syndication_groups", []))
    return multipart, groups, syndication


MULTIPART_SUFFIXES, SOURCE_GROUPS, SYNDICATION_PLATFORMS = _load_registry()


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
    """取 eTLD+1：``news.sina.com.cn`` → ``sina.com.cn``，``www.reuters.com`` → ``reuters.com``。"""
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
    - 查不到就用 registrable domain 兜底（``dom:<eTLD+1>``），保证"未知来源互不合并"。
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
