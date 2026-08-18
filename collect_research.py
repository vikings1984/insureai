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
  - 方向驱动补充：每次运行统计 8 个方向的报告数，低于 RESEARCH_TOPIC_MIN 的方向
    自动触发「方向主题页 + 搜狗定向搜索」补缺，尾部输出方向覆盖报告与补齐建议。

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
    "chinare.com.cn": ("China Re", "中再集团", "domestic"),
    "iamac.org.cn": ("IAMAC", "中国保险资产管理业协会", "domestic"),
}

# 机构报告源清单：仅保留权威机构一手页面（kind=page 抓列表页提取链接；
# kind=rss 走 parse_feed）。失败自动跳过，不阻塞。
RESEARCH_SOURCES = [
    {"name": "Swiss Re Institute", "institution_cn": "瑞再研究院", "layer": "reinsurance",
     "kind": "page", "url": "https://www.swissre.com/institute/research/sigma-research.html"},
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

# ===================== 方向驱动补充（按 8 个设定方向定期补缺） =====================
# 主采集是「信源驱动」（机构首页有什么收什么），方向覆盖天然不均衡。
# 机制：每次运行统计各方向报告数 → 低于 RESEARCH_TOPIC_MIN 的方向触发补充：
#   1) TOPIC_SOURCES：该方向的机构主题页（已验证可抓，可靠性优先）
#   2) direction_search()：搜狗「方向关键词」搜索，结果仍过三重门控 + 方向词命中
#      （CI 数据中心 IP 易触发反爬，自动跳过不报错）
# 补不齐的方向在尾部缺口报告中提示，走人工精编（inbox / MCP 辅助搜索）兜底。

RESEARCH_TOPIC_MIN = 3  # 每个方向的目标条数

# 方向 → 搜狗搜索短语（针对国内权威域名的中文方向检索）
TOPIC_QUERIES = {
    "ai_intelligent": ["保险 人工智能 报告", "保险 大模型 白皮书"],
    "pension_finance": ["养老保险 报告", "个人养老金 白皮书"],
    "product_innovation": ["健康险 产品 报告", "保险 产品创新 白皮书"],
    "channel_transformation": ["保险 渠道 变革 报告", "保险中介 白皮书"],
    "capital_reinsurance": ["再保险 报告", "偿付能力 报告"],
    "climate_catastrophe": ["巨灾保险 报告", "气候变化 保险 研究"],
    "digital_transformation": ["保险 数字化 白皮书", "保险科技 报告"],
    "regulatory_change": ["保险 监管 报告", "保险业 政策 研究"],
}

# 方向关键词（搜索/主题页结果须在标题命中至少一个，防止跑题；避免超短英文词防误匹配）
TOPIC_KEYWORDS = {
    "ai_intelligent": ["artificial intelligence", "machine learning", "llm", "genai",
                       "人工智能", "大模型", "智能核保", "智能理赔"],
    "pension_finance": ["pension", "retirement", "aging", "longevity",
                        "养老", "养老金", "年金"],
    "product_innovation": ["parametric", "product innovation",
                           "产品创新", "健康险", "惠民保"],
    "channel_transformation": ["distribution", "bancassurance", "agent", "intermediary",
                               "渠道", "中介", "经代", "银保", "代理人"],
    "capital_reinsurance": ["reinsurance", "solvency", "m&a", "capital market",
                            "再保险", "偿付能力", "并购"],
    "climate_catastrophe": ["climate", "catastrophe", "natural disaster", "flood", "typhoon", "earthquake",
                            "气候", "巨灾", "自然灾害", "台风", "地震"],
    "digital_transformation": ["digital", "insurtech", "transformation",
                               "数字化", "数智", "线上化"],
    "regulatory_change": ["regulation", "regulator", "compliance", "supervisory",
                          "监管", "合规", "政策"],
}

# 方向专属主题页（扩展点：按方向补充已验证的机构主题页；国际机构站多为 JS 渲染，
# 静态抓取产出有限，主要靠 iachina 主源 + 搜狗方向搜索 + 缺口报告引导人工补充）
TOPIC_SOURCES = {
    "climate_catastrophe": [
        {"name": "Lloyd's Risk Reports", "institution_cn": "劳合社", "layer": "reinsurance",
         "kind": "page", "url": "https://www.lloyds.com/news-and-risk-insight/risk-reports"},
    ],
    "pension_finance": [
        {"name": "Swiss Re sigma Research", "institution_cn": "瑞再研究院", "layer": "reinsurance",
         "kind": "page", "url": "https://www.swissre.com/institute/research/sigma-research.html"},
    ],
}


def topic_coverage(reports):
    """8 个方向各自的报告条数（auto 与 curated 都计入）。"""
    cov = {t: 0 for t in TOPIC_QUERIES}
    for r in reports:
        t = r.get("topic")
        if t in cov:
            cov[t] += 1
    return cov


def weak_topics(reports, min_per=RESEARCH_TOPIC_MIN):
    """低于目标条数的方向列表。"""
    return [t for t, n in topic_coverage(reports).items() if n < min_per]


def _hits_topic(title, topic):
    """标题是否命中该方向关键词。"""
    t = (title or "").lower()
    return any(k.lower() in t for k in TOPIC_KEYWORDS.get(topic, []))


def direction_search(topic, per_q=3):
    """搜狗定向搜索薄弱方向：搜索 → 真实 URL → 方向词命中过滤（三重门控在 build_report 中）。"""
    cands = []
    opener = collect._sogou_session()
    for q in TOPIC_QUERIES.get(topic, [])[:2]:
        try:
            url = "https://news.sogou.com/news?query=" + urllib.parse.quote_plus(q)
            page = opener.open(url, timeout=TIMEOUT).read().decode("utf-8", "ignore")
            if "验证码" in page or "antispider" in page:
                print("    ⚠ 搜狗反爬，方向搜索跳过")
                break
            for href, title in collect.parse_sogou_results(page)[:per_q]:
                real = collect.resolve_sogou_link(opener, href, url)
                if not real:
                    continue
                if _hits_topic(title, topic):
                    cands.append({"title": title, "link": real, "summary": "", "published": ""})
            time.sleep(1.5)
        except Exception:
            continue
    return cands


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


def build_report(cands, src, topic_override=None):
    """候选条目经三重门控后结构化（auto=True）。URL 白名单信息优先于源清单。
    topic_override：方向补充场景下强制归属到触发补充的方向。"""
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
        topic = topic_override or collect.infer_topic(title, summary) or "product_innovation"
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

    # —— 方向驱动补充：对低于目标条数的方向定向补缺 ——
    weak = weak_topics(merged)
    if weak:
        print(f"方向缺口：{', '.join(weak)} → 启动定向补充")
        supp = []
        for t in weak:
            for src in TOPIC_SOURCES.get(t, []):
                cands = fetch_source(src)
                rs = [r for r in build_report(cands, src)
                      if r["topic"] == t or _hits_topic(r["title"], t)]
                print(f"    · 主题页 {src['name']}：候选 {len(cands)} → 方向命中 {len(rs)}")
                supp.extend(rs)
            found = direction_search(t)
            rs = build_report(found, {"name": f"direction:{t}"}, topic_override=t)
            print(f"    · 方向搜索 {t}：候选 {len(found)} → 通过门控 {len(rs)}")
            supp.extend(rs)
        if supp:
            merged, added2 = merge(supp, {"reports": merged})
            added += added2
            print(f"方向补充新增：{added2} 条")

    # 预览
    for r in collected + (supp if weak else []):
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

    # —— 方向覆盖报告：每方向条数 vs 目标 ——
    labels = existing.get("topics", {})
    cov = topic_coverage(merged)
    gaps = []
    print(f"—— 方向覆盖（目标每方向 ≥{RESEARCH_TOPIC_MIN} 条）——")
    for t, n in cov.items():
        if n >= RESEARCH_TOPIC_MIN:
            print(f"  ✓ {labels.get(t, t)}: {n}")
        else:
            print(f"  ⚠ {labels.get(t, t)}: {n}（缺口 {RESEARCH_TOPIC_MIN - n}）")
            gaps.append(t)
    if gaps:
        print(f"💡 补齐建议：{', '.join(labels.get(t, t) for t in gaps)} "
              f"可经 inbox.json / MCP 辅助搜索后人工精编补充")


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
