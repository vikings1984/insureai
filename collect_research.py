#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_research.py — 深度研究页「半自动闭环」采集（白皮书聚焦版）
=================================================================
初衷校准：只收录权威机构发布的研究报告/白皮书，不再混入媒体日常新闻。

三重门控（缺一不可）：
  1) 机构域名白名单 RESEARCH_DOMAINS：候选 URL 必须指向权威机构官网
     （瑞再/慕再/麦肯锡/德勤等一手信源）。媒体网站（Reinsurance News 等）
     的文章一律不算研究报告 —— 这是此前内容偏离初衷的根因。
  2) 财报噪声排除 EARNINGS_NOISE_RE：机构官网也会发季度财报通稿
     （"Munich Re posts Q2 net profit"），这是新闻不是研究报告。
  3) 标题须含报告型名词（报告/白皮书/研报/展望/report/whitepaper/sigma…），
     且通过保险信号门控。

机制：
  - 新发现标 auto=True、curated=False 写入 research.json；key_data/key_insight 留空待人工精炼。
  - 现有「无 auto 字段」的条目视为人工精编（curated=True），合并时永不覆盖。
  - --clean：一次性清洗历史 auto 条目（白名单/财报门控不通过的剔除；精编条目不动）。

复用 collect.py 的零依赖工具（fetch_url / parse_feed / is_insurance_relevant /
infer_topic / is_dup / to_iso / clean_text），保持零外部依赖。

用法：
    python3 collect_research.py            # 抓取 + 增量合并 + 写回 research.json
    python3 collect_research.py --dry-run  # 仅预览将新增的报告，不写文件
    python3 collect_research.py --clean    # 清洗历史 auto 条目（不抓新）
"""

import json
import sys
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import collect  # 复用零依赖工具（collect.py 有 __main__ 守卫，import 安全）

HERE = os.path.dirname(os.path.abspath(__file__))
RESEARCH_PATH = os.path.join(HERE, "research.json")
TIMEOUT = 15

# layer -> 中文 source_type（写入条的 source_type 字段，与前端徽章色对应：
# 绿=国际再保险 / 橙=全球咨询 / 蓝=国内研究）
LAYER_TO_TYPE = {
    "reinsurance": "国际再保险",
    "consulting": "全球咨询",
    "domestic": "国内研究",
    "regulator": "监管机构",
}

# ===================== 门控 1：权威机构域名白名单 =====================
# 域名 → (机构英文名, 机构中文名, 层级)。只有这些域名下的内容才算「机构报告」。
# 媒体/聚合站（reinsurancene.ws / insurancejournal.com / artemis.bm 等）刻意不在列。
RESEARCH_DOMAINS = {
    # —— 国际再保险（绿）——
    "swissre.com": ("Swiss Re Institute", "瑞再研究院", "reinsurance"),
    "munichre.com": ("Munich Re", "慕尼黑再保险", "reinsurance"),
    "hannover-re.com": ("Hannover Re", "汉诺威再保险", "reinsurance"),
    "sc.com": ("SCOR", "法国再保险", "reinsurance"),
    "lloyds.com": ("Lloyd's of London", "劳合社", "reinsurance"),
    "guycarp.com": ("Guy Carpenter", "佳达再保险经纪", "reinsurance"),
    "aon.com": ("Aon", "怡安", "reinsurance"),
    "wtwco.com": ("WTW", "韦莱韬悦", "reinsurance"),
    # —— 全球咨询（橙）——
    "mckinsey.com": ("McKinsey & Company", "麦肯锡", "consulting"),
    "bcg.com": ("BCG", "波士顿咨询", "consulting"),
    "bain.com": ("Bain & Company", "贝恩咨询", "consulting"),
    "deloitte.com": ("Deloitte", "德勤", "consulting"),
    "pwc.com": ("PwC", "普华永道", "consulting"),
    "kpmg.com": ("KPMG", "毕马威", "consulting"),
    "ey.com": ("EY", "安永", "consulting"),
    "oliverwyman.com": ("Oliver Wyman", "奥纬咨询", "consulting"),
    "capgemini.com": ("Capgemini", "凯捷", "consulting"),
    "accenture.com": ("Accenture", "埃森哲", "consulting"),
    "gartner.com": ("Gartner", "高德纳", "consulting"),
    # —— 国内研究（蓝）——
    "iachina.cn": ("中国保险行业协会", "中国保险行业协会", "domestic"),
    "nfra.gov.cn": ("国家金融监督管理总局", "金融监管总局", "regulator"),
    "iachina.org.cn": ("中国保险行业协会", "中国保险行业协会", "domestic"),
}

# 机构报告源清单：仅保留权威机构一手页面（kind=page 抓列表页提取链接；
# kind=rss 走 parse_feed）。失败自动跳过，不阻塞。
RESEARCH_SOURCES = [
    {"name": "Swiss Re Institute", "institution_cn": "瑞再研究院", "layer": "reinsurance",
     "kind": "page", "url": "https://www.swissre.com/institute.html"},
    {"name": "Munich Re", "institution_cn": "慕尼黑再保险", "layer": "reinsurance",
     "kind": "page", "url": "https://www.munichre.com/en/insights.html"},
    {"name": "McKinsey Insurance", "institution_cn": "麦肯锡", "layer": "consulting",
     "kind": "page", "url": "https://www.mckinsey.com/industries/financial-services/our-insights"},
    {"name": "Deloitte Insurance", "institution_cn": "德勤", "layer": "consulting",
     "kind": "page", "url": "https://www.deloitte.com/global/en/issues/insurance.html"},
    {"name": "Capgemini Research", "institution_cn": "凯捷", "layer": "consulting",
     "kind": "page", "url": "https://www.capgemini.com/insights/research-library/"},
    {"name": "Lloyd's", "institution_cn": "劳合社", "layer": "reinsurance",
     "kind": "page", "url": "https://www.lloyds.com/news-and-risk-insight"},
    {"name": "中国保险行业协会", "institution_cn": "中国保险行业协会", "layer": "domestic",
     "kind": "page", "url": "https://www.iachina.cn/"},
]

# ===================== 门控 2：财报/通稿噪声排除 =====================
# 机构官网也发季度财报与人事任命通稿 —— 是新闻，不是研究报告。
# 注意：只匹配「动词 + 财务名词」结构（reports 7.2% revenue growth），
# 不匹配「报告名词 + 年份」结构（Insurance Report 2026 是合法报告标题）。
EARNINGS_NOISE_RE = re.compile(
    r"\b(?:reports?|posts?|announces?|logs?|sees?)\s+(?:[a-z0-9’'%.$-]+\s+){0,4}"
    r"(?:profit|loss|revenue|income|earnings|growth|results|figures|guidance)"
    r"|\bprofit\s+(?:rises|falls|jumps|drops|climbs|soars|slips|hits)"
    r"|\b(?:raises|cuts|lowers|lifts|upgrades|revises)\s+(?:[a-z0-9’'%.$-]+\s+){0,3}"
    r"(?:profit|earnings|guidance|outlook|target)"
    r"|\bnet\s+(?:income|profit|loss)"
    r"|\bQ[1-4]\b['’]?\s*\d{0,4}"
    r"|\bH[12]\b\s*\d{0,4}"
    r"|\b(?:revenue|premium)s?\s+(?:growth|hike|rises|up)\b"
    r"|\b(?:appoints?|names?)\s+(?:\w+\s+){1,4}(?:as|to)\s+"
    r"|季度财报|净利润|营收增长|人事任命|人事变动",
    re.I,
)

# ===================== 门控 3：报告型标题信号（名词性） =====================
RESEARCH_SIGNALS = [
    "report", "whitepaper", "white paper", "study", "sigma", "outlook",
    "survey", "research", "annual report", "emerging risks",
    "报告", "白皮书", "蓝皮书", "研报", "年报", "展望", "洞察", "研究", "趋势",
]

HTML_LINK_RE = re.compile(
    r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>([^<]{4,120})</a>", re.I
)


def _is_earnings_noise(title):
    return bool(EARNINGS_NOISE_RE.search(title or ""))


def _is_research_title(title):
    t = (title or "").lower()
    if _is_earnings_noise(t):
        return False
    return any(sig in t for sig in RESEARCH_SIGNALS)


def _institution_for_url(url):
    """URL 域名命中白名单 → (机构英文名, 机构中文名, 层级)；否则 None。"""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return None
    host = host.replace("www.", "")
    for domain, info in RESEARCH_DOMAINS.items():
        # 精确匹配或子域（institute.swissre.com → swissre.com）
        if host == domain or host.endswith("." + domain):
            return info
    return None


def _abs_url(base, href):
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        p = urlparse(base)
        return f"{p.scheme}://{p.netloc}{href}"
    return base.rstrip("/") + "/" + href.lstrip("/")


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
    """候选条目经三重门控后结构化（auto=True）。URL 白名单信息优先于源清单。"""
    out = []
    for c in cands:
        title = collect.clean_text(c.get("title", ""))
        url = c.get("link", "")
        summary = c.get("summary", "") or ""
        if not title or not url or url.startswith("#"):
            continue
        # 门控 1：权威机构域名（白名单信息覆盖源清单默认值）
        inst = _institution_for_url(url)
        if not inst:
            continue
        # 门控 3：报告型标题；门控 2：财报通稿排除（含在 _is_research_title 内）
        if not _is_research_title(title):
            continue
        if not collect.is_insurance_relevant(title, summary):
            continue
        topic = collect.infer_topic(title, summary) or "product_innovation"
        now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        rid = "auto-" + str(abs(hash(url)) % (10 ** 12))
        name_en, name_cn, layer = inst
        out.append({
            "id": rid,
            "institution": name_en,
            "institution_cn": name_cn,
            "layer": layer,
            "title": title,
            "publish_date": collect.to_iso(c.get("published", "")),
            "topic": topic,
            "key_data": "",        # 待人工精炼
            "key_insight": "",     # 待人工精炼
            "url": url,
            "source_type": LAYER_TO_TYPE.get(layer, "全球咨询"),
            "is_pdf": url.lower().endswith(".pdf"),
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


def _passes_gates(r):
    """对历史条目重放三重门控（auto 条目用；curated 条目永不受此约束）。"""
    url = r.get("url", "")
    if not _institution_for_url(url):
        return False
    if not _is_research_title(r.get("title", "")):
        return False
    return True


def merge(new_reports, existing):
    """保留全部现有条（curated/auto 都不动），仅追加通过门控的真正新增。"""
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


def clean(existing):
    """一次性清洗：剔除不符合门控的 auto 条目（curated 精编条目一律保留）。"""
    kept, removed = [], []
    for r in existing.get("reports", []):
        if r.get("curated") or not r.get("auto"):
            kept.append(r)
            continue
        if _passes_gates(r):
            kept.append(r)
        else:
            removed.append(r)
    existing["reports"] = kept
    return removed


def run(dry_run=False, per_source_limit=10):
    existing = load_existing()
    print(f"=== InsureAI 研究采集（白皮书聚焦，dry={dry_run}）===")
    print(f"现有报告：{len(existing.get('reports', []))} 条")

    collected = []
    for src in RESEARCH_SOURCES:
        print(f"· 源 {src['name']} ({src['layer']}) …")
        cands = fetch_source(src)
        reports = build_report(cands, src)[:per_source_limit]
        print(f"    候选 {len(cands)} → 通过三重门控 {len(reports)}")
        collected.extend(reports)

    merged, added = merge(collected, existing)
    print(f"将新增：{added} 条（去重后）")

    # 预览
    for r in collected:
        if r.get("auto") and r["url"] not in {x.get("url") for x in existing.get("reports", [])}:
            tag = " [PDF]" if r.get("is_pdf") else ""
            print(f"  + [{r['institution_cn']}] {r['title'][:48]}{tag}  ({r['topic']})")

    if dry_run:
        print("（dry-run，未写文件）")
        return

    existing["reports"] = merged
    existing["last_updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with open(RESEARCH_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"✅ research.json 已更新：共 {len(merged)} 条（新增 {added}）")


def run_clean():
    """清洗历史 auto 条目并写回。"""
    existing = load_existing()
    removed = clean(existing)
    print(f"=== 清洗 auto 条目：剔除 {len(removed)} 条 ===")
    for r in removed:
        print(f"  🗑 [{r.get('institution_cn', '?')}] {r.get('title', '')[:50]}")
    existing["last_updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with open(RESEARCH_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"✅ 保留 {len(existing['reports'])} 条（精编 + 通过门控的 auto）")


if __name__ == "__main__":
    t0 = time.time()
    if "--clean" in sys.argv:
        run_clean()
    else:
        dry = "--dry-run" in sys.argv
        limit = 10
        for a in sys.argv:
            if a.startswith("--limit="):
                limit = int(a.split("=")[1])
        run(dry_run=dry, per_source_limit=limit)
    print(f"耗时 {time.time() - t0:.1f}s")
