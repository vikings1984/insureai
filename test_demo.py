#!/usr/bin/env python3
"""测试脚本 - 演示 InsureScope 完整功能"""

import asyncio
import json
from datetime import date
from pathlib import Path

# 添加项目路径
import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.models import NewsItem, DailySummary
from src.output.summary_generator import SummaryGenerator
from src.output.rss_output import RSSFeedGenerator
from src.config import load_config

# 模拟采集的保险资讯数据
MOCK_NEWS_ITEMS = [
    {
        "title": "金融监管总局发布《保险资金运用管理办法》修订版",
        "url": "https://example.com/news/1",
        "source_name": "金融监管总局",
        "source_type": "rss",
        "content": "为进一步规范保险资金运用行为，防范资金运用风险，金融监管总局对《保险资金运用管理办法》进行了修订。修订内容包括：完善保险资金运用范围、优化资产配置比例、加强风险管控措施等。",
        "ai_score": 9.2,
        "insurance_relevance": 0.95,
        "category": "regulation",
        "ai_summary": "金融监管总局修订保险资金运用管理办法，完善资金运用范围和风险管控",
        "ai_tags": ["监管政策", "资金运用", "风险管控"],
        "whats_new": "新增了对保险资金投资新兴产业的相关规定，扩大了可投资范围",
        "why_it_matters": "直接影响保险公司资产配置策略和投资收益，对保险行业资金运用具有重大指导意义",
        "key_details": "修订版将于2026年7月1日正式实施，过渡期6个月",
        "background": [
            {"concept": "保险资金运用", "explanation": "保险公司将保费收入进行投资以获取收益的行为"},
            {"concept": "偿付能力", "explanation": "保险公司履行赔付义务的能力，是监管核心指标"}
        ],
        "references": [
            {"title": "保险资金运用管理办法全文", "url": "https://www.nfra.gov.cn", "description": "金融监管总局官方文件"}
        ],
        "community_discussion": "专业人士关注新规对保险资金投资股票、债券比例的影响",
    },
    {
        "title": "平安保险推出AI智能理赔系统，理赔时效缩短80%",
        "url": "https://example.com/news/2",
        "source_name": "保险科技周刊",
        "source_type": "rss",
        "content": "平安保险宣布推出新一代AI智能理赔系统，通过深度学习和计算机视觉技术，实现车险理赔全流程自动化。系统可在5分钟内完成定损，理赔时效缩短80%。",
        "ai_score": 8.5,
        "insurance_relevance": 0.90,
        "category": "product",
        "ai_summary": "平安保险推出AI理赔系统，车险理赔时效缩短80%",
        "ai_tags": ["AI理赔", "保险科技", "产品创新"],
        "whats_new": "首次实现车险理赔全流程自动化，包括定损、核赔、赔付",
        "why_it_matters": "标志着保险行业数字化转型的重要里程碑，将推动行业理赔服务升级",
        "key_details": "系统采用计算机视觉技术自动识别车辆损伤，准确率达95%",
        "background": [
            {"concept": "智能理赔", "explanation": "运用AI技术实现理赔流程自动化，提升效率和用户体验"},
            {"concept": "计算机视觉", "explanation": "让计算机能够识别和理解图像内容的人工智能技术"}
        ],
        "references": [
            {"title": "平安保险科技布局", "url": "https://tech.pingan.com", "description": "平安保险科技官网"}
        ],
        "community_discussion": "技术人员讨论AI定损的准确性和边界情况处理",
    },
    {
        "title": "中国人寿2025年一季度保费收入突破3000亿元",
        "url": "https://example.com/news/3",
        "source_name": "财经日报",
        "source_type": "rss",
        "content": "中国人寿保险股份有限公司发布2025年第一季度业绩报告，实现保费收入3021亿元，同比增长8.5%。新业务价值同比增长12.3%，继续引领行业增长。",
        "ai_score": 7.8,
        "insurance_relevance": 0.85,
        "category": "industry",
        "ai_summary": "中国人寿一季度保费收入3021亿元，同比增长8.5%",
        "ai_tags": ["业绩报告", "保费收入", "行业动态"],
        "whats_new": "新业务价值增速超过保费增速，业务结构持续优化",
        "why_it_matters": "反映保险行业持续稳健发展态势，头部公司竞争优势明显",
        "key_details": "寿险业务占比65%，健康险业务占比25%，意外险占比10%",
        "background": [
            {"concept": "新业务价值", "explanation": "衡量保险公司新保单未来利润贡献的指标"},
            {"concept": "保费收入", "explanation": "保险公司从投保人收取的保险费总额"}
        ],
        "references": [
            {"title": "中国人寿投资者关系", "url": "https://www.e-chinalife.com", "description": "中国人寿官网"}
        ],
        "community_discussion": "投资者关注新业务价值增长的质量和可持续性",
    },
    {
        "title": "研究论文：基于深度学习的车险定价模型",
        "url": "https://example.com/news/4",
        "source_name": "精算研究期刊",
        "source_type": "rss",
        "content": "清华大学精算研究中心发布最新研究成果，提出基于深度学习的车险定价模型。该模型整合驾驶行为数据、车辆特征和道路环境因素，定价准确率提升15%。",
        "ai_score": 8.0,
        "insurance_relevance": 0.88,
        "category": "research",
        "ai_summary": "清华研究团队提出深度学习车险定价模型，准确率提升15%",
        "ai_tags": ["精算研究", "深度学习", "定价模型"],
        "whats_new": "首次将驾驶行为数据纳入定价模型，实现千人千面定价",
        "why_it_matters": "为车险精准定价提供新方法论，有望降低整体赔付率",
        "key_details": "模型使用Transformer架构，训练数据包含100万条理赔记录",
        "background": [
            {"concept": "车险定价", "explanation": "根据风险因素计算车险保费的过程"},
            {"concept": "UBI保险", "explanation": "基于驾驶行为的保险，根据实际驾驶数据定价"}
        ],
        "references": [
            {"title": "论文原文", "url": "https://arxiv.org", "description": "arXiv预印本"}
        ],
        "community_discussion": "精算师讨论模型可解释性和监管合规性",
    },
    {
        "title": "首例互联网保险纠纷判例：保险公司败诉",
        "url": "https://example.com/news/5",
        "source_name": "法治日报",
        "source_type": "rss",
        "content": "北京互联网法院审理了一起互联网保险纠纷案件。消费者通过手机APP购买健康险后被拒赔，法院判决保险公司未尽到明确说明义务，应承担赔偿责任。",
        "ai_score": 7.5,
        "insurance_relevance": 0.82,
        "category": "claims",
        "ai_summary": "北京互联网法院判决保险公司未尽说明义务需赔偿",
        "ai_tags": ["理赔纠纷", "判例", "消费者权益"],
        "whats_new": "首例互联网保险销售说明义务认定判例，确立裁判标准",
        "why_it_matters": "对互联网保险销售合规具有重要指导意义，推动行业规范发展",
        "key_details": "法院认定电子投保流程中的免责条款提示不够显著",
        "background": [
            {"concept": "说明义务", "explanation": "保险公司有义务向投保人说明保险合同条款"},
            {"concept": "互联网保险", "explanation": "通过互联网渠道销售的保险产品"}
        ],
        "references": [
            {"title": "判决书全文", "url": "https://www.bjinternetcourt.gov.cn", "description": "北京互联网法院"}
        ],
        "community_discussion": "法律人士讨论电子投保的合规边界",
    },
]


def create_mock_items() -> list[NewsItem]:
    """创建模拟新闻条目"""
    items = []
    for data in MOCK_NEWS_ITEMS:
        item = NewsItem(
            title=data["title"],
            url=data["url"],
            source_name=data["source_name"],
            source_type=data["source_type"],
            content=data.get("content", ""),
            ai_score=data.get("ai_score", 0),
            insurance_relevance=data.get("insurance_relevance", 0),
            category=data.get("category", ""),
            ai_summary=data.get("ai_summary", ""),
            ai_tags=data.get("ai_tags", []),
            whats_new=data.get("whats_new", ""),
            why_it_matters=data.get("why_it_matters", ""),
            key_details=data.get("key_details", ""),
            background=data.get("background", []),
            references=data.get("references", []),
            community_discussion=data.get("community_discussion", ""),
        )
        items.append(item)
    return items


async def run_demo():
    """运行演示"""
    config = load_config()
    today = date.today().isoformat()

    print("\n" + "="*60)
    print("📋 InsureScope 保险信息聚合系统 - 演示模式")
    print("="*60)
    print(f"\n📅 日期: {today}\n")

    # 创建模拟数据
    items = create_mock_items()
    
    # 按分数排序
    items.sort(key=lambda x: x.ai_score, reverse=True)
    
    # 组织数据
    highlights = [item for item in items if item.ai_score >= 9.0]
    by_category = {}
    for item in items:
        cat = item.category or "industry"
        by_category.setdefault(cat, []).append(item)

    summary = DailySummary(
        date=today,
        items=items,
        highlights=highlights,
        by_category=by_category,
    )

    # 显示采集结果
    print("📊 采集统计")
    print("-"*40)
    print(f"  总计: {len(items)} 条资讯")
    print(f"  平均分: {summary.avg_score:.1f}")
    print(f"  高分资讯: {len(highlights)} 条\n")

    # 显示分类统计
    print("📁 分类统计")
    print("-"*40)
    for cat, cat_items in by_category.items():
        print(f"  {cat}: {len(cat_items)} 条")
    print()

    # 显示高分资讯
    print("⭐ 今日精选 (AI评分 ≥ 9.0)")
    print("-"*40)
    for item in highlights:
        print(f"  [{item.ai_score:.1f}] {item.title}")
        print(f"        {item.ai_summary}")
    print()

    # 显示所有资讯
    print("📰 今日资讯列表")
    print("-"*40)
    for i, item in enumerate(items, 1):
        print(f"  {i}. [{item.ai_score:.1f}] {item.title}")
        print(f"     分类: {item.category} | 来源: {item.source_name}")
        print(f"     摘要: {item.ai_summary}")
        if item.whats_new:
            print(f"     📌 最新动态: {item.whats_new}")
        if item.why_it_matters:
            print(f"     💡 行业影响: {item.why_it_matters}")
        print()

    # 生成输出文件
    print("📝 生成输出文件...")
    print("-"*40)
    
    # 确保 summaries 目录存在
    summary_dir = Path(__file__).parent / "data" / "summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成 Markdown 和 JSON
    generator = SummaryGenerator(config)
    paths = generator.save(summary, total_fetched=28)
    for lang, path in paths.items():
        print(f"  📄 {lang}: {path}")

    # 生成 RSS
    rss_gen = RSSFeedGenerator(config)
    for lang in ("zh", "en"):
        feed = rss_gen.generate_curated_feed(items, lang)
        feed_path = rss_gen.save_feed(feed, f"curated-{lang}.xml")
        print(f"  📡 RSS ({lang}): {feed_path}")

    print("\n" + "="*60)
    print("✅ 演示完成!")
    print("="*60 + "\n")

    return summary


if __name__ == "__main__":
    asyncio.run(run_demo())
