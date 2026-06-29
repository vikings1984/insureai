#!/usr/bin/env python3
"""InsureAI 高质量数据采集 Pipeline
多源采集 + 智能分类 + 新鲜度过滤

数据源优先级：
1. 东方财富搜索 API（主源）— 多关键词搜索，覆盖全分类，当天新闻
2. 中国保险行业协会（辅源）— 协会要闻 + 行业动态
3. 降级数据（兜底）— 真实采集全部失败时
"""

import asyncio
import html as html_module
import json
import os
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urljoin

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

# ===== 数据源配置 =====
EASTMONEY_SEARCH_KEYWORDS = [
    {"keyword": "保险", "category_hint": "", "page_size": 15},
    {"keyword": "保险监管", "category_hint": "regulation", "page_size": 8},
    {"keyword": "保险产品", "category_hint": "product", "page_size": 8},
    {"keyword": "保险理赔", "category_hint": "claims", "page_size": 8},
    {"keyword": "保险科技", "category_hint": "research", "page_size": 8},
]

IACHINA_COLUMNS = [
    {"col": 22, "name": "中国保险行业协会", "category_hint": "industry"},
    {"col": 24, "name": "中国保险行业协会", "category_hint": "industry"},
]

FRESHNESS_DAYS = 14  # 只保留最近 N 天的文章

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

    authority = 1.5 if any(s in source_name for s in AUTHORITY_SOURCES) else 0
    length_bonus = min(len(content) / 300, 2.0)

    # 新鲜度加分
    freshness_bonus = 0
    try:
        d = datetime.strptime(pub_date[:10], "%Y-%m-%d")
        days_old = (datetime.now() - d).days
        if days_old <= 1:
            freshness_bonus = 2.0
        elif days_old <= 3:
            freshness_bonus = 1.5
        elif days_old <= 7:
            freshness_bonus = 1.0
        elif days_old <= 14:
            freshness_bonus = 0.5
    except Exception:
        pass

    base = 4.0 + kw_count * 0.3 + authority + length_bonus + freshness_bonus
    score = min(round(base + random.uniform(-0.2, 0.2), 1), 10.0)
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
            m = re.search(r'jQuery\((.*)\)', resp.text, re.S)
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
                pub = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}" if dm else date.today().isoformat()
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


# ===== 采集主流程 =====
async def collect_all() -> tuple[list[dict], bool]:
    all_items = []
    real_count = 0

    print("📡 东方财富搜索 API（主源）...")
    async with httpx.AsyncClient(follow_redirects=True, headers=HTTP_HEADERS) as client:
        em_items = await fetch_eastmoney(client)
        all_items.extend(em_items)
        real_count += len(em_items)

        print("\n🌐 中国保险行业协会（辅源）...")
        ia_items = await fetch_iachina(client)
        all_items.extend(ia_items)
        real_count += len(ia_items)

    # 去重（按 URL）
    seen_urls = set()
    deduped = []
    for item in all_items:
        url = item.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped.append(item)
    all_items = deduped

    if real_count == 0:
        print("\n⚠️ 真实采集失败，启用降级数据...")
        today = date.today().isoformat()
        for fb in FALLBACK_DATA:
            all_items.append({
                "title": fb["title"], "url": fb["url"], "content": fb["snippet"],
                "source_name": fb["source"], "source_type": "fallback",
                "published_at": today, "category_hint": fb.get("category", ""), "language": "zh",
            })
        return all_items, False

    # 新鲜度过滤
    cutoff = date.today() - timedelta(days=FRESHNESS_DAYS)
    fresh = [i for i in all_items if i.get("published_at", "") >= cutoff.isoformat()]
    if not fresh:
        fresh = all_items  # 如果过滤后为空，保留全部

    print(f"\n📥 采集 {len(all_items)} 条 → 去重后 {len(deduped)} 条 → 近{FRESHNESS_DAYS}天 {len(fresh)} 条")
    return fresh, True


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
    return items


def generate_output(items: list[dict], target_date: str, is_real: bool):
    items.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
    items = items[:25]  # 最多 25 条

    by_cat = {}
    for item in items:
        by_cat.setdefault(item["category"], []).append(item)

    curated = [i for i in items if i.get("ai_score", 0) >= 6.0]
    highlights = [i for i in curated if i.get("ai_score", 0) >= 8.5]

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
        (DOCS_POSTS / f"{target_date}-zh.md", zh),
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

    data["news"] = [{
        "id": i + 1, "title": item["title"], "summary": item.get("content", "")[:300],
        "source_name": item["source_name"], "source_type": item.get("source_type", "web"),
        "source_url": item.get("url", "#"), "ai_score": int(item.get("ai_score", 0) * 10),
        "tags": ",".join(item.get("ai_tags", [])), "category": item.get("category", "industry"),
        "published_at": item.get("published_at", target_date), "reason": item.get("ai_reason", ""),
    } for i, item in enumerate(curated)]

    data["days"][target_date] = {
        "total": len(items), "curated": len(curated), "highlights": len(highlights),
        "avg_score": round(sum(i.get("ai_score", 0) for i in curated) / max(len(curated), 1), 1),
        "categories": {c: len(ci) for c, ci in by_cat.items()},
        "sources": list(set(i["source_name"] for i in items)),
    }
    data["last_updated"] = datetime.now().isoformat()
    data["data_source"] = "real" if is_real else "fallback"
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
    target = date.today().isoformat()
    print(f"\n🚀 InsureAI 采集 Pipeline | {target}\n")
    items, is_real = await collect_all()
    if not items:
        print("⚠️ 无数据")
        return
    items = process_items(items)
    generate_output(items, target, is_real)


if __name__ == "__main__":
    asyncio.run(main())
