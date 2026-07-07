#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
InsureScope 自动采集管道 (collect.py)
=====================================
零依赖（仅 Python 标准库）。让"发布资讯"的成本趋近于零。

两条采集通道（任一可用即可）：
  1) RSS/Atom 信源：在 SOURCES 中填入真实可用的订阅地址（中文保险站点多无公开 RSS，
     故默认仅作框架；请按需替换/扩充为已验证的 Feed）。
  2) 收件箱 ingestion：把你想收录的真实文章链接放进 inbox.json
     （[{ "url": "...", "source_name": "...", "source_type": "..." }]），
     管道会自动抓取标题/摘要、评分、分类、去重并合并。这是最可靠的主通道。

流程：抓取 → 评分(0-100) → 研究主题分类 → Levenshtein 去重(相似度≥0.82) →
      增量合并(不覆盖既有精选) → 重算 days / source_health → 写回 data.json。

容错：单个信源超时/失败不影响其他；全部失败则保留既有数据并仅刷新统计。

用法：
    python3 collect.py                # 执行采集并合并
    python3 collect.py --dry-run      # 仅预览将新增条目，不写文件
    python3 collect.py --limit 10     # 每个 RSS 信源最多取 10 条
"""

import json
import sys
import os
import re
import time
import html
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

# ===================== 配置 =====================
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data.json")
INBOX_PATH = os.path.join(HERE, "inbox.json")
TIMEOUT = 12
UA = "Mozilla/5.0 (compatible; InsureScopeBot/1.0; +https://github.com/vikings1984/insureai)"

# RSS 信源（真实可用地址；国内保险站点普遍无公开 RSS，故以国际权威信源为主通道）
# 如需中文内容，请把文章链接放入 inbox.json 走收件箱通道（最可靠）。
SOURCES = [
    {"name": "Insurance Journal", "type": "媒体", "authority": 84, "rss": "https://www.insurancejournal.com/feed/"},
    {"name": "Reinsurance News", "type": "媒体", "authority": 82, "rss": "https://www.reinsurancene.ws/feed/"},
    {"name": "Artemis (ILS)", "type": "媒体", "authority": 83, "rss": "https://www.artemis.bm/feed/"},
]

# 研究主题关键词
RESEARCH_TOPICS = {
    "ai_intelligent": ["人工智能", "AI", "大模型", "智能核保", "智能理赔", "智能体", "Agent", "数字化", "科技",
                        "artificial intelligence", "generative ai", "insurtech", "automation"],
    "pension_finance": ["养老", "年金", "退休", "养老金", "第三支柱", "个人养老金", "pension", "annuity", "retirement"],
    "product_innovation": ["产品", "创新", "UBI", "惠民保", "参数化", "健康险", "医疗险", "重疾险", "车险",
                            "医疗", "医保", "保单", "寿险", "慢病", "product", "launch", "parametric",
                            "health insurance", "motor", "life insurance"],
    "channel_transformation": ["代理人", "银保", "渠道", "互联网保险", "线上化", "中介", "agent", "broker",
                                "distribution", "digital"],
    "capital_reinsurance": ["再保险", "巨灾", "偿付能力", "ILS", "续转", "资本", "并购", "投资", "险资", "资管",
                             "reinsurance", "catastrophe", "capital", "merger", "investment", "solvency"],
    "climate_catastrophe": ["气候", "自然灾害", "台风", "洪灾", "极端天气", "巨灾保险", "农业保险", "指数",
                             "climate", "natural catastrophe", "flood", "wildfire", "hurricane", "parametric"],
    "digital_transformation": ["数字化", "保险科技", "InsurTech", "核心系统", "区块链", "数据中台", "digital",
                                "blockchain", "core system", "data"],
    "regulatory_change": ["监管", "合规", "C-ROSS", "IFRS 17", "金融监管总局", "行政处罚", "政策", "处罚",
                           "regulation", "compliance", "regulator", "ifrs 17", "policy", "fine"],
}

SCORE_BOOST = [
    (["人工智能", "AI", "大模型", "智能体", "Agent", "insurtech", "generative ai"], 6),
    (["养老", "巨灾", "偿付能力", "气候", "碳中和", "reinsurance", "catastrophe", "solvency", "ils"], 5),
    (["监管", "合规", "处罚", "办法", "指引", "regulation", "compliance", "regulator", "fine"], 4),
    (["创新", "首发", "首个", "突破", "launch", "unveils", "parametric"], 3),
    (["产品", "渠道", "数字化", "product", "digital"], 2),
]


# ===================== 工具函数 =====================
def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_feed(content):
    items = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return items
    for it in root.iter("item"):
        items.append({
            "title": _text(it.find("title")),
            "link": _text(it.find("link")),
            "summary": _strip(_text(it.find("description")) or _text(it.find("summary"))),
            "published": _text(it.find("pubDate")) or _text(it.find("dc:date")),
        })
    if not items:
        ns = "{http://www.w3.org/2005/Atom}"
        for en in root.iter(ns + "entry"):
            link = ""
            for l in en.findall(ns + "link"):
                if l.get("href"):
                    link = l.get("href"); break
            items.append({
                "title": _text(en.find(ns + "title")),
                "link": link,
                "summary": _strip(_text(en.find(ns + "summary"))),
                "published": _text(en.find(ns + "updated")),
            })
    return items


def _text(el):
    if el is None or el.text is None:
        return ""
    return html.unescape(el.text.strip())


def _strip(h):
    t = re.sub(r"<[^>]+>", " ", h or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()[:300]


def extract_page(url):
    """从文章页抓取标题与摘要"""
    html_text = fetch_url(url)
    title = ""
    m = re.search(r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)[\"']", html_text, re.I)
    if not m:
        m = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.I | re.S)
    if m:
        title = html.unescape(m.group(1)).strip()
    desc = ""
    for pat in [r"property=[\"']og:description[\"'][^>]+content=[\"']([^\"']+)[\"']",
                r"name=[\"']description[\"'][^>]+content=[\"']([^\"']+)[\"']"]:
        mm = re.search(pat, html_text, re.I)
        if mm:
            desc = html.unescape(mm.group(1)).strip(); break
    return title, _strip(desc) or (title[:120] if title else "")


def to_iso(pub):
    if not pub:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except Exception:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def infer_topic(title, summary):
    text = (title + " " + summary).lower()
    scores = {t: sum(1 for kw in kws if kw.lower() in text) for t, kws in RESEARCH_TOPICS.items()}
    scores = {t: c for t, c in scores.items() if c}
    return max(scores, key=scores.get) if scores else None


def score_item(title, summary, authority):
    text = (title + " " + summary).lower()
    s = authority
    for kws, boost in SCORE_BOOST:
        if any(k.lower() in text for k in kws):
            s += boost
    return max(60, min(95, s))


def lev_ratio(a, b):
    a, b = a.lower(), b.lower()
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if la == 0 or lb == 0:
        return 0.0
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return 1.0 - prev[lb] / max(la, lb)


def is_dup(title, existing_titles, threshold=0.82):
    return any(lev_ratio(title, t) >= threshold for t in existing_titles)


def _category(title, summary):
    text = (title + " " + summary).lower()
    if any(k in text for k in ["监管", "办法", "指引", "处罚", "合规", "政策", "regulation", "compliance",
                               "regulator", "fine", "ifrs"]):
        return "regulation"
    if any(k in text for k in ["研报", "报告", "研究表明", "sigma", "白皮书", "咨询", "report", "research",
                               "whitepaper", "study"]):
        return "research"
    if any(k in text for k in ["产品", "首发", "推出", "上线", "launch", "unveils", "introduces", "product"]):
        return "product"
    if any(k in text for k in ["理赔", "案例", "纠纷", "判决", "claim", "lawsuit", "settlement", "verdict"]):
        return "claims"
    return "industry"


# ===================== 主流程 =====================
def run(dry_run=False, per_source_limit=10):
    data = load_existing()
    existing = data.get("news", [])
    existing_titles = [n.get("title", "") for n in existing]
    collected = []
    source_health = {}
    next_id = max((n.get("id", 0) for n in existing), default=0) + 1

    # 通道 1：RSS
    for src in SOURCES:
        name = src["name"]
        try:
            raw = parse_feed(fetch_url(src["rss"]))
            ok = bool(raw)
        except Exception as e:
            raw = []; ok = False
            print(f"  ⚠ RSS {name} 失败: {e}")
        source_health[name] = {"count": len(raw), "ok": ok}
        for it in raw[:per_source_limit]:
            _ingest(it["title"], it["summary"], it["link"], src["name"], src["type"],
                    src["authority"], to_iso(it["published"]), existing_titles, collected,
                    require_topic=True)
            next_id += 1

    # 通道 2：收件箱
    inbox = load_inbox()
    if inbox:
        print(f"  📥 收件箱: {len(inbox)} 条待处理")
        processed = []
        for entry in inbox:
            url = entry.get("url")
            if not url:
                continue
            try:
                title, desc = extract_page(url)
                sname = entry.get("source_name") or _host(url)
                stype = entry.get("source_type") or "媒体"
                auth = entry.get("authority", 85)
                _ingest(title, desc, url, sname, stype, auth,
                        entry.get("published_at") or to_iso(None),
                        existing_titles, collected, reason=entry.get("reason"))
                processed.append(entry)
            except Exception as e:
                print(f"  ⚠ 收件箱条目失败 {url}: {e}")
        if processed and not dry_run:
            save_inbox([e for e in inbox if e not in processed])  # 清空已处理
    else:
        print("  📭 收件箱为空")

    # 合并
    merged = existing + collected
    merged.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    for i, n in enumerate(merged, 1):
        n["id"] = i

    _sync_sources(data, merged)
    days = _rebuild_days(merged)
    _merge_source_health(data, source_health, merged)

    if dry_run:
        print(f"\n[dry-run] 将新增 {len(collected)} 条，合并后共 {len(merged)} 条。")
        for c in collected[:12]:
            print(f"  + [{c['ai_score']}] {c['title'][:42]}")
        return

    data["news"] = merged
    data["days"] = days
    data["version"] = bump_version(data.get("version", "2.2.2"))
    data["last_updated"] = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 采集完成：新增 {len(collected)} 条，合并后共 {len(merged)} 条，版本 {data['version']}")
    print(f"   days 天数: {len(days)}；source_health 信源: {len(data.get('source_health', {}))}")


def _ingest(title, summary, url, sname, stype, authority, published, existing_titles, collected, reason=None, require_topic=False):
    if not title or is_dup(title, existing_titles + [c["title"] for c in collected]):
        return
    topic = infer_topic(title, summary)
    if require_topic and topic is None:
        return  # RSS 噪声过滤：未命中任何保险主题关键词则不收录
    collected.append({
        "id": 0,
        "title": title,
        "summary": summary or title,
        "source_name": sname,
        "source_type": stype,
        "source_url": url,
        "importance": 4,
        "ai_score": score_item(title, summary, authority),
        "tags": "",
        "category": _category(title, summary),
        "published_at": published,
        "reason": reason or "由自动采集管道生成，建议人工复核后提升为精选。",
        "date_verified": False,
        "research_topic": topic or "product_innovation",
        "is_research_report": stype in ("研究机构", "咨询"),
    })
    existing_titles.append(title)


def _host(url):
    m = re.search(r"https?://([^/]+)/?", url)
    return m.group(1) if m else url


def _sync_sources(data, merged):
    """确保 news 中出现的所有 source_name 都在 sources 列表中"""
    sources = data.get("sources", [])
    known = {s.get("name") for s in sources}
    for n in merged:
        name = n.get("source_name")
        if name and name not in known:
            sources.append({
                "name": name,
                "type": n.get("source_type", "媒体"),
                "score": 80,
                "update_freq": "不定期",
                "last_update": datetime.now().strftime("%Y-%m-%d"),
                "status": "active",
            })
            known.add(name)
    data["sources"] = sources


def _rebuild_days(news):
    days = {}
    for n in news:
        d = n.get("published_at", "")[:10]
        if not d:
            continue
        rec = days.setdefault(d, {"total": 0, "curated": 0, "highlights": 0,
                                  "avg_score": 0.0, "categories": {}, "sources": set()})
        rec["total"] += 1
        if n.get("source_url"):
            rec["curated"] += 1
        if n.get("ai_score", 0) >= 80:
            rec["highlights"] += 1
        cat = n.get("category", "industry")
        rec["categories"][cat] = rec["categories"].get(cat, 0) + 1
        if n.get("source_name"):
            rec["sources"].add(n["source_name"])
    for d, rec in days.items():
        same = [x for x in news if x.get("published_at", "")[:10] == d]
        rec["avg_score"] = round(sum(x.get("ai_score", 0) for x in same) / len(same), 1)
        rec["sources"] = sorted([s for s in rec["sources"] if s])
    return days


def _merge_source_health(data, fetched, news):
    sh = data.get("source_health", {})
    counts = {}
    for n in news:
        counts[n.get("source_name", "")] = counts.get(n.get("source_name", ""), 0) + 1
    for name, info in fetched.items():
        sh[name] = {"count": counts.get(name, info["count"]), "ok": info["ok"]}
    for name, c in counts.items():
        if name not in sh:
            sh[name] = {"count": c, "ok": True}
    data["source_health"] = sh


def load_existing():
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"news": [], "sources": [], "days": {}, "version": "2.3.0"}


def load_inbox():
    try:
        with open(INBOX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_inbox(items):
    with open(INBOX_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def bump_version(v):
    parts = v.split(".")
    try:
        parts[2] = str(int(parts[2]) + 1)
    except (IndexError, ValueError):
        return "2.3.0"
    return ".".join(parts[:3]) if len(parts) >= 3 else "2.3.0"


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    limit = 10
    for a in sys.argv:
        if a.startswith("--limit="):
            limit = int(a.split("=")[1])
    print(f"=== InsureScope 采集管道 (dry={dry}, limit={limit}) ===")
    t0 = time.time()
    run(dry_run=dry, per_source_limit=limit)
    print(f"耗时 {time.time() - t0:.1f}s")
