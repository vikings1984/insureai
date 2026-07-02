#!/usr/bin/env python3
"""InsureAI 高质量数据采集 Pipeline
多源采集 + 智能分类 + 新鲜度过滤

数据源优先级：
1. 东方财富搜索 API（主源）— 多关键词搜索，覆盖全分类，当天新闻
2. AkShare 开源接口（补充源）— 个股新闻 + CCTV 新闻联播
3. 中国保险行业协会（辅源）— 协会要闻 + 行业动态
4. 降级数据（兜底）— 真实采集全部失败时
"""

import asyncio
import html as html_module
import json
import os
import re
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urljoin
from zoneinfo import ZoneInfo

import httpx

# ===== 项目路径 =====
def _find_project_root():
    if "GITHUB_WORKSPACE" in os.environ:
        return Path(os.environ["GITHUB_WORKSPACE"])
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "docs" / "index.html").exists():
            return p
        p = p.parent
    return Path.cwd()

PROJECT_ROOT = _find_project_root()
SUMMARIES_DIR = PROJECT_ROOT / "data" / "summaries"
DOCS_POSTS = PROJECT_ROOT / "docs" / "_posts"
SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
DOCS_POSTS.mkdir(parents=True, exist_ok=True)

# 加载配置
CONFIG_PATH = PROJECT_ROOT / "data" / "config.json"
_config_cache = None
def _load_config():
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    try:
        _config_cache = json.loads(CONFIG_PATH.read_text("utf-8"))
    except Exception:
        _config_cache = {}
    return _config_cache

# ===== 数据源配置 =====
EASTMONEY_SEARCH_KEYWORDS = [
    {"keyword": "保险", "category_hint": "", "page_size": 12},
    {"keyword": "保险监管", "category_hint": "regulation", "page_size": 12},
    {"keyword": "保险产品", "category_hint": "product", "page_size": 10},
    {"keyword": "保险理赔", "category_hint": "claims", "page_size": 12},
    {"keyword": "保险科技", "category_hint": "research", "page_size": 10},
    {"keyword": "人身险", "category_hint": "product", "page_size": 5},
    {"keyword": "健康险", "category_hint": "product", "page_size": 5},
    {"keyword": "养老保险", "category_hint": "product", "page_size": 5},
    {"keyword": "险资运用", "category_hint": "industry", "page_size": 5},
    {"keyword": "偿付能力", "category_hint": "regulation", "page_size": 8},
    {"keyword": "金融监管总局", "category_hint": "regulation", "page_size": 8},
    {"keyword": "车险", "category_hint": "product", "page_size": 5},
    {"keyword": "保险消费者", "category_hint": "claims", "page_size": 5},
]

IACHINA_COLUMNS = [
    {"col": 22, "name": "中国保险行业协会", "category_hint": "industry"},
    {"col": 24, "name": "中国保险行业协会", "category_hint": "industry"},
]

# AkShare: 保险上市公司个股新闻（5家主要险企）
AKSHARE_STOCK_SYMBOLS = [
    {"code": "601318", "name": "中国平安", "category_hint": "industry"},
    {"code": "601628", "name": "中国人寿", "category_hint": "industry"},
    {"code": "601601", "name": "中国太保", "category_hint": "industry"},
    {"code": "601336", "name": "新华保险", "category_hint": "industry"},
    {"code": "601319", "name": "中国人保", "category_hint": "industry"},
]

# AkShare: CCTV 新闻联播（保险关键词过滤）
CCTV_INSURANCE_KEYWORDS = ["保险", "金融监管", "银保监", "偿付能力", "农险", "养老金"]

FRESHNESS_DAYS = 21  # 只保留最近 N 天的文章

# ===== 降级数据 =====
SOURCE_URLS = {
    "金融监管总局": "https://www.nfra.gov.cn/",
    "中国银行保险报": "https://www.cbimc.cn/",
    "36氪": "https://www.36kr.com/",
}

FALLBACK_DATA = [
    {"title": "金融监管总局发布《保险公司偿付能力监管规则》修订版",
     "url": SOURCE_URLS["金融监管总局"], "snippet": "国家金融监督管理总局近日发布偿付能力监管规则修订版，强化资本管理。",
     "source": "金融监管总局", "category": "regulation"},
    {"title": "新能源车险综合改革方案出台，保费有望下降15%-20%",
     "url": SOURCE_URLS["中国银行保险报"], "snippet": "车险综合改革方案通过UBI数据共享优化定价。",
     "source": "中国银行保险报", "category": "product"},
    {"title": "中国人寿上半年保费收入突破5000亿元",
     "url": SOURCE_URLS["中国银行保险报"], "snippet": "中国人寿上半年保费收入约5120亿元，同比增长8.3%。",
     "source": "中国银行保险报", "category": "industry"},
    {"title": "保险科技公司水滴完成D轮融资",
     "url": SOURCE_URLS["36氪"], "snippet": "水滴公司完成3亿美元D轮融资。",
     "source": "36氪", "category": "research"},
    {"title": "保险业上半年罚单破亿，虚假材料成重灾区",
     "url": SOURCE_URLS["中国银行保险报"], "snippet": "保险业累计罚单金额突破1.2亿元。",
     "source": "中国银行保险报", "category": "claims"},
]

# ===== 分类关键词 =====
CATEGORY_KEYWORDS = {
    "regulation": ["监管", "政策", "合规", "银保监", "金融监管", "处罚", "牌照", "偿付能力", "准备金", "通知", "管理办法", "约谈", "新规", "行政处罚", "立案调查", "指导"],
    "product": ["产品", "上线", "费率", "保费", "承保", "保险产品", "条款", "保障", "投保", "车险", "健康险", "寿险", "养老金", "农险", "分红", "万能险"],
    "industry": ["保险行业", "市场", "并购", "重组", "上市", "业绩", "保费收入", "融资", "估值", "经营", "成绩单", "总资产", "增长"],
    "research": ["研究", "精算", "模型", "风险", "保险科技", "InsurTech", "AI", "大数据", "人工智能", "算法", "科技保险", "数字"],
    "claims": ["理赔", "拒赔", "纠纷", "诉讼", "判例", "欺诈", "反欺诈", "消费者", "投诉", "调解", "赔付", "赔付率"],
}

AUTHORITY_SOURCES = ["中国证券报", "上海证券报", "证券时报", "新华财经", "人民日报", "中国经营报", "第一财经", "澎湃新闻", "券商中国", "北京商报"]

# 股市行情噪声关键词 — 标题中包含这些词的条目视为股市快讯而非行业资讯
STOCK_NOISE_KEYWORDS = [
    "板块拉升", "板块走强", "板块反弹", "板块震荡", "板块大涨", "板块下跌",
    "涨停", "跌停", "涨幅", "跌幅", "盘中走强", "午后走强", "持续走强",
    "大幅反弹", "持续反弹", "持续拉升", "强势拉升", "震荡拉升",
    "融资客", "净买入", "净卖出", "资金流入", "资金流出",
]

# 股市噪声豁免词 — 如果标题同时包含这些词则保留（说明是实质性内容）
STOCK_NOISE_EXEMPT = ["保险科技", "保险产品", "保险理赔", "保险监管", "偿付能力", "保险创新", "保险服务"]

# 非新闻来源黑名单 — 百度/搜索引擎结果中排除这些非新闻网站
BLACKLIST_DOMAINS = [
    "zhihu.com", "baike.baidu.com", "bilibili.com", "360doc.com",
    "wenku.baidu.com", "experience.baidu.com", "edu.baidu.com",
    "tieba.baidu.com", "douban.com", "segmentfault.com",
    "csdn.net", "jianshu.com", "cnblogs.com",
]
BLACKLIST_SOURCE_NAMES = [
    "知乎", "百度百科", "哔哩哔哩", "发表网", "发表云", "百度知道",
    "百度经验", "360doc", "豆瓣", "博客园", "CSDN", "简书",
    "百度文库", "百度贴吧",
]

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def clean_text(text: str) -> str:
    text = html_module.unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def is_stock_noise(title: str) -> bool:
    """检测标题是否为股市行情噪声（快讯而非行业资讯）"""
    if not title:
        return False
    # 豁免：包含实质性保险话题词的不过滤
    if any(kw in title for kw in STOCK_NOISE_EXEMPT):
        return False
    # 明确的股市噪声词
    if any(kw in title for kw in STOCK_NOISE_KEYWORDS):
        return True
    # 组合检测：保险板块 + 股市动词
    stock_verbs = ["拉升", "走强", "反弹", "涨停", "跌停", "震荡", "大涨", "下跌", "盘中", "午后", "持续", "暴力", "强势"]
    if "保险板块" in title and any(v in title for v in stock_verbs):
        return True
    # 融资数据类
    if "融资客" in title or "净买入" in title or "净卖出" in title:
        return True
    return False


def is_blacklisted(url: str, source_name: str) -> bool:
    """检测是否为非新闻来源（知乎/百科/论坛等）"""
    url_lower = (url or "").lower()
    for domain in BLACKLIST_DOMAINS:
        if domain in url_lower:
            return True
    for name in BLACKLIST_SOURCE_NAMES:
        if name in (source_name or ""):
            return True
    return False


def title_similarity(t1: str, t2: str) -> float:
    """计算两个标题的字符级相似度（Jaccard）"""
    if not t1 or not t2:
        return 0
    s1, s2 = set(t1), set(t2)
    inter = len(s1 & s2)
    union = len(s1 | s2)
    return inter / union if union > 0 else 0


def validate_url(url: str) -> str:
    """验证 URL 安全性，只允许 http/https 协议"""
    if not url or not isinstance(url, str):
        return ""
    url = url.strip()
    if re.match(r'^https?://', url, re.I):
        return url
    return ""


def assign_category(title: str, content: str, hint: str = "") -> str:
    if hint:
        return hint
    text = (title + " " + content).lower()
    scores = {cat: sum(1 for kw in kws if kw.lower() in text) for cat, kws in CATEGORY_KEYWORDS.items()}
    if max(scores.values()) == 0:
        return "industry"
    return max(scores, key=scores.get)


def assign_score(title: str, content: str, source_name: str, pub_date: str) -> tuple:
    text = (title + " " + content).lower()
    all_kw = [kw for kws in CATEGORY_KEYWORDS.values() for kw in kws]
    kw_count = sum(1 for kw in all_kw if kw.lower() in text)

    # 权威来源加分（最高1.0）
    authority = 1.0 if any(s in source_name for s in AUTHORITY_SOURCES) else 0
    # 内容长度加分（最高1.0）
    length_bonus = min(len(content) / 500, 1.0)

    # 新鲜度加分（当天3.5，3天内2.0，7天内1.0，14天内0.5）
    freshness_bonus = 0
    try:
        d = datetime.strptime(pub_date[:10], "%Y-%m-%d").date()
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        days_old = (today - d).days
        if days_old <= 0:
            freshness_bonus = 3.5
        elif days_old <= 1:
            freshness_bonus = 2.0
        elif days_old <= 3:
            freshness_bonus = 1.0
        elif days_old <= 7:
            freshness_bonus = 0.5
        elif days_old <= 14:
            freshness_bonus = 0.3
    except Exception:
        pass

    # 关键词匹配加分（每个关键词0.2，最高1.5）
    kw_bonus = min(kw_count * 0.2, 1.5)

    # 基础分3.0 + 各维度加分，满分10.0
    base = 3.0 + kw_bonus + authority + length_bonus + freshness_bonus
    score = min(round(base, 1), 10.0)
    relevance = min(round(0.3 + kw_count * 0.05, 2), 1.0)
    return score, relevance


def generate_reason(item: dict) -> str:
    title = item["title"][:30]
    cat = item.get("category", "industry")
    reasons = {
        "regulation": [f"监管动态：{title}，涉及行业合规与风险管理。", f"政策风向：{title}，影响保险公司经营策略。"],
        "product": [f"产品创新：{title}，反映保险产品设计新方向。", f"市场动态：{title}，对消费者有参考价值。"],
        "industry": [f"行业风向：{title}，反映保险行业发展趋势。", f"市场观察：{title}，有助于理解行业格局。"],
        "research": [f"技术前沿：{title}，推动行业数字化转型。", f"研究洞察：{title}，为行业创新提供支撑。"],
        "claims": [f"理赔动态：{title}，展示保险服务实践。", f"消费者权益：{title}，了解理赔服务最新动态。"],
    }
    pool = reasons.get(cat, reasons["industry"])
    return pool[sum(ord(c) for c in title) % len(pool)]


# ===== 东方财富搜索 API =====
async def fetch_eastmoney(client: httpx.AsyncClient) -> list[dict]:
    items = []
    for cfg in EASTMONEY_SEARCH_KEYWORDS:
        kw = cfg["keyword"]
        page_size = cfg["page_size"]
        param = json.dumps({
            "uid": "", "keyword": kw, "type": ["cmsArticleWebOld"],
            "client": "web", "clientType": "web", "clientVersion": "curr",
            "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default",
                       "pageIndex": 1, "pageSize": page_size, "preTag": "", "postTag": ""}}
        }, ensure_ascii=False)
        url = f"https://search-api-web.eastmoney.com/search/jsonp?cb=jQuery&param={quote(param)}"
        try:
            resp = await client.get(url, timeout=15)
            resp.raise_for_status()
            m = re.search(r'jQuery[\w]*\((.*)\)', resp.text, re.S)
            if not m:
                continue
            data = json.loads(m.group(1))
            articles = data.get("result", {}).get("cmsArticleWebOld", [])
            for a in articles:
                title = clean_text(a.get("title", ""))
                content = clean_text(a.get("content", ""))
                if not title or len(title) < 5:
                    continue
                items.append({
                    "title": title,
                    "url": a.get("url", ""),
                    "content": content[:500],
                    "source_name": a.get("mediaName", "东方财富"),
                    "source_type": "api",
                    "published_at": a.get("date", "")[:10],
                    "category_hint": cfg.get("category_hint", ""),
                    "language": "zh",
                })
            print(f"    ✅ '{kw}': {len(articles)} 篇")
            await asyncio.sleep(0.3)
        except Exception as e:
            print(f"    ⚠️ '{kw}': {e}")
    return items


# ===== iachina.cn 网页爬取 =====
async def fetch_iachina(client: httpx.AsyncClient) -> list[dict]:
    items = []
    for col_cfg in IACHINA_COLUMNS:
        col = col_cfg["col"]
        url = f"https://www.iachina.cn/col/col{col}/index.html"
        try:
            resp = await client.get(url, timeout=15)
            resp.raise_for_status()
            links = re.findall(r'href="(/art/\d+/\d+/\d+/art_\d+_\d+\.html)"[^>]*>([^<]+)', resp.text)
            seen = set()
            for link, title in links[:10]:
                title = clean_text(title)
                if not title or len(title) < 5:
                    continue
                full_url = urljoin("https://www.iachina.cn", link)
                if full_url in seen:
                    continue
                seen.add(full_url)
                dm = re.search(r'/art/(\d+)/(\d+)/(\d+)/', link)
                if not dm:
                    continue
                pub = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
                items.append({
                    "title": title,
                    "url": full_url,
                    "content": title,
                    "source_name": col_cfg["name"],
                    "source_type": "web",
                    "published_at": pub,
                    "category_hint": col_cfg.get("category_hint", ""),
                    "language": "zh",
                })
            print(f"    ✅ col{col}: {len(links)} 篇")
        except Exception as e:
            print(f"    ⚠️ col{col}: {e}")
    return items


# ===== AkShare 采集 =====
def fetch_akshare_stock_news() -> list[dict]:
    """通过 AkShare 获取保险上市公司个股新闻"""
    items = []
    try:
        import akshare as ak
    except ImportError:
        print("    ⚠️ AkShare 未安装，跳过个股新闻")
        return items

    for cfg in AKSHARE_STOCK_SYMBOLS:
        code = cfg["code"]
        name = cfg["name"]
        try:
            df = ak.stock_news_em(symbol=code)
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                title = str(row.get("新闻标题", "")).strip()
                content = str(row.get("新闻内容", "")).strip()
                if not title or len(title) < 5:
                    continue
                pub = str(row.get("发布时间", ""))[:10]
                items.append({
                    "title": title,
                    "url": str(row.get("新闻链接", "")),
                    "content": content[:500],
                    "source_name": str(row.get("文章来源", name)),
                    "source_type": "akshare",
                    "published_at": pub,
                    "category_hint": cfg.get("category_hint", ""),
                    "language": "zh",
                })
            print(f"    ✅ {name}({code}): {len(df)} 篇")
        except Exception as e:
            print(f"    ⚠️ {name}({code}): {e}")
    return items


def fetch_akshare_cctv_news() -> list[dict]:
    """通过 AkShare 获取央视新闻联播，按保险关键词过滤"""
    items = []
    try:
        import akshare as ak
    except ImportError:
        return items

    # 尝试今天和昨天的新闻联播
    for days_ago in [0, 1]:
        d = datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=days_ago)
        date_str = d.strftime("%Y%m%d")
        try:
            df = ak.news_cctv(date=date_str)
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                title = str(row.get("title", "")).strip()
                content = str(row.get("content", "")).strip()
                # 关键词过滤：只保留保险相关新闻
                text = title + content
                if not any(kw in text for kw in CCTV_INSURANCE_KEYWORDS):
                    continue
                items.append({
                    "title": title,
                    "url": f"https://tv.cctv.com/lm/xwlb/day/{date_str}.shtml",
                    "content": content[:500],
                    "source_name": "央视新闻联播",
                    "source_type": "akshare",
                    "published_at": d.isoformat(),
                    "category_hint": "regulation",
                    "language": "zh",
                })
            filtered_count = sum(1 for _, r in df.iterrows() if any(kw in str(r.get("title", "")) + str(r.get("content", "")) for kw in CCTV_INSURANCE_KEYWORDS))
            print(f"    ✅ CCTV {date_str}: {len(df)} 篇（筛选后 {filtered_count} 条保险相关）")
        except Exception as e:
            print(f"    ⚠️ CCTV {date_str}: {e}")
    return items


# ===== 百度新闻搜索 =====
BAIDU_SEARCH_KEYWORDS = [
    {"keyword": "保险", "category_hint": ""},
    {"keyword": "保险监管", "category_hint": "regulation"},
    {"keyword": "保险理赔", "category_hint": "claims"},
    {"keyword": "保险产品", "category_hint": "product"},
]

async def fetch_baidu_news(client: httpx.AsyncClient) -> list[dict]:
    """通过百度新闻搜索采集保险资讯（含重试逻辑）"""
    items = []
    mobile_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    for cfg in BAIDU_SEARCH_KEYWORDS:
        kw = cfg["keyword"]
        # 尝试两种URL格式：桌面版 + 移动版
        urls = [
            f"https://www.baidu.com/s?tn=news&wd={quote(kw)}&rn=10&cl=2",
            f"https://m.baidu.com/s?word={quote(kw)}&from=1099a&sa=tb&tn=news",
        ]
        html = None
        for url in urls:
            try:
                headers = {"User-Agent": mobile_ua} if "m.baidu.com" in url else {}
                resp = await client.get(url, timeout=15, headers=headers)
                resp.raise_for_status()
                page = resp.text
                if "百度安全验证" in page or "wappass.baidu.com" in page:
                    continue
                html = page
                break
            except Exception:
                continue
        if not html:
            print(f"    ⚠️ 百度'{kw}': 所有URL均被拦截")
            continue
        try:
            # 解析搜索结果
            results = re.findall(r'<a[^>]*href="(https?://[^"]*)"[^>]*>(.*?)</a>', html, re.S)
            # 过滤百度自身链接
            results = [(u, t) for u, t in results if "baidu.com" not in u and len(clean_text(re.sub(r'<[^>]+>', '', t))) > 5]
            # 提取摘要
            snippets = re.findall(r'<span class="c-color-text"[^>]*>(.*?)</span>', html, re.S)
            source_info = re.findall(r'<span class="c-color-gray"[^>]*>(.*?)</span>', html, re.S)
            
            count = 0
            for i, (link, title_html) in enumerate(results[:8]):
                title = clean_text(re.sub(r'<[^>]+>', '', title_html))
                if not title or len(title) < 5:
                    continue
                snippet = ""
                if i < len(snippets):
                    snippet = clean_text(re.sub(r'<[^>]+>', '', snippets[i]))
                source_name = "百度新闻"
                pub_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
                if i < len(source_info):
                    info_text = clean_text(re.sub(r'<[^>]+>', '', source_info[i]))
                    parts = info_text.split()
                    if parts:
                        source_name = parts[0]
                    date_match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', info_text)
                    if date_match:
                        pub_date = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
                    else:
                        days_match = re.search(r'(\d+)天前', info_text)
                        if days_match:
                            d = datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=int(days_match.group(1)))
                            pub_date = d.isoformat()
                        hours_match = re.search(r'(\d+)小时前', info_text)
                        if hours_match:
                            pub_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

                items.append({
                    "title": title,
                    "url": link,
                    "content": snippet[:500] if snippet else title,
                    "source_name": source_name,
                    "source_type": "baidu",
                    "published_at": pub_date,
                    "category_hint": cfg.get("category_hint", ""),
                    "language": "zh",
                })
                count += 1
            print(f"    ✅ 百度'{kw}': {count} 篇")
            await asyncio.sleep(1.0)
        except Exception as e:
            print(f"    ⚠️ 百度'{kw}'解析失败: {e}")
    return items


# ===== 今日头条搜索 =====
TOUTIAO_SEARCH_KEYWORDS = [
    {"keyword": "保险", "category_hint": ""},
    {"keyword": "保险监管", "category_hint": "regulation"},
    {"keyword": "保险理赔", "category_hint": "claims"},
]

async def fetch_toutiao_news(client: httpx.AsyncClient) -> list[dict]:
    """通过今日头条搜索采集保险资讯"""
    items = []
    for cfg in TOUTIAO_SEARCH_KEYWORDS:
        kw = cfg["keyword"]
        url = f"https://so.toutiao.com/search?keyword={quote(kw)}&pd=information&dvpf=pc"
        try:
            resp = await client.get(url, timeout=15)
            resp.raise_for_status()
            html = resp.text
            # 头条搜索结果解析
            # 提取标题和链接
            results = re.findall(r'<a[^>]*class="[^"]*result-title[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
            if not results:
                # 尝试另一种结构
                results = re.findall(r'<a[^>]*href="(https?://[^"]*toutiao[^"]*)"[^>]*>(.*?)</a>', html, re.S)
            
            count = 0
            for link, title_html in results[:8]:
                title = clean_text(re.sub(r'<[^>]+>', '', title_html))
                if not title or len(title) < 5:
                    continue
                if "保险" not in title and kw not in title:
                    continue
                # 提取摘要
                snippet_match = re.search(rf'{re.escape(title_html)}.*?<p[^>]*>(.*?)</p>', html, re.S)
                snippet = ""
                if snippet_match:
                    snippet = clean_text(re.sub(r'<[^>]+>', '', snippet_match.group(1)))
                
                items.append({
                    "title": title,
                    "url": link,
                    "content": snippet[:500] if snippet else title,
                    "source_name": "今日头条",
                    "source_type": "toutiao",
                    "published_at": datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
                    "category_hint": cfg.get("category_hint", ""),
                    "language": "zh",
                })
                count += 1
            print(f"    ✅ 头条'{kw}': {count} 篇")
            await asyncio.sleep(0.8)
        except Exception as e:
            print(f"    ⚠️ 头条'{kw}': {e}")
    return items


# ===== 搜狗微信公众号搜索 =====
SOGOU_WECHAT_KEYWORDS = [
    {"keyword": "保险", "category_hint": ""},
    {"keyword": "保险监管", "category_hint": "regulation"},
    {"keyword": "保险产品", "category_hint": "product"},
    {"keyword": "保险科技", "category_hint": "research"},
    {"keyword": "健康险", "category_hint": "product"},
    {"keyword": "养老保险", "category_hint": "product"},
]

async def fetch_sogou_wechat(client: httpx.AsyncClient) -> list[dict]:
    """通过搜狗微信搜索采集公众号保险文章（尽力而为）"""
    items = []
    for cfg in SOGOU_WECHAT_KEYWORDS:
        kw = cfg["keyword"]
        url = f"https://weixin.sogou.com/weixin?type=2&query={quote(kw)}&ie=utf8"
        try:
            wechat_headers = {
                **HTTP_HEADERS,
                "Referer": "https://weixin.sogou.com/",
                "Cookie": "SUV=00A0000000000001",
            }
            resp = await client.get(url, timeout=15, headers=wechat_headers)
            resp.raise_for_status()
            html = resp.text
            if "验证码" in html or "antispider" in html.lower():
                print(f"    ⚠️ 搜狗微信'{kw}': 触发验证码，跳过")
                continue
            # 解析搜索结果：提取文章链接、标题、日期
            # 搜狗微信结果块结构: <div class="txt-box"> ... <a href="link">title</a> ... <span class="s2">日期</span>
            results = re.findall(r'<a[^>]*target="_blank"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
            # 提取日期信息（格式: "YYYY-MM-DD" 或 "X天前" 或 "X小时前"）
            date_blocks = re.findall(r'<span[^>]*class="s2"[^>]*>(.*?)</span>', html, re.S)
            # 提取公众号账号名（class="all-time-y2" 的 span）
            account_names = re.findall(r'<span[^>]*class="all-time-y2"[^>]*>(.*?)</span>', html, re.S)
            # 提取 Unix 时间戳（timeConvert('XXXX') 格式）
            timestamps = re.findall(r"timeConvert\('(\d+)'\)", html)
            
            count = 0
            for i, (link, title_html) in enumerate(results[:8]):
                title = clean_text(re.sub(r'<[^>]+>', '', title_html))
                if not title or len(title) < 5:
                    continue
                if "保险" not in title and kw not in title:
                    continue
                # 提取公众号账号名
                source_name = "微信公众号"
                if i < len(account_names):
                    acct = clean_text(re.sub(r'<[^>]+>', '', account_names[i]))
                    if acct and len(acct) > 1:
                        source_name = f"公众号·{acct}"
                if not link.startswith("http"):
                    link = urljoin("https://weixin.sogou.com", link)
                # 解析日期：优先从 Unix 时间戳转换
                pub_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
                if i < len(timestamps):
                    try:
                        ts = int(timestamps[i])
                        dt = datetime.fromtimestamp(ts, tz=ZoneInfo("Asia/Shanghai"))
                        pub_date = dt.date().isoformat()
                    except Exception:
                        pass
                
                items.append({
                    "title": title,
                    "url": link,
                    "content": title,
                    "source_name": source_name,
                    "source_type": "wechat",
                    "published_at": pub_date,
                    "category_hint": cfg.get("category_hint", ""),
                    "language": "zh",
                })
                count += 1
            print(f"    ✅ 搜狗微信'{kw}': {count} 篇")
            await asyncio.sleep(1.5)
        except Exception as e:
            print(f"    ⚠️ 搜狗微信'{kw}': {e}")
    return items


# ===== 采集主流程 =====
async def collect_all() -> tuple[list[dict], bool, dict]:
    all_items = []
    real_count = 0
    source_health = {}

    print("📡 东方财富搜索 API（主源）...")
    async with httpx.AsyncClient(follow_redirects=True, headers=HTTP_HEADERS) as client:
        em_items = await fetch_eastmoney(client)
        all_items.extend(em_items)
        real_count += len(em_items)
        source_health["eastmoney"] = {"count": len(em_items), "ok": len(em_items) > 0}

        print("\n🌐 中国保险行业协会（辅源）...")
        ia_items = await fetch_iachina(client)
        all_items.extend(ia_items)
        real_count += len(ia_items)
        source_health["iachina"] = {"count": len(ia_items), "ok": len(ia_items) > 0}

        print("\n🔍 百度新闻搜索...")
        bd_items = await fetch_baidu_news(client)
        all_items.extend(bd_items)
        real_count += len(bd_items)
        source_health["baidu"] = {"count": len(bd_items), "ok": len(bd_items) > 0}

        print("\n📄 今日头条搜索...")
        tt_items = await fetch_toutiao_news(client)
        all_items.extend(tt_items)
        real_count += len(tt_items)
        source_health["toutiao"] = {"count": len(tt_items), "ok": len(tt_items) > 0}

        print("\n💬 搜狗微信公众号搜索...")
        wx_items = await fetch_sogou_wechat(client)
        all_items.extend(wx_items)
        real_count += len(wx_items)
        source_health["wechat"] = {"count": len(wx_items), "ok": len(wx_items) > 0}

    # AkShare 同步采集
    print("\n📊 AkShare 个股新闻（5家险企）...")
    ak_stock_items = await asyncio.to_thread(fetch_akshare_stock_news)
    all_items.extend(ak_stock_items)
    real_count += len(ak_stock_items)
    source_health["akshare_stock"] = {"count": len(ak_stock_items), "ok": len(ak_stock_items) > 0}

    print("\n📺 AkShare 央视新闻联播（保险关键词过滤）...")
    ak_cctv_items = await asyncio.to_thread(fetch_akshare_cctv_news)
    all_items.extend(ak_cctv_items)
    real_count += len(ak_cctv_items)
    source_health["akshare_cctv"] = {"count": len(ak_cctv_items), "ok": len(ak_cctv_items) > 0}

    # 去重（按 URL，无 URL 时按标题）+ 股市噪声过滤 + 黑名单过滤 + 标题相似度去重
    seen_urls = set()
    seen_titles = set()
    deduped = []
    noise_filtered = 0
    blacklist_filtered = 0
    for item in all_items:
        url = item.get("url", "")
        title = item.get("title", "")
        source_name = item.get("source_name", "")
        # 股市噪声过滤
        if is_stock_noise(title):
            noise_filtered += 1
            continue
        # 非新闻来源黑名单过滤
        if is_blacklisted(url, source_name):
            blacklist_filtered += 1
            continue
        # URL 去重
        if url:
            if url in seen_urls:
                continue
            seen_urls.add(url)
        elif title:
            if title in seen_titles:
                continue
            seen_titles.add(title)
        # 标题相似度去重（与已保留的条目比较）
        is_dup = False
        for kept in deduped:
            if title_similarity(title, kept.get("title", "")) > 0.5:
                is_dup = True
                break
        if is_dup:
            continue
        deduped.append(item)
    all_items = deduped
    if noise_filtered:
        print(f"  🚫 过滤股市噪声 {noise_filtered} 条")
    if blacklist_filtered:
        print(f"  🚫 过滤非新闻来源 {blacklist_filtered} 条")

    if real_count == 0:
        print("\n⚠️ 真实采集失败，启用降级数据...")
        today = date.today().isoformat()
        for fb in FALLBACK_DATA:
            all_items.append({
                "title": fb["title"], "url": fb["url"], "content": fb["snippet"],
                "source_name": fb["source"], "source_type": "fallback",
                "published_at": today, "category_hint": fb.get("category", ""), "language": "zh",
            })
        print(f"\n🏥 数据源健康: {json.dumps(source_health, ensure_ascii=False)}")
        return all_items, False, source_health

    # 新鲜度过滤
    cutoff = (datetime.now(ZoneInfo("Asia/Shanghai")).date()) - timedelta(days=FRESHNESS_DAYS)
    fresh = [i for i in all_items if i.get("published_at", "") >= cutoff.isoformat()]
    if not fresh:
        fresh = all_items  # 如果过滤后为空，保留全部

    print(f"\n📥 采集 {len(all_items)} 条 → 去重后 {len(deduped)} 条 → 近{FRESHNESS_DAYS}天 {len(fresh)} 条")
    print(f"\n🏥 数据源健康: {json.dumps(source_health, ensure_ascii=False)}")
    return fresh, True, source_health


def process_items(items: list[dict]) -> list[dict]:
    for item in items:
        title = clean_text(item["title"])
        content = clean_text(item["content"])
        item["title"] = title
        item["content"] = content
        item["category"] = assign_category(title, content, item.get("category_hint", ""))
        score, rel = assign_score(title, content, item["source_name"], item.get("published_at", ""))
        item["ai_score"] = score
        item["insurance_relevance"] = rel
        item["ai_tags"] = [kw for kw in CATEGORY_KEYWORDS.get(item["category"], [])[:3] if kw.lower() in (title + content).lower()]
        item["ai_reason"] = generate_reason(item)

    # 分类均衡加分：每个分类至少保证有内容
    cat_counts = {}
    for item in items:
        cat_counts[item["category"]] = cat_counts.get(item["category"], 0) + 1
    for item in items:
        cat = item["category"]
        if cat_counts.get(cat, 0) < 3:
            # 弱势分类加分，最高+1.0
            item["ai_score"] = min(item["ai_score"] + 1.0, 10.0)
    return items


def generate_output(items: list[dict], target_date: str, is_real: bool, source_health: dict = None):
    SOURCE_TYPE_MAP = {
        "api": "财经媒体", "web": "行业协会", "akshare": "财经媒体",
        "fallback": "兜底数据", "regulator": "监管机构", "company": "保险公司",
        "baidu": "搜索引擎", "toutiao": "头条资讯", "wechat": "微信公众号",
    }
    items.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
    # 渠道均衡：限制每个 source_type 最多占比 50%
    stype_counts = {}
    balanced = []
    for item in items:
        st = item.get("source_type", "")
        if stype_counts.get(st, 0) >= 15:  # 每个渠道最多15条
            continue
        stype_counts[st] = stype_counts.get(st, 0) + 1
        balanced.append(item)
    items = balanced[:30]  # 最多 30 条

    by_cat = {}
    for item in items:
        by_cat.setdefault(item["category"], []).append(item)

    curated = [i for i in items if i.get("ai_score", 0) >= 6.0]
    highlights = [i for i in curated if i.get("ai_score", 0) >= 7.0]

    cat_names = {"regulation": "🏛️ 监管政策", "product": "📦 产品发布", "industry": "📊 行业动态", "research": "🔬 研究洞察", "claims": "⚖️ 理赔案例"}
    src_tag = "真实多源采集" if is_real else "降级数据"

    # Markdown 日报
    zh = f"""---
layout: daily
title: "InsureAI 保险日报 - {target_date}"
date: {target_date}
lang: zh
---
# 📋 InsureAI 保险日报

**{target_date}** · {src_tag} · {len(curated)} 条精选 / {len(items)} 条总计

---
## ⭐ 今日重点 ({len(highlights)})

"""
    for item in highlights:
        zh += f"""### [{item['title']}]({item['url']})
**{item['ai_score']:.1f}** | {item['source_name']} | {cat_names.get(item['category'], item['category'])}

{item['content'][:200]}

> {item['ai_reason']}

---

"""
    for cat, cat_items in by_cat.items():
        cat_curated = [i for i in cat_items if i in curated]
        if not cat_curated:
            continue
        zh += f"## {cat_names.get(cat, cat)}\n\n"
        for item in cat_curated:
            zh += f"### [{item['title']}]({item['url']})\n**{item['ai_score']:.1f}** | {item['source_name']} | {item.get('published_at','')}\n\n{item['content'][:150]}\n\n---\n\n"
    zh += f"\n*InsureAI · {len(curated)} 条精选 · {src_tag}*\n"

    # 写入文件
    for path, content in [
        (SUMMARIES_DIR / f"{target_date}-zh.md", zh),
    ]:
        path.write_text(content, encoding="utf-8")
    (SUMMARIES_DIR / f"{target_date}.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    # data.json
    dj_path = PROJECT_ROOT / "docs" / "data.json"
    try:
        data = json.loads(dj_path.read_text("utf-8")) if dj_path.exists() else {}
    except Exception:
        data = {}
    if "days" not in data:
        data["days"] = {}

    today_news = [{
        "id": i + 1, "title": item["title"], "summary": item.get("content", "")[:300],
        "source_name": item["source_name"], "source_type": SOURCE_TYPE_MAP.get(item.get("source_type", ""), item.get("source_type", "web")),
        "source_url": validate_url(item.get("url", "")) or "#", "ai_score": round(item.get("ai_score", 0) * 10),
        "tags": ",".join(item.get("ai_tags", [])), "category": item.get("category", "industry"),
        "published_at": item.get("published_at", target_date), "reason": item.get("ai_reason", ""),
    } for i, item in enumerate(curated)]

    # 增量合并：保留近3天的历史新闻
    old_news = data.get("news", [])
    seen_urls = set(n.get("source_url", "") for n in today_news if n.get("source_url"))
    merged = list(today_news)
    for old_item in old_news:
        old_url = old_item.get("source_url", "")
        if old_url and old_url not in seen_urls:
            # 只保留近3天的历史
            try:
                old_date = old_item.get("published_at", "")[:10]
                if old_date >= (datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=3)).isoformat():
                    # 映射旧 source_type 为中文标签
                    old_item["source_type"] = SOURCE_TYPE_MAP.get(old_item.get("source_type", ""), old_item.get("source_type", "财经媒体"))
                    merged.append(old_item)
                    seen_urls.add(old_url)
            except Exception:
                pass
    # 限制总量100条
    data["news"] = merged[:100]

    data["days"][target_date] = {
        "total": len(items), "curated": len(curated), "highlights": len(highlights),
        "avg_score": round(sum(i.get("ai_score", 0) for i in curated) / max(len(curated), 1), 1),
        "categories": {c: len(ci) for c, ci in by_cat.items()},
        "sources": list(set(i["source_name"] for i in items)),
    }
    data["last_updated"] = datetime.now().isoformat()
    # 输出信源列表
    source_set = {}
    for item in items:
        sn = item.get("source_name", "")
        if sn and sn not in source_set:
            source_set[sn] = {
                "name": sn,
                "type": SOURCE_TYPE_MAP.get(item.get("source_type", ""), "财经媒体"),
                "score": 85 if sn in AUTHORITY_SOURCES else 75,
                "reason": f"采集自{sn}的保险行业资讯",
            }
    data["sources"] = list(source_set.values())[:10]
    data["data_source"] = "real" if is_real else "fallback"
    data["source_health"] = source_health or {}
    dj_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 统计
    print(f"\n{'='*50}")
    print(f"📊 采集统计 ({src_tag})")
    print(f"{'='*50}")
    print(f"  总计: {len(items)} | 精选: {len(curated)} | 重点: {len(highlights)}")
    print(f"  平均分: {sum(i.get('ai_score',0) for i in curated)/max(len(curated),1):.1f}")
    print(f"  分类: {', '.join(f'{c}={len(ci)}' for c, ci in by_cat.items())}")
    sources = {}
    for i in items:
        sources[i["source_name"]] = sources.get(i["source_name"], 0) + 1
    print(f"  来源({len(sources)}家): {', '.join(f'{k}={v}' for k,v in sorted(sources.items(), key=lambda x:-x[1])[:5])}")
    print(f"{'='*50}")


async def main():
    target = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    print(f"\n🚀 InsureAI 采集 Pipeline | {target}\n")
    items, is_real, source_health = await collect_all()
    if not items:
        print("⚠️ 无数据")
        return
    items = process_items(items)
    generate_output(items, target, is_real, source_health)


if __name__ == "__main__":
    asyncio.run(main())
