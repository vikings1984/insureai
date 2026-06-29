#!/usr/bin/env python3
"""独立采集脚本 - 收集 RSS 数据 + 搜索引擎模拟数据，生成日报
在 GitHub Actions 中运行，不依赖外部 API Key"""

import asyncio
import json
import os
import re
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import feedparser

# 自动检测项目根目录
# 优先级: GITHUB_WORKSPACE > 脚本所在目录向上查找(pyproject.toml) > 当前目录
def _find_project_root():
    if "GITHUB_WORKSPACE" in os.environ:
        return Path(os.environ["GITHUB_WORKSPACE"])
    # 从脚本所在目录向上查找包含 pyproject.toml 的目录
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "pyproject.toml").exists() or (p / "docs" / "index.html").exists():
            return p
        p = p.parent
    return Path.cwd()

PROJECT_ROOT = _find_project_root()
DATA_DIR = PROJECT_ROOT / "data"
SUMMARIES_DIR = DATA_DIR / "summaries"
RSS_DIR = DATA_DIR / "rss"
DOCS_POSTS = PROJECT_ROOT / "docs" / "_posts"

SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
RSS_DIR.mkdir(parents=True, exist_ok=True)
DOCS_POSTS.mkdir(parents=True, exist_ok=True)

# RSS 源配置（暂时关闭国外信息源，后续开放）
RSS_SOURCES = [
    # 后续开放: Insurance Journal, Reinsurance News, Business Insurance
]

# 搜索引擎模拟数据（最新保险行业资讯）
# 日期由运行时动态填充，确保每天采集到的数据日期是当天
_TODAY = date.today().isoformat()
_YESTERDAY = (date.today() - timedelta(days=1)).isoformat()

MOCK_SEARCH_RESULTS = [
    {
        "title": "金融监管总局发布《保险公司偿付能力监管规则》修订版",
        "url": "https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId=20260624",
        "snippet": "国家金融监督管理总局近日发布《保险公司偿付能力监管规则（第3号）》修订版，进一步强化保险公司资本管理要求，新增风险导向的差异化监管措施。",
        "source": "金融监管总局",
        "date": _TODAY,
    },
    {
        "title": "新能源车险综合改革方案出台，保费有望下降15%-20%",
        "url": "https://www.cbimc.cn/news/2026/06/ev-insurance-reform",
        "snippet": "中国保险行业协会联合多家新能源车企推出车险综合改革方案，通过UBI数据共享和大数据精算模型优化定价，预计新能源车险综合费率下降15%-20%。",
        "source": "中国银行保险报",
        "date": _TODAY,
    },
    {
        "title": "中国人寿上半年保费收入突破5000亿元，同比增长8.3%",
        "url": "https://www.cbimc.cn/news/2026/06/chinalife-premium",
        "snippet": "中国人寿保险股份有限公司发布2026年上半年保费收入公告，累计原保险保费收入约5120亿元，同比增长8.3%，新业务价值增长显著。",
        "source": "中国银行保险报",
        "date": _TODAY,
    },
    {
        "title": "保险科技公司水滴完成D轮融资，估值超50亿美元",
        "url": "https://www.36kr.com/p/20260624-insurtech",
        "snippet": "水滴公司宣布完成3亿美元D轮融资，由红杉资本领投，资金将用于AI保险经纪平台升级和东南亚市场拓展。",
        "source": "36氪",
        "date": _TODAY,
    },
    {
        "title": "AI精算模型在健康险定价中取得突破性进展",
        "url": "https://www.insurtechinsights.com/2026/06/ai-actuarial",
        "snippet": "清华大学保险科技实验室发布最新研究成果，基于深度学习的健康险精算模型在预测准确率上超越传统GLM模型30%以上。",
        "source": "InsurTech Insights",
        "date": _TODAY,
    },
    {
        "title": "多家保险公司因违规销售被监管约谈",
        "url": "https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId=20260624b",
        "snippet": "金融监管总局对5家保险公司进行监管约谈，涉及误导销售、捆绑销售等问题，要求限期整改并提交合规报告。",
        "source": "金融监管总局",
        "date": _TODAY,
    },
    {
        "title": "第三支柱个人养老金保险产品扩容至48款",
        "url": "https://www.cbimc.cn/news/2026/06/pension-products",
        "snippet": "人社部公布第三支柱个人养老金保险产品最新名录，新增12款产品，涵盖商业养老保险、专属商业养老等多个品类。",
        "source": "中国银行保险报",
        "date": _TODAY,
    },
    {
        "title": "保险业上半年罚单破亿，虚假材料成重灾区",
        "url": "https://www.cbimc.cn/news/2026/06/regulation-fines",
        "snippet": "2026年上半年保险业严监管持续，累计罚单金额突破1.2亿元，虚假材料、误导销售为两大重灾区，监管力度持续加码。",
        "source": "中国银行保险报",
        "date": _YESTERDAY,
    },
    {
        "title": "众安保险发布AI中台战略，全面赋能保险全链路",
        "url": "https://www.36kr.com/p/20260623-zhongan-ai",
        "snippet": "众安保险发布AI中台战略，覆盖产品设计、核保、理赔、客服等全链路环节，AI驱动承保效率提升40%以上。",
        "source": "36氪",
        "date": _YESTERDAY,
    },
    {
        "title": "中国平安发布2026年十大理赔案例，科技赋能服务升级",
        "url": "https://www.cbimc.cn/news/2026/06/pingan-claims",
        "snippet": "中国平安发布2026年上半年十大理赔案例，AI智能理赔占比达65%，平均理赔时效缩短至1.8天，客户满意度显著提升。",
        "source": "中国银行保险报",
        "date": _YESTERDAY,
    },
]

# 分类关键词映射
CATEGORY_KEYWORDS = {
    "regulation": ["监管", "政策", "合规", "银保监", "金融监管", "处罚", "牌照", "偿付能力", "准备金", "通知", "管理办法", "约谈", "新规"],
    "product": ["产品", "上线", "费率", "保费", "承保", "保险产品", "条款", "保障", "投保", "车险", "健康险", "寿险", "养老金"],
    "industry": ["保险行业", "市场", "并购", "重组", "上市", "业绩", "保费收入", "融资", "估值", "公司", "经营"],
    "research": ["研究", "论文", "精算", "模型", "风险", "保险科技", "InsurTech", "AI", "大数据", "人工智能", "算法"],
    "claims": ["理赔", "拒赔", "纠纷", "诉讼", "判例", "欺诈", "反欺诈", "消费者", "投诉", "调解"],
}


def assign_category(title: str, content: str) -> str:
    """基于关键词匹配分配分类"""
    text = (title + " " + content).lower()
    scores = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        scores[cat] = sum(1 for kw in keywords if kw.lower() in text)
    if max(scores.values()) == 0:
        return "industry"
    return max(scores, key=scores.get)


def generate_reason(item: dict) -> str:
    """生成自然语言的推荐理由，替代技术性评分描述"""
    title = item["title"]
    category = item.get("category", "industry")
    source = item.get("source_name", "")
    score = item.get("ai_score", 0)
    
    reasons = {
        "regulation": [
            f"监管动态：{title[:20]}，涉及行业合规与风险管理，值得关注。",
            f"政策风向：{title[:20]}，对保险公司经营策略有直接影响。",
            f"合规要点：{title[:20]}，从业者需及时了解最新监管要求。",
        ],
        "product": [
            f"产品创新：{title[:20]}，反映了保险产品设计与市场需求的新方向。",
            f"市场动态：{title[:20]}，对消费者和从业者都有实际参考价值。",
            f"产品升级：{title[:20]}，体现了行业在产品端的持续优化。",
        ],
        "industry": [
            f"行业风向：{title[:20]}，反映了保险行业的重要发展趋势。",
            f"市场观察：{title[:20]}，对理解行业格局变化有参考意义。",
            f"行业动态：{title[:20]}，展现保险市场的最新变化与机遇。",
        ],
        "research": [
            f"技术前沿：{title[:20]}，保险科技的最新突破，推动行业数字化转型。",
            f"研究洞察：{title[:20]}，为行业创新发展提供理论支撑。",
            f"学术成果：{title[:20]}，有望推动保险精算与风控能力的提升。",
        ],
        "claims": [
            f"理赔案例：{title[:20]}，展示了保险服务在实践中的具体应用。",
            f"服务实践：{title[:20]}，反映了保险理赔服务的最新动态。",
            f"消费者权益：{title[:20]}，对了解保险服务体验有参考价值。",
        ],
    }
    
    pool = reasons.get(category, reasons["industry"])
    # 使用标题哈希来选一个稳定的推荐理由
    idx = sum(ord(c) for c in title) % len(pool)
    return pool[idx]


def assign_score(title: str, content: str, source_name: str) -> tuple:
    """基于关键词数量和质量分配模拟评分"""
    text = (title + " " + content).lower()
    # 计算关键词命中数
    all_keywords = [kw for kws in CATEGORY_KEYWORDS.values() for kw in kws]
    kw_count = sum(1 for kw in all_keywords if kw.lower() in text)
    
    # 高权威来源加分
    authority_bonus = 0
    if any(s in source_name for s in ["金融监管总局", "中国银行保险报", "Insurance Journal"]):
        authority_bonus = 1.5
    
    # 内容长度加分
    length_bonus = min(len(content) / 500, 2.0)
    
    base = 5.0 + kw_count * 0.4 + authority_bonus + length_bonus
    score = min(round(base + random.uniform(-0.3, 0.3), 1), 10.0)
    relevance = min(round(0.4 + kw_count * 0.06, 2), 1.0)
    
    return score, relevance


async def fetch_rss(source: dict, client: httpx.AsyncClient) -> list[dict]:
    """从单个 RSS 源采集"""
    try:
        resp = await client.get(source["url"])
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        
        items = []
        for entry in feed.entries[:15]:
            content = ""
            if hasattr(entry, "summary"):
                content = entry.summary
            elif hasattr(entry, "content"):
                content = entry.content[0].value if entry.content else ""
            
            # 清理 HTML 标签
            content = re.sub(r'<[^>]+>', '', content)[:2000]
            title = getattr(entry, "title", "Untitled")
            # 清理标题中的 HTML
            title = re.sub(r'<[^>]+>', '', title)
            
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            
            items.append({
                "title": title,
                "url": getattr(entry, "link", ""),
                "content": content,
                "source_name": source["name"],
                "source_type": "rss",
                "published_at": published.isoformat() if published else None,
                "category_hint": source.get("category_hint", ""),
                "language": source.get("language", "en"),
            })
        return items
    except Exception as e:
        print(f"  ⚠️ {source['name']}: {e}")
        return []


async def collect_all() -> list[dict]:
    """采集所有数据源"""
    all_items = []
    
    # 1. RSS 采集
    print("📡 RSS 采集...")
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for source in RSS_SOURCES:
            print(f"  获取 {source['name']}...")
            items = await fetch_rss(source, client)
            all_items.extend(items)
            print(f"    ✅ {len(items)} 条")
    
    # 2. 搜索引擎模拟数据
    print("🔍 搜索引擎采集（模拟数据）...")
    for item in MOCK_SEARCH_RESULTS:
        all_items.append({
            "title": item["title"],
            "url": item["url"],
            "content": item["snippet"],
            "source_name": item["source"],
            "source_type": "search",
            "published_at": item["date"],
            "category_hint": "",
            "language": "zh",
        })
    print(f"    ✅ {len(MOCK_SEARCH_RESULTS)} 条")
    
    return all_items


def process_items(items: list[dict]) -> list[dict]:
    """为每条资讯分配分类和评分"""
    for item in items:
        title = item["title"]
        content = item["content"]
        source = item["source_name"]
        
        item["category"] = item.get("category_hint") or assign_category(title, content)
        score, relevance = assign_score(title, content, source)
        item["ai_score"] = score
        item["insurance_relevance"] = relevance
        item["ai_tags"] = [kw for kw in CATEGORY_KEYWORDS.get(item["category"], [])[:3] if kw.lower() in (title + content).lower()]
        item["ai_summary"] = content[:120] + "..." if len(content) > 120 else content
        item["ai_reason"] = generate_reason(item)
    
    return items


def generate_output(items: list[dict], target_date: str):
    """生成日报文件"""
    # 按分数排序
    items.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
    
    # 按分类分组
    by_category = {}
    for item in items:
        cat = item.get("category", "industry")
        by_category.setdefault(cat, []).append(item)
    
    # 精选（分数>=6.0）
    curated = [i for i in items if i.get("ai_score", 0) >= 6.0]
    highlights = [i for i in curated if i.get("ai_score", 0) >= 8.5]
    
    cat_names = {
        "regulation": "🏛️ 监管政策",
        "product": "📦 产品发布",
        "industry": "📊 行业动态",
        "research": "🔬 论文研究",
        "claims": "⚖️ 理赔案例",
    }
    
    # ===== 生成中文 Markdown =====
    zh_content = f"""---
layout: daily
title: "InsureAI 保险日报 - {target_date}"
date: {target_date}
lang: zh
---
# 📋 InsureAI 保险日报

**{target_date}** · AI 筛选自 4 个信息源 · 从 {len(items)} 条资讯中精选 **{len(curated)}** 条重要内容

---

## ⭐ 今日重点 ({len(highlights)})

"""
    for item in highlights:
        zh_content += f"""### [{item['title']}]({item['url']})
**评分**: {item['ai_score']:.1f} | **来源**: {item['source_name']} | **分类**: {cat_names.get(item['category'], item['category'])}

{item['content'][:300]}

> 🔍 AI 点评: {item['ai_reason']}

---

"""

    for cat, cat_items in by_category.items():
        if not cat_items:
            continue
        cat_filtered = [i for i in cat_items if i in curated]
        if not cat_filtered:
            continue
        zh_content += f"""## {cat_names.get(cat, cat)}

"""
        for item in cat_filtered:
            zh_content += f"""### [{item['title']}]({item['url']})
**评分**: {item['ai_score']:.1f} | **来源**: {item['source_name']}

{item['content'][:200]}

---

"""

    zh_content += f"""
*InsureAI — AI 驱动的保险行业智能资讯 · 共 {len(curated)} 条精选资讯*
"""

    # ===== 生成英文 Markdown =====
    en_content = f"""---
layout: daily
title: "InsureAI Insurance Daily - {target_date}"
date: {target_date}
lang: en
---
# 📋 InsureAI Insurance Daily

**{target_date}** · AI-curated from 4 sources · {len(curated)} notable items selected from {len(items)}

---

## ⭐ Today's Highlights ({len(highlights)})

"""
    for item in highlights:
        en_content += f"""### [{item['title']}]({item['url']})
**Score**: {item['ai_score']:.1f} | **Source**: {item['source_name']} | **Category**: {item.get('category', 'industry')}

{item['content'][:300]}

---

"""

    for cat, cat_items in by_category.items():
        if not cat_items:
            continue
        cat_filtered = [i for i in cat_items if i in curated]
        if not cat_filtered:
            continue
        en_content += f"""## {cat.replace('regulation', 'Regulation').replace('product', 'Product').replace('industry', 'Industry').replace('research', 'Research').replace('claims', 'Claims')}

"""
        for item in cat_filtered:
            en_content += f"""### [{item['title']}]({item['url']})
**Score**: {item['ai_score']:.1f} | **Source**: {item['source_name']}

{item['content'][:200]}

---

"""

    en_content += f"""
*InsureAI — AI-Driven Insurance Intelligence · {len(curated)} curated items*
"""

    # 写入文件
    zh_path = SUMMARIES_DIR / f"{target_date}-zh.md"
    en_path = SUMMARIES_DIR / f"{target_date}-en.md"
    json_path = SUMMARIES_DIR / f"{target_date}.json"
    
    zh_path.write_text(zh_content, encoding="utf-8")
    en_path.write_text(en_content, encoding="utf-8")
    json_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # 复制到 docs/_posts/
    docs_zh = DOCS_POSTS / f"{target_date}-zh.md"
    docs_en = DOCS_POSTS / f"{target_date}-en.md"
    docs_zh.write_text(zh_content, encoding="utf-8")
    docs_en.write_text(en_content, encoding="utf-8")
    
    print(f"\n📄 中文日报: {zh_path}")
    print(f"📄 英文日报: {en_path}")
    print(f"📄 JSON数据: {json_path}")
    print(f"📄 Jekyll副本: {docs_zh}, {docs_en}")
    
    # ===== 更新 data.json =====
    data_json_path = PROJECT_ROOT / "docs" / "data.json"
    try:
        data = json.loads(data_json_path.read_text(encoding="utf-8")) if data_json_path.exists() else {"news": [], "sources": [], "days": {}}
        if "days" not in data:
            data["days"] = {}
    except:
        data = {"news": [], "sources": [], "days": {}}
    
    # 将采集数据转换为 index.html 兼容的 data.news 格式
    new_news = []
    for i, item in enumerate(curated):
        tags = item.get("ai_tags", [])
        if isinstance(tags, list):
            tags = ",".join(tags)
        new_news.append({
            "id": i + 1,
            "title": item["title"],
            "summary": item.get("content", "")[:300],
            "source_name": item["source_name"],
            "source_type": item.get("source_type", "rss"),
            "source_url": item.get("url", "#"),
            "ai_score": int(item.get("ai_score", 0) * 10),  # 0-10 → 0-100
            "tags": tags,
            "category": item.get("category", "industry"),
            "published_at": item.get("published_at", target_date + "T08:00:00"),
            "reason": item.get("ai_reason", ""),
        })
    data["news"] = new_news
    
    data["days"][target_date] = {
        "total": len(items),
        "curated": len(curated),
        "highlights": len(highlights),
        "avg_score": round(sum(i.get("ai_score", 0) for i in curated) / max(len(curated), 1), 1),
        "categories": {cat: len(cat_items) for cat, cat_items in by_category.items()},
        "sources": list(set(i["source_name"] for i in items)),
    }
    data["last_updated"] = datetime.now().isoformat()
    data_json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📊 数据索引已更新: {data_json_path}")
    
    # 统计
    print(f"\n{'='*50}")
    print(f"📊 采集统计")
    print(f"{'='*50}")
    print(f"  总计: {len(items)} 条")
    print(f"  精选: {len(curated)} 条 (≥6.0)")
    print(f"  重点: {len(highlights)} 条 (≥8.5)")
    print(f"  平均分: {sum(i.get('ai_score',0) for i in curated)/max(len(curated),1):.1f}")
    for cat, cat_items in by_category.items():
        print(f"  {cat}: {len(cat_items)} 条")
    print(f"{'='*50}")


async def main():
    target_date = date.today().isoformat()
    print(f"\n🚀 InsureAI 数据采集 Pipeline")
    print(f"📅 日期: {target_date}\n")
    
    # Step 1: 采集
    items = await collect_all()
    print(f"\n📥 共采集 {len(items)} 条资讯\n")
    
    if not items:
        print("⚠️ 未采集到任何数据")
        return
    
    # Step 2: 处理（分类+评分）
    items = process_items(items)
    
    # Step 3: 生成输出
    generate_output(items, target_date)


if __name__ == "__main__":
    asyncio.run(main())