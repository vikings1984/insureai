"""InsureScope 主入口 - CLI 与 Pipeline"""

from __future__ import annotations
import asyncio
import argparse
import json
from datetime import date, datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.config import load_config, get_project_root
from src.models import NewsItem, DailySummary
from src.collectors import get_all_collectors
from src.ai.scorer import InsuranceScorer
from src.ai.enricher import InsuranceEnricher
from src.output.summary_generator import SummaryGenerator
from src.output.rss_output import RSSFeedGenerator

console = Console()


async def run_pipeline(target_date: str | None = None, full: bool = False) -> DailySummary:
    """运行完整 Pipeline: 采集 → 去重 → 评分 → 过滤 → 增强 → 生成简报
    
    Args:
        target_date: 指定日期，默认为今天
        full: 是否使用全量模式（包含低分内容）
    """

    config = load_config()
    today = target_date or date.today().isoformat()
    
    # 模式标识
    mode = "全量模式" if full else "精选模式"

    console.print(f"\n[bold blue]📋 InsureScope 保险信息聚合系统[/bold blue]")
    console.print(f"[dim]日期: {today} | 模式: {mode}[/dim]\n")

    # ===== Step 1: 采集 =====
    console.print("[bold green]📡 Step 1: 采集信息源[/bold green]")
    all_items: list[NewsItem] = []

    # 动态导入所有采集器
    import src.collectors.rss_collector
    import src.collectors.hackernews_collector
    import src.collectors.reddit_collector
    import src.collectors.github_collector
    import src.collectors.wechat_collector
    import src.collectors.search_collector
    import src.collectors.akshare_collector

    collectors = get_all_collectors()
    for name, collector_cls in collectors.items():
        try:
            collector = collector_cls()
            if not collector.is_enabled(config):
                console.print(f"  [dim]⏭ {name}: 已禁用[/dim]")
                continue

            with console.status(f"  采集中 {name}..."):
                items = await collector.fetch(config)
            all_items.extend(items)
            console.print(f"  ✅ {name}: {len(items)} 条")
        except Exception as e:
            console.print(f"  ❌ {name}: {e}")

    # 额外采集：搜索引擎（用于中文新闻）
    search_config = config.get("sources", {}).get("search", {})
    if search_config.get("enabled", False):
        try:
            from src.collectors.search_collector import SearchCollector
            search_collector = SearchCollector()
            
            with console.status("  🔍 搜索引擎采集..."):
                search_items = await search_collector.search_insurance_news(
                    num_results_per_query=search_config.get("num_results_per_query", 10)
                )
            all_items.extend(search_items)
            console.print(f"  ✅ 搜索引擎: {len(search_items)} 条")
            await search_collector.close()
        except Exception as e:
            console.print(f"  ⚠️ 搜索引擎: {e}")

    console.print(f"\n[bold]共采集 {len(all_items)} 条资讯[/bold]\n")

    if not all_items:
        console.print("[yellow]未采集到任何资讯，请检查配置。[/yellow]")
        return DailySummary(date=today)

    # ===== Step 2: 去重 =====
    console.print("[bold green]🔄 Step 2: 去重[/bold green]")
    seen_urls = set()
    unique_items = []
    for item in all_items:
        # 标准化 URL 去重
        normalized_url = item.url.rstrip("/").split("?")[0].split("#")[0]
        if normalized_url not in seen_urls:
            seen_urls.add(normalized_url)
            unique_items.append(item)

    removed = len(all_items) - len(unique_items)
    console.print(f"  去除 {removed} 条重复，保留 {len(unique_items)} 条\n")

    # ===== Step 3: AI 评分 =====
    console.print("[bold green]🤖 Step 3: AI 评分与分类[/bold green]")
    scorer = InsuranceScorer(config)

    with console.status("AI 评分中..."):
        scored_items = await scorer.score_all(unique_items)

    # 按分数排序
    scored_items.sort(key=lambda x: x.ai_score, reverse=True)
    console.print(f"  ✅ 评分完成\n")

    # ===== Step 4: 过滤（根据模式）=====
    console.print("[bold green]🔍 Step 4: 过滤内容[/bold green]")
    
    if full:
        # 全量模式：不过滤，保留所有内容
        filtered_items = scored_items
        console.print(f"  [yellow]全量模式: 保留全部 {len(filtered_items)} 条资讯[/yellow]\n")
    else:
        # 精选模式：过滤低分内容
        filtered_items = scorer.filter_items(scored_items)
        threshold = config.get('scoring', {}).get('ai_score_threshold', 6.0)
        console.print(f"  精选模式: 保留 {len(filtered_items)}/{len(scored_items)} 条（阈值: {threshold}）\n")

    # ===== Step 5: 增强 =====
    if config.get("enrichment", {}).get("enabled", True):
        console.print("[bold green]📚 Step 5: 内容增强[/bold green]")
        enricher = InsuranceEnricher(config)

        with console.status("增强高分资讯..."):
            enriched_items = await enricher.enrich_all(filtered_items)

        enriched_count = sum(1 for item in enriched_items if item.detailed_summary)
        console.print(f"  ✅ 增强 {enriched_count} 条资讯\n")
        filtered_items = enriched_items

    # ===== Step 6: 生成简报 =====
    console.print("[bold green]📝 Step 6: 生成每日简报[/bold green]")

    # 组织数据
    highlights = [item for item in filtered_items if item.ai_score >= 9.0]
    by_category: dict[str, list[NewsItem]] = {}
    for item in filtered_items:
        cat = item.category or "industry"
        by_category.setdefault(cat, []).append(item)

    summary = DailySummary(
        date=today,
        items=filtered_items,
        highlights=highlights,
        by_category=by_category,
    )

    # 生成 Markdown 和 JSON（根据模式选择文件名）
    generator = SummaryGenerator(config)
    suffix = "-full" if full else ""
    paths = generator.save(summary, suffix=suffix)
    
    for lang, path in paths.items():
        if lang == "json":
            console.print(f"  📄 JSON: {path}")
        else:
            console.print(f"  📄 Markdown ({lang}): {path}")

    # 生成 RSS（精选模式才生成 RSS）
    if not full:
        rss_gen = RSSFeedGenerator(config)
        for lang in ("zh", "en"):
            feed = rss_gen.generate_curated_feed(filtered_items, lang)
            feed_path = rss_gen.save_feed(feed, f"curated-{lang}.xml")
            console.print(f"  📡 RSS ({lang}): {feed_path}")
    else:
        console.print(f"  [dim]📡 RSS: 全量模式不生成 RSS[/dim]")

    console.print(f"\n[bold green]✅ 完成! 共 {summary.total_items} 条资讯，平均分 {summary.avg_score:.1f}[/bold green]\n")

    return summary


def cli():
    """CLI 入口"""
    parser = argparse.ArgumentParser(description="InsureScope - AI 驱动的保险信息聚合系统")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # run 命令
    run_parser = subparsers.add_parser("run", help="运行采集 Pipeline")
    run_parser.add_argument("--date", type=str, help="指定日期 YYYY-MM-DD")
    run_parser.add_argument("--full", action="store_true", help="完整模式（增强所有内容）")

    # api 命令
    api_parser = subparsers.add_parser("api", help="启动 API 服务器")
    api_parser.add_argument("--host", type=str, default="0.0.0.0")
    api_parser.add_argument("--port", type=int, default=8080)

    # validate 命令
    validate_parser = subparsers.add_parser("validate", help="验证配置文件")

    args = parser.parse_args()

    if args.command == "run":
        asyncio.run(run_pipeline(target_date=args.date, full=args.full))
    elif args.command == "api":
        import uvicorn
        from src.output.api_server import create_app
        app = create_app()
        uvicorn.run(app, host=args.host, port=args.port)
    elif args.command == "validate":
        try:
            config = load_config()
            console.print("[green]✅ 配置文件有效[/green]")
            console.print(f"  AI 提供商: {config.get('ai', {}).get('provider', 'N/A')}")
            console.print(f"  RSS 源: {len(config.get('sources', {}).get('rss', []))} 个")
            console.print(f"  Reddit: {', '.join(config.get('sources', {}).get('reddit', {}).get('subreddits', []))}")
            console.print(f"  分类: {len(config.get('categories', {}))} 个")
        except Exception as e:
            console.print(f"[red]❌ 配置文件无效: {e}[/red]")
    else:
        parser.print_help()


if __name__ == "__main__":
    cli()
