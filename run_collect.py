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
import ipaddress
import json
import os
import re
import socket
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse
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

# ===== 权威研究报告来源（三层覆盖体系）=====
# 第一层：国际再保险巨头（宏观市场数据）
AUTHORITATIVE_REPORT_SOURCES_REINSURANCE = [
    "瑞士再保险", "Swiss Re", "瑞再", "慕尼黑再保险", "Munich Re", "慕再",
    "劳合社", "Lloyd", "怡安", "Aon", "韦莱再保险", "Willis Re",
]
# 第二层：全球咨询机构（战略趋势）
AUTHORITATIVE_REPORT_SOURCES_CONSULTING = [
    "麦肯锡", "McKinsey", "德勤", "Deloitte", "BCG", "波士顿咨询",
    "Gartner", "毕马威", "KPMG", "普华永道", "PwC",
    "奥纬咨询", "Oliver Wyman", "埃森哲", "Accenture",
    "佳达再保险", "Guy Carpenter", "Marsh McLennan", "威达信",
]
# 第三层：国内研究机构（本土落地视角）
AUTHORITATIVE_REPORT_SOURCES_DOMESTIC = [
    "中国保险行业协会", "中金公司", "CICC", "艾瑞咨询", "iResearch",
    "头豹研究院", "LeadLeo", "清华五道口", "清华大学五道口",
    "零壹财经", "零壹智库", "国家金融监督管理总局", "NFRA", "银保监会",
]
AUTHORITATIVE_REPORT_SOURCES = (
    AUTHORITATIVE_REPORT_SOURCES_REINSURANCE
    + AUTHORITATIVE_REPORT_SOURCES_CONSULTING
    + AUTHORITATIVE_REPORT_SOURCES_DOMESTIC
)

# ===== 8大研究主题关键词体系 =====
RESEARCH_TOPICS = {
    "ai_intelligent": [
        "人工智能", "AI", "生成式AI", "GenAI", "大模型", "智能核保", "智能理赔",
        "机器学习", "深度学习", "自然语言处理", "NLP", "计算机视觉",
        "智能体", "Agentic AI", "数字化转型", "数字化", "自动化",
    ],
    "pension_finance": [
        "养老金融", "养老金", "养老保险", "个人养老金", "年金", "退休",
        "老龄化", "银发经济", "第三支柱", "个人商业养老金", "养老储蓄",
    ],
    "product_innovation": [
        "产品创新", "新品上市", "保险产品", "健康险", "惠民保", "护理险",
        "UBI车险", "参数化保险", "创新产品", "产品升级", "保障方案",
    ],
    "channel_transformation": [
        "渠道变革", "银保渠道", "代理人", "互联网保险", "线上化",
        "数字化分销", "BBE", "团险转个险", "直销", "保险中介",
    ],
    "capital_reinsurance": [
        "再保险", "巨灾债券", "ILS", "保险连接证券", "续转", "承保能力",
        "私募资本", "资本管理", "并购", "M&A", "ROE", "偿付能力",
    ],
    "climate_catastrophe": [
        "自然灾害", "巨灾", "台风", "飓风", "洪灾", "地震", "野火",
        "气候变化", "极端天气", "NatCat", "巨灾保险", "灾害损失",
        "碳排放", "绿色保险", "ESG",
    ],
    "digital_transformation": [
        "数字化转型", "核心系统", "保险科技", "InsurTech", "区块链",
        "大数据", "云计算", "API生态", "平台化", "线上化率",
        "数字化指数", "技术栈", "系统现代化",
    ],
    "regulatory_change": [
        "监管变革", "偿付能力", "C-ROSS", "IFRS 17", "金融监管总局",
        "合规", "牌照", "行政处罚", "监管政策", "分级分类监管",
        "数据安全", "个人信息保护", "反洗钱",
    ],
}

RESEARCH_TOPIC_LABELS = {
    "ai_intelligent": "AI智能化",
    "pension_finance": "养老金融",
    "product_innovation": "产品创新",
    "channel_transformation": "渠道变革",
    "capital_reinsurance": "资本与再保险",
    "climate_catastrophe": "气候与巨灾",
    "digital_transformation": "数字化转型",
    "regulatory_change": "监管变革",
}

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
    # 保险公司官网/产品页（非新闻）
    "picc.com.cn", "epicc.com", "pingan.com", "pa18.com",
    "cpic.com.cn", "newchinalife.com", "chinalife.com",
    "cmbchina.com", "cignacmb.com", "taikang.com",
    "hzins.com", "huize.com", "bxahz.com",
]
BLACKLIST_SOURCE_NAMES = [
    "知乎", "百度百科", "哔哩哔哩", "发表网", "发表云", "百度知道",
    "百度经验", "360doc", "豆瓣", "博客园", "CSDN", "简书",
    "百度文库", "百度贴吧",
]

# 搜索引擎噪声标题模式 — 标题匹配这些模式的视为非新闻内容（产品页/官网/SEO垃圾）
SEARCH_ENGINE_NOISE_PATTERNS = [
    "官网", "官方网站", "计算器", "一站尽览", "第\\d+页", "网上投保",
    "网上买保险", "保险商城", "投保入口", "产品介绍_保险产品知识",
    "险种_网上", "保险产品介绍", "保险产品知识", "理赔流程-",
    "理赔服务$", "保险网$", "保险频道", "招聘猎头",
    "保险险种_", "保险产品知识_",
    "保险问答", "需要多久", "保险知识_", "爆款产品", "产品名称:",
    "_汽车之家", "保险测评.*期", "保险专题报告.*腾讯",
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


def is_search_engine_noise(title: str) -> bool:
    """检测搜索引擎结果是否为非新闻内容（产品页/官网/SEO垃圾）"""
    if not title:
        return False
    for pattern in SEARCH_ENGINE_NOISE_PATTERNS:
        if re.search(pattern, title):
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


def is_safe_url(url: str) -> bool:
    """SSRF 防护：检查 URL 主机名是否解析到内网/私有/环回地址"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        # 解析所有 A 记录，拒绝内网地址
        addrs = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addrs:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except Exception:
        return False


# ===== 文章页日期提取（第一性原理：发布日期只能来自源页面，不能来自爬虫时间）=====
# 可靠的日期提取模式（搜索完整 HTML）
ARTICLE_DATE_PATTERNS_RELIABLE = [
    re.compile(r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta[^>]+name=["\']publishdate["\'][^>]+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta[^>]+name=["\']publication_date["\'][^>]+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta[^>]+name=["\']weibo:article:create_at["\'][^>]+content=["\']([^"\']+)["\']', re.I),
    # JSON-LD 结构化数据
    re.compile(r'"datePublished"[:\s]*"([^"]+)"', re.I),
    # 时间元素
    re.compile(r'<time[^>]+datetime=["\']([^"\']+)["\']', re.I),
]

# 兜底模式：仅在 HTML 前 2K 搜索（通常是 <head> 区域，避免匹配正文中的无关日期）
ARTICLE_DATE_PATTERN_FALLBACK = re.compile(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', re.I)

# URL 中的日期模式（支持 /20260702/ 和 /2026/07/02/ 两种格式）
URL_DATE_PATTERNS = [
    re.compile(r'/(\d{4})(\d{2})(\d{2})/'),
    re.compile(r'/(\d{4})/(\d{1,2})/(\d{1,2})/'),
]


async def fetch_article_date(client: httpx.AsyncClient, url: str) -> str | None:
    """从文章页面提取真实发布日期。
    第一性原理：发布日期是文章的固有属性，只能从源页面提取，不能默认为今天。
    安全：SSRF 防护 + 流式读取限制响应大小 + 手动重定向校验。
    """
    if not url or not validate_url(url) or not is_safe_url(url):
        return None
    if is_blacklisted(url, ""):
        return None
    try:
        # 手动跟随重定向，每跳都校验目标 URL 安全性
        current_url = url
        for _ in range(5):  # 最多5次重定向
            async with client.stream("GET", current_url, timeout=httpx.Timeout(8.0, connect=3.0), follow_redirects=False) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location", "")
                    if not location:
                        return None
                    current_url = urljoin(current_url, location)
                    if not validate_url(current_url) or not is_safe_url(current_url):
                        return None
                    continue
                if resp.status_code != 200:
                    return None
                # 流式读取，限制响应体大小（真正节省内存和带宽）
                chunks = []
                total = 0
                async for chunk in resp.aiter_bytes(8192):
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= 60000:  # 略大于 50K 以容纳多字节 UTF-8
                        break
                raw_bytes = b"".join(chunks)
                html = raw_bytes.decode("utf-8", errors="ignore")[:50000]
                break
        else:
            return None  # 重定向次数超限

        # 1. 尝试可靠的 meta 标签和结构化数据（搜索完整 HTML）
        for pattern in ARTICLE_DATE_PATTERNS_RELIABLE:
            m = pattern.search(html)
            if m:
                parsed = _parse_date_string(m.group(1))
                if parsed:
                    return parsed
        # 2. 兜底模式：仅搜索前 2K（<head> 区域，避免匹配正文无关日期）
        head_html = html[:2000]
        m = ARTICLE_DATE_PATTERN_FALLBACK.search(head_html)
        if m:
            parsed = _parse_date_string(m.group(1))
            if parsed:
                return parsed
        # 3. 尝试从 URL 提取日期
        for url_pat in URL_DATE_PATTERNS:
            url_match = url_pat.search(url)
            if url_match:
                y, mo, d = url_match.groups()
                return _validate_date(y, mo, d)
        return None
    except Exception:
        return None


def _parse_date_string(raw: str) -> str | None:
    """将各种日期格式解析为 YYYY-MM-DD，含范围校验"""
    raw = raw.strip()
    # ISO 格式: 2026-07-02T10:30:00+08:00
    m = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})', raw)
    if m:
        return _validate_date(m.group(1), m.group(2), m.group(3))
    # 中文格式: 2026年7月2日（"日"可选，兼容 ARTICLE_DATE_PATTERNS 捕获组不含"日"的情况）
    m = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日?', raw)
    if m:
        return _validate_date(m.group(1), m.group(2), m.group(3))
    # 斜杠格式: 2026/07/02
    m = re.match(r'(\d{4})/(\d{1,2})/(\d{1,2})', raw)
    if m:
        return _validate_date(m.group(1), m.group(2), m.group(3))
    return None


def _validate_date(y: str, mo: str, d: str) -> str | None:
    """校验日期范围并返回 YYYY-MM-DD，无效日期返回 None"""
    try:
        datetime(year=int(y), month=int(mo), day=int(d))
    except ValueError:
        return None
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def extract_date_from_text(text: str) -> str | None:
    """从文本中提取日期（用于搜索引擎结果页的时间信息）"""
    if not text:
        return None
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    today = now.date()
    # "X小时前" → 今天（仅当 < 24 小时）
    hours_match = re.search(r'(\d+)小时前', text)
    if hours_match and int(hours_match.group(1)) < 24:
        return today.isoformat()
    # "X天前" → 计算日期
    days_match = re.search(r'(\d+)天前', text)
    if days_match:
        d = today - timedelta(days=int(days_match.group(1)))
        return d.isoformat()
    # "昨天"
    if '昨天' in text:
        d = today - timedelta(days=1)
        return d.isoformat()
    # "前天"
    if '前天' in text:
        d = today - timedelta(days=2)
        return d.isoformat()
    # "今天"
    if '今天' in text or '今日' in text:
        return today.isoformat()
    # YYYY-MM-DD 或 YYYY-MM-DD HH:MM
    m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', text)
    if m:
        return _validate_date(m.group(1), m.group(2), m.group(3))
    # MM-DD（当年）
    m = re.search(r'(\d{1,2})月(\d{1,2})日', text)
    if m:
        return _validate_date(str(now.year), m.group(1), m.group(2))
    return None


def assign_category(title: str, content: str, hint: str = "") -> str:
    if hint:
        return hint
    text = (title + " " + content).lower()
    scores = {cat: sum(1 for kw in kws if kw.lower() in text) for cat, kws in CATEGORY_KEYWORDS.items()}
    if max(scores.values()) == 0:
        return "industry"
    return max(scores, key=scores.get)


def assign_research_topic(title: str, content: str) -> str:
    """将文章归类到8大研究主题之一。
    返回主题key（如 'ai_intelligent'），无匹配则返回空字符串。
    """
    if not title and not content:
        return ""
    title = title or ""
    content = content or ""
    text = (title + " " + content).lower()
    scores = {}
    for topic, keywords in RESEARCH_TOPICS.items():
        count = sum(1 for kw in keywords if kw.lower() in text)
        if count > 0:
            scores[topic] = count
    if not scores:
        return ""
    return max(scores, key=scores.get)


def is_authoritative_report(source_name: str, title: str, content: str) -> bool:
    """检测文章是否来自权威研究报告来源或引用了权威机构。
    三层覆盖体系：国际再保险巨头 + 全球咨询机构 + 国内研究机构。
    """
    text = (source_name + " " + title + " " + content).lower()
    for src in AUTHORITATIVE_REPORT_SOURCES:
        if src.lower() in text:
            return True
    # 报告类关键词（标题中包含"报告""白皮书""研究""展望"等）
    report_indicators = ["报告", "白皮书", "研究", "展望", "洞察", "趋势", "蓝皮书", "年报"]
    title_lower = title.lower()
    if any(ind in title_lower for ind in report_indicators):
        # 同时需匹配权威来源才认定
        for src in AUTHORITATIVE_REPORT_SOURCES:
            if src.lower() in text:
                return True
    return False


def detect_report_layer(source_name: str) -> str:
    """检测权威来源所属层级：reinsurance / consulting / domestic / 空"""
    for src in AUTHORITATIVE_REPORT_SOURCES_REINSURANCE:
        if src.lower() in source_name.lower():
            return "reinsurance"
    for src in AUTHORITATIVE_REPORT_SOURCES_CONSULTING:
        if src.lower() in source_name.lower():
            return "consulting"
    for src in AUTHORITATIVE_REPORT_SOURCES_DOMESTIC:
        if src.lower() in source_name.lower():
            return "domestic"
    return ""


def assign_score(title: str, content: str, source_name: str, pub_date: str, date_verified: bool = False, is_auth_report: bool = False) -> tuple:
    """计算文章评分。
    第一性原理：新鲜度加分只能给予已验证发布日期的文章。
    未知日期的文章不获得新鲜度加分（避免旧文冒充新闻）。
    权威研究报告加分：来自权威咨询/再保险/研究机构的文章获得额外加分。
    """
    text = (title + " " + content).lower()
    all_kw = [kw for kws in CATEGORY_KEYWORDS.values() for kw in kws]
    kw_count = sum(1 for kw in all_kw if kw.lower() in text)

    # 权威来源加分（最高1.0）
    authority = 1.0 if any(s in source_name for s in AUTHORITY_SOURCES) else 0
    # 权威研究报告加分（最高1.5）— 来自咨询机构/再保险巨头/研究智库的深度报告
    report_bonus = 1.5 if is_auth_report else 0
    # 内容长度加分（最高1.0）
    length_bonus = min(len(content) / 500, 1.0)

    # 新鲜度加分：仅对已验证日期的文章生效
    freshness_bonus = 0
    if date_verified and pub_date:
        try:
            d = datetime.strptime(pub_date[:10], "%Y-%m-%d").date()
            today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
            days_old = (today - d).days
            if days_old < 0:
                # 未来日期异常，不加分
                pass
            elif days_old <= 0:
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
    # 未知日期：freshness_bonus 保持为 0，旧文无法冒充新闻

    # 关键词匹配加分（每个关键词0.2，最高1.5）
    kw_bonus = min(kw_count * 0.2, 1.5)

    # 基础分3.0 + 各维度加分，满分10.0
    base = 3.0 + kw_bonus + authority + report_bonus + length_bonus + freshness_bonus
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
                pub_date = a.get("date", "")[:10]
                items.append({
                    "title": title,
                    "url": a.get("url", ""),
                    "content": content[:500],
                    "source_name": a.get("mediaName", "东方财富"),
                    "source_type": "api",
                    "published_at": pub_date,
                    "date_verified": bool(pub_date),  # API 返回的日期可信
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
                    "date_verified": True,  # URL 路径中的日期可信
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
                    "date_verified": bool(pub),  # AkShare 返回的日期可信
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
                    "date_verified": True,  # 按日期查询，日期可信
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
    # 时间过滤参数（7天内），在循环外计算避免重复
    now_ts = int(datetime.now(ZoneInfo("Asia/Shanghai")).timestamp())
    week_ago_ts = now_ts - 7 * 86400
    gpc_param = f"stf%3D{week_ago_ts}%2C{now_ts}%7Cstftype%3D1"
    for cfg in BAIDU_SEARCH_KEYWORDS:
        kw = cfg["keyword"]
        # 尝试两种URL格式：桌面版 + 移动版（均带时间过滤：仅最近7天）
        urls = [
            f"https://www.baidu.com/s?tn=news&wd={quote(kw)}&rn=10&cl=2&gpc={gpc_param}",
            f"https://m.baidu.com/s?word={quote(kw)}&from=1099a&sa=tb&tn=news&gpc={gpc_param}",
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
                pub_date = None
                date_verified = False
                if i < len(source_info):
                    info_text = clean_text(re.sub(r'<[^>]+>', '', source_info[i]))
                    parts = info_text.split()
                    if parts:
                        source_name = parts[0]
                    extracted = extract_date_from_text(info_text)
                    if extracted:
                        pub_date = extracted
                        date_verified = True
                # 未能提取日期时，published_at 设为空字符串，不默认为今天
                # 空日期的条目不会被新鲜度加分，但仍保留在候选池中等待日期验证
                if not pub_date:
                    pub_date = ""

                items.append({
                    "title": title,
                    "url": link,
                    "content": snippet[:500] if snippet else title,
                    "source_name": source_name,
                    "source_type": "baidu",
                    "published_at": pub_date,
                    "date_verified": date_verified,
                    "category_hint": cfg.get("category_hint", ""),
                    "language": "zh",
                })
                count += 1
            print(f"    ✅ 百度'{kw}': {count} 篇")
            await asyncio.sleep(1.0)
        except Exception as e:
            print(f"    ⚠️ 百度'{kw}'解析失败: {e}")
    return items


# ===== Google News RSS（可靠搜索引擎渠道，无需API Key）=====
GOOGLE_NEWS_KEYWORDS = [
    {"keyword": "保险", "category_hint": ""},
    {"keyword": "保险监管", "category_hint": "regulation"},
    {"keyword": "保险理赔", "category_hint": "claims"},
    {"keyword": "保险产品", "category_hint": "product"},
]

async def fetch_google_news_rss(client: httpx.AsyncClient) -> list[dict]:
    """通过 Google News RSS 采集保险资讯（可靠，无需API Key）"""
    import xml.etree.ElementTree as ET
    items = []
    for cfg in GOOGLE_NEWS_KEYWORDS:
        kw = cfg["keyword"]
        url = f"https://news.google.com/rss/search?q={quote(kw)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        try:
            resp = await client.get(url, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            count = 0
            for item_elem in root.findall('.//item'):
                title = (item_elem.findtext('title') or '').strip()
                link = (item_elem.findtext('link') or '').strip()
                pub_date_raw = (item_elem.findtext('pubDate') or '').strip()
                source = (item_elem.findtext('source') or 'Google新闻').strip()
                desc = (item_elem.findtext('description') or '').strip()
                if not title or len(title) < 5:
                    continue
                # Google News 标题格式: "标题 - 来源"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    if not source or source == 'Google新闻':
                        source = parts[1].strip()
                # 解析日期 (RFC 2822)
                pub_date = None
                date_verified = False
                if pub_date_raw:
                    try:
                        dt = datetime.strptime(pub_date_raw, '%a, %d %b %Y %H:%M:%S GMT')
                        pub_date = dt.date().isoformat()
                        date_verified = True
                    except Exception:
                        try:
                            dt = datetime.strptime(pub_date_raw, '%a, %d %b %Y %H:%M:%S %z')
                            pub_date = dt.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                            date_verified = True
                        except Exception:
                            pass
                if not pub_date:
                    pub_date = ""  # 不默认为今天，等待日期验证
                content = clean_text(desc) if desc else title
                items.append({
                    "title": title,
                    "url": link,
                    "content": content[:500],
                    "source_name": source,
                    "source_type": "google",
                    "published_at": pub_date,
                    "date_verified": date_verified,
                    "category_hint": cfg.get("category_hint", ""),
                    "language": "zh",
                })
                count += 1
                if count >= 8:
                    break
            print(f"    ✅ Google News'{kw}': {count} 篇")
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"    ⚠️ Google News'{kw}': {e}")
    return items


# ===== 360 搜索新闻 =====
SEARCH360_KEYWORDS = [
    {"keyword": "保险", "category_hint": ""},
    {"keyword": "保险监管", "category_hint": "regulation"},
    {"keyword": "保险理赔", "category_hint": "claims"},
]

async def fetch_360_news(client: httpx.AsyncClient) -> list[dict]:
    """通过 360 搜索新闻采集保险资讯"""
    items = []
    for cfg in SEARCH360_KEYWORDS:
        kw = cfg["keyword"]
        url = f"https://news.so.com/ns?q={quote(kw)}"
        try:
            resp = await client.get(url, timeout=15)
            resp.raise_for_status()
            html = resp.text
            # 360搜索新闻结果：title属性中包含标题，href中包含链接
            title_blocks = re.findall(
                r'<a[^>]*href="(https?://[^"]+)"[^>]*target="_blank"[^>]*title="([^"]+)"',
                html, re.S
            )
            # 过滤非新闻链接（360导航、登录等）
            title_blocks = [
                (u, t) for u, t in title_blocks
                if "360kuai.com" in u or "so.com" not in u
                and len(t) > 8 and ("保险" in t or kw in t)
            ]
            # 提取时间信息
            time_spans = re.findall(r'<span[^>]*class="[^"]*time[^"]*"[^>]*>(.*?)</span>', html, re.S)

            count = 0
            for i, (link, title) in enumerate(title_blocks[:8]):
                title = clean_text(title)
                if not title or len(title) < 5:
                    continue
                # 解析日期：优先从时间span提取，提取失败则为未知
                pub_date = None
                date_verified = False
                if i < len(time_spans):
                    time_text = clean_text(re.sub(r'<[^>]+>', '', time_spans[i]))
                    extracted = extract_date_from_text(time_text)
                    if extracted:
                        pub_date = extracted
                        date_verified = True
                # 未能提取日期时，不默认为今天，稍后通过 fetch_article_date 补充
                if not pub_date:
                    pub_date = ""
                # 从URL推断来源
                source_name = "360搜索"
                if "360kuai.com" in link:
                    source_name = "360快资讯"
                items.append({
                    "title": title,
                    "url": link,
                    "content": title,
                    "source_name": source_name,
                    "source_type": "360",
                    "published_at": pub_date,
                    "date_verified": date_verified,
                    "category_hint": cfg.get("category_hint", ""),
                    "language": "zh",
                })
                count += 1
            print(f"    ✅ 360搜索'{kw}': {count} 篇")
            await asyncio.sleep(0.8)
        except Exception as e:
            print(f"    ⚠️ 360搜索'{kw}': {e}")
    return items


# ===== 搜狗新闻搜索（非微信）=====
SOGOU_NEWS_KEYWORDS = [
    {"keyword": "保险", "category_hint": ""},
    {"keyword": "保险监管", "category_hint": "regulation"},
]

async def fetch_sogou_news(client: httpx.AsyncClient) -> list[dict]:
    """通过搜狗新闻搜索采集保险资讯"""
    items = []
    for cfg in SOGOU_NEWS_KEYWORDS:
        kw = cfg["keyword"]
        url = f"https://news.sogou.com/news?query={quote(kw)}&mode=1"
        try:
            resp = await client.get(url, timeout=15)
            resp.raise_for_status()
            html = resp.text
            # 搜狗新闻结果：标题在 h3 标签内的 a 标签中
            results = re.findall(
                r'<h3[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                html, re.S
            )
            count = 0
            for link, title_html in results[:8]:
                title = clean_text(re.sub(r'<[^>]+>', '', title_html))
                if not title or len(title) < 8:
                    continue
                if "保险" not in title and kw not in title:
                    continue
                if not link.startswith("http"):
                    link = urljoin("https://news.sogou.com", link)
                # 尝试从链接域名提取来源名
                source_name = "搜狗新闻"
                domain_match = re.search(r'https?://([^/]+)', link)
                if domain_match:
                    domain = domain_match.group(1)
                    # 域名到名称映射（优先匹配已知媒体）
                    domain_map = {
                        "finance.sina.com.cn": "新浪财经",
                        "finance.eastmoney.com": "东方财富网",
                        "www.cs.com.cn": "中证网",
                        "www.cnstock.com": "上海证券报",
                        "insurance.hexun.com": "和讯保险",
                        "www.bjqb.com.cn": "北京青年报",
                        "www.cbimc.cn": "中国银行保险报",
                        "www.nfra.gov.cn": "金融监管总局",
                        "www.iachina.cn": "中国保险行业协会",
                    }
                    if domain in domain_map:
                        source_name = domain_map[domain]
                    else:
                        # 智能提取域名主体（去掉 www/news/finance 等前缀）
                        parts = domain.replace(".com.cn", "").replace(".cn", "").replace(".com", "").split(".")
                        # 取最后一个非前缀部分
                        prefixes = {"www", "news", "finance", "m", "wap", "insurance", "b", "sogou"}
                        main_part = next((p for p in reversed(parts) if p not in prefixes and len(p) > 2), "")
                        source_name = main_part if main_part and len(main_part) > 2 else "搜狗新闻"
                items.append({
                    "title": title,
                    "url": link,
                    "content": title,
                    "source_name": source_name,
                    "source_type": "sogou",
                    "published_at": "",  # 搜狗新闻结果页无日期信息，等待 fetch_article_date 补充
                    "date_verified": False,
                    "category_hint": cfg.get("category_hint", ""),
                    "language": "zh",
                })
                count += 1
            print(f"    ✅ 搜狗新闻'{kw}': {count} 篇")
            await asyncio.sleep(0.8)
        except Exception as e:
            print(f"    ⚠️ 搜狗新闻'{kw}': {e}")
    return items


# ===== 搜狗微信公众号搜索 =====
# 微信公众号低质量标记 — 账号名包含这些词的视为非专业保险媒体
WECHAT_LOW_QUALITY_MARKERS = [
    "社区", "随笔", "日常", "生活", "风的", "晓", "日记", "博客",
    "个人", "小镇", "村庄", "街道", "便民", "信息港", "同城",
    "人社", "政务", "管委会", "办事处",
]

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
                        # 低质量账号过滤
                        if any(marker in acct for marker in WECHAT_LOW_QUALITY_MARKERS):
                            continue
                        source_name = f"公众号·{acct}"
                if not link.startswith("http"):
                    link = urljoin("https://weixin.sogou.com", link)
                # 解析日期：优先从 Unix 时间戳转换
                pub_date = None
                date_verified = False
                if i < len(timestamps):
                    try:
                        ts = int(timestamps[i])
                        dt = datetime.fromtimestamp(ts, tz=ZoneInfo("Asia/Shanghai"))
                        pub_date = dt.date().isoformat()
                        date_verified = True
                    except Exception:
                        pass
                # 退而求其次：从日期块提取
                if not date_verified and i < len(date_blocks):
                    date_text = clean_text(re.sub(r'<[^>]+>', '', date_blocks[i]))
                    extracted = extract_date_from_text(date_text)
                    if extracted:
                        pub_date = extracted
                        date_verified = True
                if not pub_date:
                    pub_date = ""  # 不默认为今天，等待日期验证
                
                items.append({
                    "title": title,
                    "url": link,
                    "content": title,
                    "source_name": source_name,
                    "source_type": "wechat",
                    "published_at": pub_date,
                    "date_verified": date_verified,
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

        print("\n📰 Google News RSS...")
        gn_items = await fetch_google_news_rss(client)
        all_items.extend(gn_items)
        real_count += len(gn_items)
        source_health["google"] = {"count": len(gn_items), "ok": len(gn_items) > 0}

        print("\n🔍 360 搜索新闻...")
        s360_items = await fetch_360_news(client)
        all_items.extend(s360_items)
        real_count += len(s360_items)
        source_health["360"] = {"count": len(s360_items), "ok": len(s360_items) > 0}

        print("\n🔍 搜狗新闻搜索...")
        sn_items = await fetch_sogou_news(client)
        all_items.extend(sn_items)
        real_count += len(sn_items)
        source_health["sogou_news"] = {"count": len(sn_items), "ok": len(sn_items) > 0}

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
    se_noise_filtered = 0
    for item in all_items:
        url = item.get("url", "")
        title = item.get("title", "")
        source_name = item.get("source_name", "")
        source_type = item.get("source_type", "")
        # 股市噪声过滤
        if is_stock_noise(title):
            noise_filtered += 1
            continue
        # 非新闻来源黑名单过滤
        if is_blacklisted(url, source_name):
            blacklist_filtered += 1
            continue
        # 搜索引擎噪声过滤（仅对搜索引擎渠道）
        if source_type in ("baidu", "google", "360", "sogou", "bing") and is_search_engine_noise(title):
            se_noise_filtered += 1
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
    if se_noise_filtered:
        print(f"  🚫 过滤搜索引擎噪声 {se_noise_filtered} 条")

    if real_count == 0:
        print("\n⚠️ 真实采集失败，启用降级数据...")
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        for fb in FALLBACK_DATA:
            all_items.append({
                "title": fb["title"], "url": fb["url"], "content": fb["snippet"],
                "source_name": fb["source"], "source_type": "fallback",
                "published_at": today, "date_verified": False, "category_hint": fb.get("category", ""), "language": "zh",
            })
        print(f"\n🏥 数据源健康: {json.dumps(source_health, ensure_ascii=False)}")
        return all_items, False, source_health

    # ===== 第一性原理：日期验证 =====
    # 对 date_verified=False 的条目，访问文章页面提取真实发布日期
    # 这是防止旧文冒充新闻的关键步骤
    # 使用新的 client 避免主采集阶段连接池耗尽
    unverified = [i for i in all_items if not i.get("date_verified", False)]
    if unverified:
        print(f"\n📅 日期验证: {len(unverified)} 条待验证（最多验证15条）...")
        verified_count = 0
        old_dates_found = 0
        try:
            async with httpx.AsyncClient(follow_redirects=True, headers=HTTP_HEADERS) as verify_client:
                sem = asyncio.Semaphore(5)  # 并发限制
                async def verify_one(item):
                    nonlocal verified_count, old_dates_found
                    url = item.get("url", "")
                    if not url or url == "#":
                        return
                    async with sem:
                        real_date = await fetch_article_date(verify_client, url)
                    if real_date:
                        item["published_at"] = real_date
                        item["date_verified"] = True
                        verified_count += 1
                        # 检查是否为旧文（超过7天）
                        try:
                            d = date.fromisoformat(real_date[:10])
                            today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
                            if (today - d).days > 7:
                                old_dates_found += 1
                        except Exception:
                            pass
                tasks = [verify_one(item) for item in unverified[:15]]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, Exception):
                        print(f"  ⚠️ verify_one 异常: {r!r}")
        except Exception as e:
            print(f"  ⚠️ 日期验证失败（不影响主流程）: {e}")
        print(f"  ✅ 日期验证完成: {verified_count}/{len(unverified[:15])} 条成功提取真实日期")
        if old_dates_found:
            print(f"  🚫 发现 {old_dates_found} 条旧文（>7天），将被新鲜度过滤")

    # 新鲜度过滤（日期验证后，旧文会被正确过滤）
    # 第一性原理：未验证日期的条目（published_at 为空）直接通过过滤，但不会获得新鲜度加分
    # 已验证日期的条目必须在新窗口内，否则视为旧文淘汰
    cutoff = (datetime.now(ZoneInfo("Asia/Shanghai")).date()) - timedelta(days=FRESHNESS_DAYS)
    cutoff_str = cutoff.isoformat()

    def _passes_freshness(item: dict) -> bool:
        """已验证条目检查日期是否在窗口内；未验证条目直接通过（等待后续评分降权）"""
        if not item.get("date_verified", False):
            return True
        pub = item.get("published_at", "")
        if not pub:
            return True
        try:
            pub_date = date.fromisoformat(pub[:10])
            return pub_date >= cutoff
        except Exception:
            return True  # 解析失败不淘汰

    fresh = [i for i in all_items if _passes_freshness(i)]
    if not fresh:
        fresh = all_items  # 如果过滤后为空，保留全部

    # 统计日期验证情况
    verified_items = sum(1 for i in fresh if i.get("date_verified", False))
    unverified_items = len(fresh) - verified_items
    print(f"\n📥 采集 {len(all_items)} 条 → 去重后 {len(deduped)} 条 → 近{FRESHNESS_DAYS}天 {len(fresh)} 条")
    print(f"  📅 日期已验证: {verified_items} 条, 日期未验证: {unverified_items} 条")
    print(f"\n🏥 数据源健康: {json.dumps(source_health, ensure_ascii=False)}")
    return fresh, True, source_health


def process_items(items: list[dict]) -> list[dict]:
    for item in items:
        title = clean_text(item["title"])
        content = clean_text(item["content"])
        item["title"] = title
        item["content"] = content
        item["category"] = assign_category(title, content, item.get("category_hint", ""))
        # 研究主题分类（8大主题）
        item["research_topic"] = assign_research_topic(title, content)
        # 权威研究报告检测
        item["is_research_report"] = is_authoritative_report(item.get("source_name", ""), title, content)
        score, rel = assign_score(
            title, content, item["source_name"], item.get("published_at", ""),
            item.get("date_verified", False), item.get("is_research_report", False)
        )
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
        "baidu": "搜索引擎", "google": "搜索引擎", "360": "搜索引擎", "sogou": "搜索引擎",
        "wechat": "微信公众号",
    }
    items.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
    # 渠道均衡：确保每个渠道类型至少有3条，每个渠道最多15条，总计30条
    stype_counts = {}
    balanced = []
    balanced_ids = set()  # 用 id() 避免字典相等性误判
    MIN_PER_TYPE = 3
    MAX_PER_TYPE = 15
    TARGET_TOTAL = 30
    # 第一轮：每个 source_type 取前 MIN_PER_TYPE 条（保证渠道多样性）
    by_type = {}
    for item in items:
        st = item.get("source_type", "")
        by_type.setdefault(st, []).append(item)
    for st, type_items in by_type.items():
        for item in type_items[:MIN_PER_TYPE]:
            if id(item) not in balanced_ids:
                balanced.append(item)
                balanced_ids.add(id(item))
                stype_counts[st] = stype_counts.get(st, 0) + 1
    # 第二轮：按分数填充剩余位置（不超过 TARGET_TOTAL）
    for item in items:
        if len(balanced) >= TARGET_TOTAL:
            break
        if id(item) in balanced_ids:
            continue
        st = item.get("source_type", "")
        if stype_counts.get(st, 0) >= MAX_PER_TYPE:
            continue
        balanced.append(item)
        balanced_ids.add(id(item))
        stype_counts[st] = stype_counts.get(st, 0) + 1
    # 重新按分数排序
    balanced.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
    items = balanced

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
        "published_at": item.get("published_at", target_date), "date_verified": item.get("date_verified", False),
        "research_topic": item.get("research_topic", ""),
        "is_research_report": item.get("is_research_report", False),
        "reason": item.get("ai_reason", ""),
    } for i, item in enumerate(curated)]

    # 增量合并：保留近3天的历史新闻
    # 第一性原理：已验证日期的旧条目需在3天窗口内；未验证条目保留1个周期（下次运行时自然淘汰）
    old_news = data.get("news", [])
    seen_urls = set(n.get("source_url", "") for n in today_news if n.get("source_url"))
    merged = list(today_news)
    three_days_ago = (datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=3)).isoformat()
    for old_item in old_news:
        old_url = old_item.get("source_url", "")
        if old_url and old_url not in seen_urls:
            old_date = old_item.get("published_at", "")[:10]
            if old_item.get("date_verified", False):
                # 已验证条目：检查3天窗口
                try:
                    if old_date >= three_days_ago:
                        old_item["source_type"] = SOURCE_TYPE_MAP.get(old_item.get("source_type", ""), old_item.get("source_type", "财经媒体"))
                        merged.append(old_item)
                        seen_urls.add(old_url)
                except Exception:
                    pass
            elif old_date:
                # 未验证但有日期的旧条目：保留1个周期（下次运行时被新条目覆盖）
                old_item["source_type"] = SOURCE_TYPE_MAP.get(old_item.get("source_type", ""), old_item.get("source_type", "财经媒体"))
                merged.append(old_item)
                seen_urls.add(old_url)
            # 无日期的未验证条目：不保留（无任何时间信息，无法判断新旧）
    # 限制总量100条
    merged = merged[:100]
    # 重新分配唯一ID（防止增量合并导致ID重复）
    for idx, item in enumerate(merged):
        item["id"] = idx + 1
    data["news"] = merged

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

    # 加载权威研究报告注册表（三层覆盖体系）
    research_reports_path = PROJECT_ROOT / "data" / "research_reports.json"
    try:
        if research_reports_path.exists():
            research_registry = json.loads(research_reports_path.read_text("utf-8"))
            # 更新注册表的last_updated
            research_registry["last_updated"] = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
            data["research_reports"] = research_registry
            print(f"  📚 已加载 {len(research_registry.get('reports', []))} 份权威研究报告")
    except Exception as e:
        print(f"  ⚠️ 加载研究报告注册表失败: {e}")
        data["research_reports"] = {"reports": [], "error": str(e)}

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
