#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_research.py — 深度研究页「半自动闭环」采集
=================================================
机制：
  1) 维护机构报告源清单 RESEARCH_SOURCES（国际再保险 / 全球咨询 / 国内研究 / 监管机构 四层）。
  2) 自动发现各源新发布的报告型内容（标题含 report/whitepaper/study/sigma/展望/报告… 且通过保险信号门控）。
  3) 新发现标 auto=True、curated=False 写入 research.json；字段 key_data/key_insight 留空待人工精炼。
  4) 现有「无 auto 字段」的条目视为人工精编（curated=True），合并时永不覆盖。
  5) 人工精炼后把条目标 curated=True（CI 自动采集即不再改动它）。

复用 collect.py 的零依赖工具（fetch_url / parse_feed / is_insurance_relevant /
infer_topic / is_dup / to_iso / clean_text），保持零外部依赖。

容错：单源超时/失败不影响其他；全部失败则保留既有数据（仅刷新 last_updated）。

用法：
    python3 collect_research.py            # 抓取 + 增量合并 + 写回 research.json
    python3 collect_research.py --dry-run  # 仅预览将新增的报告，不写文件
    python3 collect_research.py --limit 10 # 每个源最多取 10 条候选
"""

import json
import sys
import os
import re
import time
from datetime import datetime, timezone

import collect  # 复用零依赖工具（collect.py 有 __main__ 守卫，import 安全）

HERE = os.path.dirname(os.path.abspath(__file__))
RESEARCH_PATH = os.path.join(HERE, "research.json")
TIMEOUT = 15

# layer -> 中文 source_type（写入条的 source_type 字段）
LAYER_TO_TYPE = {
    "reinsurance": "国际再保险",
    "consulting": "全球咨询",
    "domestic": "国内研究",
    "regulator": "监管机构",
}

# 机构报告源清单（在此增删即可扩展；page 类型失败会自动跳过，不阻塞）。
#   kind=rss  : 走 collect.parse_feed
#   kind=page : 抓列表页，正则提取 <a> 链接（绝对化后过滤）
RESEARCH_SOURCES = [
    # —— 已验证可用的英文 RSS（复用 collect.py 信源，稳定）——
    {"name": "Reinsurance News", "institution_cn": "再保险新闻", "layer": "reinsurance",
     "kind": "rss", "url": "https://www.reinsurancene.ws/feed/"},
    {"name": "Artemis", "institution_cn": "Artemis (ILS)", "layer": "reinsurance",
     "kind": "rss", "url": "https://www.artemis.bm/feed/"},
    {"name": "Insurance Journal", "institution_cn": "保险期刊", "layer": "consulting",
     "kind": "rss", "url": "https://www.insurancejournal.com/feed/"},
    # —— 机构报告页（尝试性，失败自动跳过；可在 CI 跑通后校正 URL）——
    {"name": "McKinsey Insurance", "institution_cn": "麦肯锡", "layer": "consulting",
     "kind": "page", "url": "https://www.mckinsey.com/industries/financial-services/our-insights"},
    {"name": "Deloitte Insurance", "institution_cn": "德勤", "layer": "consulting",
     "kind": "page", "url": "https://www.deloitte.com/global/en/issues/insurance.html"},
    {"name": "Swiss Re Institute", "institution_cn": "瑞再研究院", "layer": "reinsurance",
     "kind": "page", "url": "https://www.swissre.com/institute.html"},
]

# 从新闻 RSS / 机构页中筛选「报告型」内容的关键词
RESEARCH_SIGNALS = [
    "report", "whitepaper", "white paper", "study", "sigma", "annual report",
    "annual", "outlook", "survey", "benchmark", "index",
    "展望", "报告", "白皮书", "蓝皮书", "研报", "年报", "洞察", "趋势", "测算",
    "解读", "深度", "年度",
]

HTML_LINK_RE = re.compile(
    r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>([^<]{4,120})</a>", re.I
)


def _is_research_title(title):
    t = (title or "").lower()
    return any(sig in t for sig in RESEARCH_SIGNALS)


def _abs_url(base, href):
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        from urllib.parse import urlparse
        p = urlparse(base)
        return f"{p.scheme}://{p.netloc}{href}"
    return base.rstrip("/") + "/" + href.lstrip("/")


def _norm_layer(layer):
    return layer if layer in LAYER_TO_TYPE else "consulting"


def fetch_source(src):
    """返回候选条目列表（原始 dict：title/link/summary/published）。"""
    cands = []
    try:
        raw = collect.fetch_url(src["url"])
    except Exception as e:
        print(f"  ⚠ 源失败 {src['name']}: {e}")
        return cands
    if src["kind"] == "rss" or "<rss" in raw[:2000] or "<feed" in raw[:2000]:
        cands = collect.parse_feed(raw)
    else:
        for href, text in HTML_LINK_RE.findall(raw):
            u = _abs_url(src["url"], href)
            if not u or u.rstrip("/") == src["url"].rstrip("/"):
                continue
            cands.append({"title": collect.clean_text(text), "link": u, "summary": "", "published": ""})
    return cands


def build_report(cands, src):
    """把候选条目过滤+结构化，产出研究条目（auto=True）。"""
    out = []
    for c in cands:
        title = collect.clean_text(c.get("title", ""))
        url = c.get("link", "")
        summary = c.get("summary", "") or ""
        if not title or not url or url.startswith("#"):
            continue
        if not _is_research_title(title):
            continue
        if not collect.is_insurance_relevant(title, summary):
            continue
        topic = collect.infer_topic(title, summary) or "product_innovation"
        now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        rid = "auto-" + str(abs(hash(url)) % (10 ** 12))
        out.append({
            "id": rid,
            "institution": src["name"],
            "institution_cn": src["institution_cn"],
            "layer": _norm_layer(src["layer"]),
            "title": title,
            "publish_date": collect.to_iso(c.get("published", "")),
            "topic": topic,
            "key_data": "",        # 待人工精炼
            "key_insight": "",     # 待人工精炼
            "url": url,
            "source_type": LAYER_TO_TYPE.get(_norm_layer(src["layer"]), "全球咨询"),
            "auto": True,
            "curated": False,
            "fetched_at": now,
        })
    return out


def load_existing():
    try:
        with open(RESEARCH_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_updated": "", "description": "", "layers": {}, "topics": {}, "reports": []}


def merge(new_reports, existing):
    """保留全部现有条（curated/auto 都不动），仅追加真正新增的。"""
    norm = []
    for r in existing.get("reports", []):
        r = dict(r)
        if "auto" not in r:
            r["curated"] = True   # 历史人工条：视为精编，永不覆盖
        norm.append(r)
    existing_urls = {r.get("url") for r in norm if r.get("url")}
    existing_titles = [r.get("title", "") for r in norm]

    out = list(norm)
    added = 0
    for r in new_reports:
        if r["url"] in existing_urls:
            continue
        if collect.is_dup(r["title"], existing_titles, 0.82):
            continue
        out.append(r)
        existing_urls.add(r["url"])
        existing_titles.append(r["title"])
        added += 1
    return out, added


def run(dry_run=False, per_source_limit=10):
    existing = load_existing()
    print(f"=== InsureAI 研究采集（dry={dry_run}）===")
    print(f"现有报告：{len(existing.get('reports', []))} 条")

    collected = []
    for src in RESEARCH_SOURCES:
        print(f"· 源 {src['name']} ({src['layer']}) …")
        cands = fetch_source(src)
        reports = build_report(cands, src)[:per_source_limit]
        print(f"    候选 {len(cands)} → 通过门控 {len(reports)}")
        collected.extend(reports)

    merged, added = merge(collected, existing)
    print(f"将新增：{added} 条（去重后）")

    # 预览
    for r in collected:
        if r.get("auto") and r["url"] not in {x.get("url") for x in existing.get("reports", [])}:
            print(f"  + [{r['institution_cn']}] {r['title'][:48]}  ({r['topic']})")

    if dry_run:
        print("（dry-run，未写文件）")
        return

    existing["reports"] = merged
    existing["last_updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with open(RESEARCH_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"✅ research.json 已更新：共 {len(merged)} 条（新增 {added}）")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    limit = 10
    for a in sys.argv:
        if a.startswith("--limit="):
            limit = int(a.split("=")[1])
    t0 = time.time()
    run(dry_run=dry, per_source_limit=limit)
    print(f"耗时 {time.time() - t0:.1f}s")
