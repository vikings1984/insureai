#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-4 Source Snapshot（不可变 Raw Layer）。

每个被采集的 item 在写入业务数据（data.json）之前，先落一份不可变 Raw 快照，
使任意 Evidence 可经 Article → Snapshot → Original URL 回溯（方案 §4.3 / 附录 B）。

约束：
- 零依赖（仅标准库），与 collect.py / intelligence.py 一致。
- 快照写入后不可变（已存在则跳过写盘，不覆盖、不删除）；同内容重抓因 retrieved_at
  不同会生成新快照，旧快照保留。
- 去重：以 content_hash 判断是否为同一篇；raw 文本内联进快照 JSON（raw_text 字段），
  无需额外 data/raw/ 目录，减少提交面与回溯断裂风险。
- source_id 采用 Source Group 标识（与 §7.1 一致）。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(HERE, "snapshot")

PARSER_VERSION = "collect-4.2"  # parser_version：随采集器演进递增


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def _content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def canonicalize_url(url: str) -> str:
    """轻量规范化：去掉 #fragment 与常见跟踪参数，用于快照去重与回溯。

    保守处理，避免破坏必需查询参数；复杂规范化留给后续阶段。
    """
    if not url:
        return url
    url = url.split("#")[0]
    if "?" in url:
        base, qs = url.split("?", 1)
        keep = []
        for kv in qs.split("&"):
            k = kv.split("=", 1)[0].lower()
            if k.startswith("utm_") or k in ("spm", "from", "wfrom", "share"):
                continue
            keep.append(kv)
        url = base + ("?" + "&".join(keep) if keep else "")
    return url


def _resolve_source_id(item: dict) -> str:
    """source_id 用 Source Group 标识（与 §7.1 一致）；未知源退化为 dom:<eTLD+1>。"""
    try:
        from source_registry import source_group
        return source_group(item)
    except Exception:
        from urllib.parse import urlparse
        host = urlparse(item.get("source_url") or item.get("url") or "").netloc
        return "dom:" + (host or "unknown")


def snapshot_id_for(source_id: str, canonical_url: str, retrieved_at: str) -> str:
    raw = f"{source_id}|{canonical_url}|{retrieved_at}"
    return "snap_" + retrieved_at[:10].replace("-", "") + "_" + hashlib.sha256(raw.encode()).hexdigest()[:8]


def build_snapshot(title, summary, url, source_name="", source_type="", published_at=None,
                   retrieved_at=None, content=None) -> dict:
    """为一个采集 item 生成快照元数据（不写盘）。返回 dict。"""
    retrieved_at = retrieved_at or _now_iso()
    canonical_url = canonicalize_url(url)
    source_id = _resolve_source_id({"source_url": url, "source_name": source_name})
    text = content if content is not None else (summary or title or "")
    content_hash = _content_hash(text)
    return {
        "snapshot_id": snapshot_id_for(source_id, canonical_url, retrieved_at),
        "source_id": source_id,
        "url": url,
        "canonical_url": canonical_url,
        "retrieved_at": retrieved_at,
        "published_at": published_at,
        "content_hash": content_hash,
        "parser_version": PARSER_VERSION,
        # 原始内容内联（不可变 Raw Layer）；content_hash 用于去重与完整性校验
        "raw_text": text,
    }


def persist_snapshot(snap: dict) -> str:
    """落盘 snapshot/snap_<id>.json（不可变）。返回 snapshot_id。"""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    sid = snap["snapshot_id"]
    path = os.path.join(SNAPSHOT_DIR, f"{sid}.json")
    if not os.path.exists(path):  # 不可变：已存在则跳过写盘
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
    return sid


def find_snapshot(snapshot_id: str):
    """回溯查询：snapshot_id → 快照元数据（含 url / raw_text）。"""
    if not snapshot_id:
        return None
    path = os.path.join(SNAPSHOT_DIR, f"{snapshot_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_raw(snapshot_id: str):
    """读取快照对应的原始内容文本（回溯链终点）。"""
    snap = find_snapshot(snapshot_id)
    return snap.get("raw_text") if snap else None
