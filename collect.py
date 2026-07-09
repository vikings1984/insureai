#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
InsureAI 自动采集管道 (collect.py)
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
import urllib.parse
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

# ===================== 配置 =====================
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data.json")
INBOX_PATH = os.path.join(HERE, "inbox.json")
TIMEOUT = 12
UA = "Mozilla/5.0 (compatible; InsureAIBot/1.0; +https://github.com/vikings1984/insureai)"

# 通道 1：RSS 信源（国际权威英文信源为主通道）
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

# 强保险领域信号词（RSS 入册门控，剔除非保险新闻：泛事故/政务/体育等）
# 刻意排除 policy/claim/report/data/product/digital/capital 等过于泛化的词，
# 因为它们会误命中 "claims three lives"(船只倾覆)、"training requirement"(地方政务) 等噪声。
STRONG_INSURANCE_TERMS = [
    "insurance", "insurer", "insurers", "insured", "reinsurance", "reinsurer",
    "reinsurers", "underwrit", "premium", "premiums", "annuity", "annuities",
    "solvency", "insurtech", "parametric", "broker", "underwriter", "underwriters",
    "actuary", "actuaries", "catastrophe", "catastrophic", "ils", "captive",
    "treaty", "retrocession", "mga", "loss ratio", "combined ratio", "policyholder",
    "policyholders", "bancassurance", "indemnity", "ceding", "cedent",
    "facultative", "proportional", "excess of loss", "insurable", "broking",
    "peril", "lapse", "subrogation", "binding authority", "insurability",
    "保险", "再保险", "承保", "理赔", "保费", "保单", "偿付能力", "年金", "巨灾",
    "险资", "银保", "核保", "责任险", "财险", "寿险", "健康险", "车险", "农险",
    "投保人", "被保险人", "保险人", "精算", "经纪", "中介", "养老", "养老金",
    "代理", "投保", "给付", "免赔", "免责", "险企", "险业", "保险业", "再保",
    "惠民保", "参保", "保险资金", "险资", "保险科技", "智能核保", "智能理赔",
    "互联网保险", "保险代理人", "新能源车险", "健康险", "责任险", "财产险",
]


def is_insurance_relevant(title, summary):
    """RSS 入册门控：标题/摘要须含强保险领域信号，否则视为噪声不入册。"""
    text = (title + " " + summary).lower()
    return any(t in text for t in STRONG_INSURANCE_TERMS)


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


def clean_text(t):
    """去除 HTML 标签与多余空白，用于中文搜索结果标题/摘要清洗（不截断）。"""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()


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


# ===================== 中文保险资讯源（东方财富搜索 API） =====================
# 零额外依赖（标准库 urllib）。中文保险站点普遍无公开 RSS，故用搜索 API 补齐中文内容，
# 解决默认英文 RSS 与中文“保险日报”标题的错位。用 is_insurance_relevant 双重门控防噪声。
# 关键词覆盖全部 8 大研究主题 + 主要产品线，确保中文内容分类均衡、无主题盲区。
EASTMONEY_KEYWORDS = [
    ("保险", "industry"),
    ("再保险", "capital_reinsurance"),
    ("养老金融", "pension_finance"),
    ("车险", "product_innovation"),
    ("健康险", "product_innovation"),
    ("保险监管", "regulation"),
    ("保险科技", "digital_transformation"),
    ("巨灾保险", "climate_catastrophe"),
    ("农业保险", "industry"),                # 农险领域
    ("保险资金", "capital_reinsurance"),     # 资管/投资维度
    ("保险AI", "ai_intelligent"),            # AI 智能化
    ("智能核保", "ai_intelligent"),          # AI 智能化（核保场景）
    ("互联网保险", "channel_transformation"),# 渠道转型
    ("保险代理人", "channel_transformation"),# 渠道转型（代理人）
    ("惠民保", "product_innovation"),        # 产品创新（城市定制医疗险）
    ("新能源车险", "product_innovation"),    # 产品创新（新能源车）
    # —— 弱分类专属搜索词（claims/product 占比偏低，加权提升覆盖）——
    ("保险理赔", "claims"),                  # 理赔实务（弱分类）
    ("重疾险", "product_innovation"),        # 产品创新
    ("百万医疗", "product_innovation"),       # 产品创新
    ("养老年金", "pension_finance"),         # 养老
    ("防癌险", "product_innovation"),         # 产品创新
]

# 分类均衡优化：弱分类(理赔/产品)搜索词加权，提升其采集覆盖（默认 per_kw=3）。
EASTMONEY_KW_WEIGHT = {
    "惠民保": 5, "新能源车险": 5, "保险理赔": 6, "重疾险": 5,
    "百万医疗": 5, "养老年金": 5, "防癌险": 5,
    "健康险": 4, "车险": 4, "养老金融": 4,
}
EASTMONEY_API = "https://search-api-web.eastmoney.com/search/jsonp?cb=jQuery&param="


def fetch_eastmoney(per_kw=3):
    """通过东方财富搜索 API 获取中文保险资讯。返回标准条目字典列表。
    每个关键词的每页条数由 EASTMONEY_KW_WEIGHT 覆盖（弱分类加权）。"""
    items = []
    for kw, _hint in EASTMONEY_KEYWORDS:
        kw_per = EASTMONEY_KW_WEIGHT.get(kw, per_kw)
        param = json.dumps({
            "uid": "", "keyword": kw, "type": ["cmsArticleWebOld"],
            "client": "web", "clientType": "web", "clientVersion": "curr",
            "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default",
                       "pageIndex": 1, "pageSize": kw_per, "preTag": "", "postTag": ""}}
        }, ensure_ascii=False)
        url = EASTMONEY_API + urllib.parse.quote(param)
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": "https://search.eastmoney.com/"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                txt = r.read().decode("utf-8", "ignore")
            m = re.search(r"jQuery[\w]*\((.*)\)", txt, re.S)
            if not m:
                continue
            data = json.loads(m.group(1))
            arts = data.get("result", {}).get("cmsArticleWebOld", [])
            for a in arts:
                title = clean_text(a.get("title", ""))
                if not title or len(title) < 6:
                    continue
                content = clean_text(a.get("content", ""))
                # 搜索召回噪声二次门控：搜索 API 会返回与关键词弱相关的结果
                # （如「智能核保」召回「星尘智能完成股改」），须含强保险信号才入册。
                if not is_insurance_relevant(title, content):
                    continue
                pub = (a.get("date", "") or "")[:10]
                pub_iso = (pub + "T00:00:00+08:00") if pub else to_iso(None)
                items.append({
                    "title": title,
                    "summary": content[:200] or title,
                    "url": a.get("url", ""),
                    "source_name": a.get("mediaName", "东方财富"),
                    "source_type": "api",
                    "authority": 82,
                    "published_at": pub_iso,
                    "language": "zh",
                })
        except Exception as e:
            print(f"  ⚠ 东方财富搜索 '{kw}' 失败: {e}")
    return items


# ===================== 中文权威行业源（中国保险行业协会官网） =====================
# 独立于东方财富的「聚合」模式，直接抓取保险行业协会官网（行业协会/监管一手信源）。
# 标准库 urllib，零额外依赖；首页即保险资讯流，文章页 <meta description> 可作摘要。
# 与东方财富形成「聚合媒体 + 一手行业源」的真正渠道多样化。
IACHINA_HOME = "https://www.iachina.cn/"
IACHINA_HOST = "https://www.iachina.cn"


def _iachina_summary(url):
    """抓取协会文章页 <meta name=description> 作为摘要（失败则回退空串）。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": IACHINA_HOME})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            t = r.read().decode("utf-8", "ignore")
        m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', t, re.I)
        if m:
            s = html.unescape(m.group(1)).strip()
            if len(s) >= 10:
                return s[:220]
    except Exception:
        pass
    return ""


def fetch_iachina(per_art=10):
    """中国保险行业协会官网（权威行业源）。返回标准条目字典列表。"""
    items = []
    seen_paths = set()
    try:
        req = urllib.request.Request(IACHINA_HOME, headers={"User-Agent": UA, "Referer": IACHINA_HOME})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            home = r.read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"  ⚠ 中国保险行业协会首页获取失败: {e}")
        return items
    # 仅取官网内部 /art/ 文章链接（排除首页混入的 nfra 等外链）
    links = re.findall(
        r'<a[^>]+href="(?:https?://www\.iachina\.cn)?(/art/[^"]+\.html)"[^>]*>(.*?)</a>',
        home, re.S)
    candidates = []
    for path, raw in links:
        if path in seen_paths:
            continue
        seen_paths.add(path)
        title = clean_text(raw)
        if len(title) < 10:
            continue
        # 协会官网几乎全为保险内容，仍用强信号二次门控防菜单/导航噪声
        if not is_insurance_relevant(title, ""):
            continue
        # 发布日期直接来自 URL 路径 /art/YYYY/M/D/
        dm = re.search(r'/art/(\d{4})/(\d{1,2})/(\d{1,2})/', path)
        pub_iso = (f"{int(dm.group(1)):04d}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
                   f"T00:00:00+08:00") if dm else to_iso(None)
        candidates.append({"title": title, "url": IACHINA_HOST + path, "published_at": pub_iso})
    # 取前 per_art 条，抓正文摘要（按首页顺序，大致最新在前）
    for c in candidates[:per_art]:
        summary = _iachina_summary(c["url"]) or c["title"]
        items.append({
            "title": c["title"],
            "summary": summary,
            "url": c["url"],
            "source_name": "中国保险行业协会",
            "source_type": "行业协会",
            "authority": 90,
            "published_at": c["published_at"],
            "language": "zh",
        })
    return items


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
    """分类逻辑（5 类）。industry 为兜底类——任何未命中具体规则的内容归入 industry，
    故具体类关键词必须足够精准，避免 industry 过度膨胀（分类均衡优化）。"""
    text = (title + " " + summary).lower()
    # 1) 监管（最具体，优先避免误归类）
    if any(k in text for k in ["监管", "办法", "指引", "处罚", "合规", "政策", "regulation", "compliance",
                               "regulator", "fine", "ifrs", "行政处罚", "金融监管总局"]):
        return "regulation"
    # 2) 理赔（保险实务核心；用精准词，避免"案例/纠纷/判决"等泛词误命中）
    if any(k in text for k in ["理赔", "赔付", "赔款", "索偿", "保险欺诈", "反欺诈", "车险理赔",
                               "健康险理赔", "医疗险理赔", "理赔服务", "理赔案例", "理赔纠纷",
                               "理赔时效", "快赔", "claim", "lawsuit", "settlement", "verdict", "claims"]):
        return "claims"
    # 3) 产品（产品创新/上市/备案）
    if any(k in text for k in ["产品", "首发", "推出", "上线", "惠民保", "新能源车险", "重疾险",
                               "百万医疗", "养老年金", "防癌险", "宠物险", "专属商业养老",
                               "创新型产品", "备案", "新品", "产品升级", "产品上市",
                               "launch", "unveils", "introduces", "product"]):
        return "product"
    # 4) 研究（研报/分析/趋势）
    if any(k in text for k in ["研报", "报告", "研究表明", "sigma", "白皮书", "咨询", "咨询报告",
                               "分析", "洞察", "趋势", "展望", "解读", "深度", "测算", "研究",
                               "report", "research", "whitepaper", "study"]):
        return "research"
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

    # 通道 3：中文搜索 API（东方财富，零额外依赖）— 补齐中文内容，解决中英文错位
    try:
        zh_items = fetch_eastmoney(per_kw=3)
        for it in zh_items:
            _ingest(it["title"], it["summary"], it["url"], it["source_name"], it["source_type"],
                    it["authority"], it["published_at"], existing_titles, collected,
                    require_topic=True)
        source_health["东方财富搜索"] = {"count": len(zh_items), "ok": True}
        print(f"  🈶 中文源(东方财富): {len(zh_items)} 条")
    except Exception as e:
        source_health["东方财富搜索"] = {"count": 0, "ok": False}
        print(f"  ⚠ 中文源采集失败: {e}")

    # 通道 4：中国保险行业协会官网（权威行业一手源，独立于东方财富聚合）
    try:
        ia_items = fetch_iachina(per_art=10)
        for it in ia_items:
            _ingest(it["title"], it["summary"], it["url"], it["source_name"], it["source_type"],
                    it["authority"], it["published_at"], existing_titles, collected,
                    require_topic=True)
        source_health["中国保险行业协会"] = {"count": len(ia_items), "ok": True}
        print(f"  🏛 中文源(保险行业协会): {len(ia_items)} 条")
    except Exception as e:
        source_health["中国保险行业协会"] = {"count": 0, "ok": False}
        print(f"  ⚠ 保险行业协会采集失败: {e}")

    # 合并
    merged = existing + collected
    merged.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    # 分类均衡优化：用最新 _category 逻辑对所有条目重跑分类，
    # 使历史条目的分类随逻辑改进而修正（改进可持久化到每日 CI）。
    for n in merged:
        n["category"] = _category(n.get("title", ""), n.get("summary", ""))
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


# ---- 自动推荐理由生成（内容感知、低模板化）----
_CATEGORY_CN = {
    "regulation": "监管动态",
    "product": "产品创新",
    "industry": "行业动态",
    "research": "研究洞察",
    "claims": "理赔服务",
}

# 主题关键词 -> (短标签, 价值说明从句，无句末标点)。
# 命中不同关键词即生成不同理由，避免千篇一律；从句尽量点出“为什么值得看”。
_THEME_HINTS = [
    (("评级", "outlook", "outlook to", "credit rating", "downgrade", "upgrade", "revised", "affirmed", "stable", "negative", "positive", "AM Best", "Moody's", "S&P", "Fitch", "标普", "穆迪", "惠誉"), "评级与信用观察", "评级机构对保险公司的信用与展望调整，直接影响融资成本与市场信心"),
    (("war", "conflict", "attack", "military", "Hormuz", "Strait", "vessel", "shipping", "geopolitical", "sanctions", "naval", "maritime"), "地缘政治与战争风险", "地缘冲突与航运袭击事件考验特殊风险与战争险的定价及承保边界"),
    (("mutual", "mutuals", "reciprocal", "brotherhood"), "相互保险", "相互保险组织的资本结构与会员治理模式，为中小险企提供差异化参照"),
    (("美国财险", "美国财产险", "US property", "commercial insurance", "property insurance", "property and casualty"), "美国财险市场", "美国财产险市场的费率、承保与诉讼环境变化，具跨境参照价值"),
    (("新能源车险", "新能源汽车", "EV", "electric", "motor"), "新能源车险", "新能源车的赔付结构与风险特征不同于燃油车，定价与风控模型正在重构"),
    (("养老", "养老金", "年金", "长护", "专属商业养老", "第三支柱", "pension", "retirement", "annuity", "longevity"), "养老与长期护理", "应对人口老龄化的第三支柱与长护险制度建设进入加速期"),
    (("健康险", "医疗险", "重疾", "百万医疗", "防癌", "带病体", "health", "medical", "life"), "健康险", "健康险从规模扩张转向精细化定价、带病体拓展与健康管理服务"),
    (("巨灾", "农险", "指数保险", "农业保险", "气候风险", "参数化", "catastrophe", "nat cat", "cat bond", "parametric", "climate", "flood", "hurricane", "wildfire", "cyclone"), "巨灾与农业保险", "气候风险上升推动指数化、参数化理赔在农险与巨灾险中普及"),
    (("偿付能力", "资本", "充足率", "风险综合评级", "solvency", "capital"), "偿付能力", "资本约束直接决定险企的展业空间与产品设计节奏"),
    (("大模型", "智能体", "人工智能", "智能核保", "智能理赔", "保险科技", "数字化", "insurtech", "automation"), "保险科技与 AI", "大模型与智能体正重塑核保、理赔与客户服务的作业方式"),
    (("监管", "办法", "指引", "行政处罚", "合规", "金融监管总局", "监管规则", "regulat", "compliance", "law", "ruling", "法案"), "监管合规", "监管规则持续细化，划定业务创新的合规边界"),
    (("理赔", "赔付", "反欺诈", "欺诈", "快赔", "代位", "claims", "settlement", "lawsuit", "fraud"), "理赔服务", "理赔时效与反欺诈能力是客户体验与险企风控的核心"),
    (("渠道", "中介", "代理人", "银保", "互联网保险", "broker", "agency"), "渠道变革", "互联网与中介渠道占比提升，倒逼传统代理人渠道转型"),
    (("再保险", "sigma", "瑞再", "慕再", "reinsurance", "retro", "treaty", "retrocession"), "再保险", "再保险续约价格与资本供需，决定直保公司的风险转移成本"),
    (("出口信用", "信用保险", "一带一路", "credit insurance", "trade credit"), "信用保险", "信用保险为外贸与跨境投资提供风险缓冲"),
    (("康养", "居家养老", "医养"), "康养与医养结合", "康养与医养结合正成为“保险+服务”生态的主要落地方向"),
    (("ILS", "cat bond", "spread", "层"), "保险连接证券(ILS)", "巨灾债券与参数化转移工具，为再保险资本提供另类供给"),
    (("cyber", "勒索", "网络安全"), "网络安全保险", "勒索与数据风险上升，推动网络安全险承保规则重构"),
    (("ESG", "green", "sustainab", "绿色"), "气候与 ESG", "气候与 ESG 议题正重塑保险资金投向与风险敞口"),
    (("insurtech", "startup", "融资", "funding", "venture"), "保险科技融资", "保险科技创企与融资动向，反映行业数字化投入方向"),
]

# 分类兜底价值说明（未命中具体主题时使用）
_CAT_VALUE = {
    "regulation": "对行业合规经营与业务边界具有指引意义",
    "product": "反映保险产品在保障责任与形态上的创新方向",
    "claims": "关乎理赔体验与保险欺诈治理的实务进展",
    "research": "提供数据与方法论，可作为研判行业走势的参考",
    "industry": "反映保险市场格局与经营环境的最新变化",
}

# 来源级主题提示：对标题/摘要未命中关键词、但来源本身有稳定定位的条目（如英文聚合源）兜底，
# 避免落入泛化分类句。只给定位高度聚焦的来源兜底；综合性门户不兜底，防止千篇一律。
_SOURCE_HINTS = {
    "Reinsurance News": ("再保险", "再保险续约价格与资本供需，决定直保公司的风险转移成本"),
    "Artemis (ILS)": ("保险连接证券(ILS)", "巨灾债券与参数化工具，为再保险资本提供另类供给"),
    "Swiss Re": ("再保险", "瑞再的 sigma 报告与巨灾数据，是直保产品设计的风标"),
    "Munich Re": ("再保险", "慕再的巨灾与定价观点，对再保险周期有指示意义"),
}

# 多种开篇句式，按标题稳定校验和选择，保证重跑幂等、且不同条目句式不一
_OPENERS_THEME = [
    "本文聚焦{label}，{clause}。",
    "围绕{label}，{clause}。",
    "{label}是本期值得关注的方向：{clause}。",
    "从{label}切入，{clause}。",
]
_OPENERS_CAT = [
    "这是一条{ccat}资讯，{clause}。",
    "{ccat}方面，{clause}。",
    "本期{ccat}值得留意：{clause}。",
]

# 高相关度时的关注提示（仅高分添加；用句式池避免每条都出现造成新模板）
_ATTENTION_HIGH = [
    "内容相关度高，建议优先关注。",
    "信息密度高，值得重点阅读。",
    "对把握行业动向具有较高价值。",
]
_ATTENTION_MID = [
    "具有较高行业参考价值。",
    "可作为了解行业动态的切入。",
    "值得从业人员留意。",
]


def _stable_idx(s, n=4):
    """稳定校验和（不依赖 hash seed），保证脚本多次运行选择一致、CI 幂等。"""
    return sum(ord(c) for c in s) % n


def _match_theme(title, summary):
    text = (title + " " + (summary or "")).lower()
    for kws, label, clause in _THEME_HINTS:
        if any(k.lower() in text for k in kws):
            return label, clause
    return None, None


def _source_prefix(sname, stype):
    """为权威/一手来源生成自然的前置表述；普通媒体省略以免模板化。"""
    if not sname:
        return ""
    notable = (stype in ("监管机构", "监管", "协会", "研究机构", "咨询")
               or any(k in sname for k in ("总局", "协会", "研究院", "再保险", "学会", "银保监")))
    return f"据{sname}披露，" if notable else ""


def auto_reason(title, summary, sname, stype, category, ai_score, topic=None):
    """为自动采集条目生成内容感知、低模板化的推荐理由。

    以文章标题/摘要中的真实主题词驱动，配合分类价值与来源可信度；
    句式按标题稳定校验和变化，保证 CI 重跑幂等、且不同条目读感不一。
    """
    cat_cn = _CATEGORY_CN.get(category, "行业动态")
    label, clause = _match_theme(title, summary)
    if not label:
        sh = _SOURCE_HINTS.get(sname)
        if sh:
            label, clause = sh
    if label:
        lead = _OPENERS_THEME[_stable_idx(title, len(_OPENERS_THEME))].format(label=label, clause=clause)
    else:
        lead = _OPENERS_CAT[_stable_idx(title, len(_OPENERS_CAT))].format(
            ccat=cat_cn, clause=_CAT_VALUE.get(category, _CAT_VALUE["industry"]))
    prefix = _source_prefix(sname, stype)
    if ai_score >= 88:
        tail = _ATTENTION_HIGH[_stable_idx(title, len(_ATTENTION_HIGH))]
    elif ai_score >= 80:
        tail = _ATTENTION_MID[_stable_idx(title, len(_ATTENTION_MID))]
    else:
        tail = ""
    return (prefix + lead + tail).strip()


def _ingest(title, summary, url, sname, stype, authority, published, existing_titles, collected, reason=None, require_topic=False):
    if not title or is_dup(title, existing_titles + [c["title"] for c in collected]):
        return
    topic = infer_topic(title, summary)
    if require_topic and not is_insurance_relevant(title, summary):
        return  # RSS 噪声过滤：不含强保险领域信号则不收录（剔除非保险新闻）
    cat = _category(title, summary)
    sc = score_item(title, summary, authority)
    collected.append({
        "id": 0,
        "title": title,
        "summary": summary or title,
        "source_name": sname,
        "source_type": stype,
        "source_url": url,
        "importance": 4,
        "ai_score": sc,
        "tags": "",
        "category": cat,
        "published_at": published,
        "reason": reason or auto_reason(title, summary, sname, stype, cat, sc, topic),
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
    print(f"=== InsureAI 采集管道 (dry={dry}, limit={limit}) ===")
    t0 = time.time()
    run(dry_run=dry, per_source_limit=limit)
    print(f"耗时 {time.time() - t0:.1f}s")
