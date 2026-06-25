"""采集测试脚本 - 展示最新数据源采集效果"""

import asyncio
import feedparser
import json
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()

def test_rss_sources():
    """测试所有 RSS 数据源"""
    console.print(Panel.fit("[bold cyan]📡 RSS 海外保险资讯源采集测试[/bold cyan]", border_style="blue"))

    rss_sources = [
        {
            "name": "Insurance Journal",
            "url": "https://www.insurancejournal.com/feed/",
            "description": "美国保险行业权威媒体"
        },
        {
            "name": "Reinsurance News",
            "url": "https://www.reinsurancene.ws/feed/",
            "description": "全球再保险新闻"
        },
        {
            "name": "Artemis - ILS",
            "url": "https://www.artemis.bm/feed/",
            "description": "保险连接证券(ILS)专业媒体"
        },
        {
            "name": "Business Insurance",
            "url": "https://www.businessinsurance.com/feed/",
            "description": "商业保险新闻"
        }
    ]

    total_articles = 0
    results = []

    for source in rss_sources:
        try:
            feed = feedparser.parse(source["url"])

            # 提取最新文章（最多10条）
            articles = []
            for entry in feed.entries[:10]:
                article = {
                    "title": entry.get("title", "无标题"),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", entry.get("updated", "未知"))[:16] if entry.get("published") or entry.get("updated") else "未知",
                    "summary": entry.get("summary", entry.get("description", ""))[:100] + "..." if entry.get("summary") or entry.get("description") else ""
                }
                articles.append(article)

            total_articles += len(articles)
            results.append({
                "name": source["name"],
                "description": source["description"],
                "status": "✅ 正常",
                "count": len(articles),
                "articles": articles,
                "error": None
            })
            console.print(f"  [green]✅[/green] {source['name']}: {len(articles)} 条")
        except Exception as e:
            results.append({
                "name": source["name"],
                "description": source["description"],
                "status": f"❌ 失败",
                "count": 0,
                "articles": [],
                "error": str(e)
            })
            console.print(f"  [red]❌[/red] {source['name']}: {e}")

    return results, total_articles


def test_akshare():
    """测试 AkShare 数据源"""
    console.print(Panel.fit("[bold cyan]📊 AkShare 金融数据采集测试[/bold cyan]", border_style="blue"))

    results = []

    # 测试 GDP 数据
    try:
        import akshare as ak
        console.print("  [dim]正在获取 GDP 数据...[/dim]")
        gdp_df = ak.macro_china_gdp()
        latest_gdp = gdp_df.iloc[0]
        gdp_value = latest_gdp.get("国内生产总值-绝对值", latest_gdp.get("gdp", "N/A"))
        gdp_date = latest_gdp.get("季度", latest_gdp.get("统计时间", "N/A"))
        results.append({
            "name": "GDP 国内生产总值",
            "status": "✅ 正常",
            "data": f"{gdp_date}: {gdp_value}万亿元" if gdp_value != "N/A" else str(latest_gdp)
        })
        console.print(f"  [green]✅[/green] GDP数据: {gdp_date} - {gdp_value}万亿元")
    except Exception as e:
        results.append({"name": "GDP 国内生产总值", "status": "❌ 失败", "data": str(e)})
        console.print(f"  [red]❌[/red] GDP数据: {e}")

    # 测试 CPI 数据
    try:
        console.print("  [dim]正在获取 CPI 数据...[/dim]")
        cpi_df = ak.macro_china_cpi()
        latest_cpi = cpi_df.iloc[0]
        cpi_date = latest_cpi.get("月份", latest_cpi.get("统计时间", "N/A"))
        cpi_value = latest_cpi.get("全国-同比增长", latest_cpi.get("同比", "N/A"))
        results.append({
            "name": "CPI 居民消费价格指数",
            "status": "✅ 正常",
            "data": f"{cpi_date}: 同比{cpi_value}%"
        })
        console.print(f"  [green]✅[/green] CPI数据: {cpi_date} - 同比{cpi_value}%")
    except Exception as e:
        results.append({"name": "CPI 居民消费价格指数", "status": "❌ 失败", "data": str(e)})
        console.print(f"  [red]❌[/red] CPI数据: {e}")

    # 测试存款准备金率
    try:
        console.print("  [dim]正在获取存款准备金率...[/dim]")
        reserve_df = ak.macro_china_reserve_requirement_ratio()
        latest_reserve = reserve_df.iloc[0]
        reserve_date = latest_reserve.get("日期", "N/A")
        reserve_value = latest_reserve.get("大型金融机构-存款准备金率(%)", "N/A")
        results.append({
            "name": "存款准备金率",
            "status": "✅ 正常",
            "data": f"{reserve_date}: {reserve_value}%"
        })
        console.print(f"  [green]✅[/green] 存款准备金率: {reserve_date} - {reserve_value}%")
    except Exception as e:
        results.append({"name": "存款准备金率", "status": "❌ 失败", "data": str(e)})
        console.print(f"  [red]❌[/red] 存款准备金率: {e}")

    return results


def test_translation_service():
    """测试翻译服务"""
    console.print(Panel.fit("[bold cyan]🌐 翻译服务状态测试[/bold cyan]", border_style="blue"))

    results = []

    # 检查配置状态
    import os
    has_zhipu = bool(os.environ.get("ZHIPU_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))

    # 测试 Google 免费翻译 (快速检查 deep_translator 是否可用)
    try:
        from deep_translator import GoogleTranslator
        console.print(f"  [green]✅[/green] deep_translator 库已安装")

        # 快速测试
        test_text = "Insurance"
        translator = GoogleTranslator(source='en', target='zh-CN')
        translated = translator.translate(test_text)

        results.append({
            "name": "Google 免费翻译",
            "status": "✅ 可用",
            "provider": "GoogleFreeTranslation",
            "sample": f"'{test_text}' -> '{translated}'"
        })
        console.print(f"  [green]✅[/green] Google 免费翻译测试: '{test_text}' -> '{translated}'")

    except ImportError:
        results.append({
            "name": "Google 免费翻译",
            "status": "⚠️ 需要安装",
            "provider": "N/A",
            "sample": "deep-translator 库未安装"
        })
        console.print(f"  [yellow]⚠️[/yellow] deep-translator 库未安装")
    except Exception as e:
        results.append({
            "name": "Google 免费翻译",
            "status": "⚠️ 网络问题",
            "provider": "N/A",
            "sample": str(e)[:50]
        })
        console.print(f"  [yellow]⚠️[/yellow] Google 翻译测试: {str(e)[:50]}")

    # 显示 API key 配置状态
    console.print(f"\n  [dim]API Key 配置状态:[/dim]")
    console.print(f"    ZHIPU_API_KEY: {'✅ 已设置' if has_zhipu else '⚠️ 未设置'}")
    console.print(f"    OPENAI_API_KEY: {'✅ 已设置' if has_openai else '⚠️ 未设置'}")
    console.print(f"    ANTHROPIC_API_KEY: {'✅ 已设置' if has_anthropic else '⚠️ 未设置'}")

    if not (has_zhipu or has_openai or has_anthropic):
        console.print(f"\n  [dim]💡 提示: 配置付费 API 可获得更高质量的翻译效果[/dim]")
        console.print(f"  [dim]   参考: docs/.env.example 中的 API_KEY 配置[/dim]")

    return results


def display_sample_articles(rss_results):
    """展示各源最新文章示例"""
    console.print(Panel.fit("[bold cyan]📰 各源最新文章示例[/bold cyan]", border_style="blue"))

    for result in rss_results:
        if result["articles"]:
            console.print(f"\n[bold green]{result['name']}[/bold green] ({result['description']})")
            for i, article in enumerate(result["articles"][:3], 1):
                console.print(f"  {i}. {article['title'][:60]}...")
                console.print(f"     [dim]{article['published']}[/dim]")


def main():
    """主测试流程"""
    console.print("\n")
    console.print(Panel.fit(
        "[bold yellow]🧪 InsureScope 数据源采集效果测试[/bold yellow]\n"
        f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        border_style="yellow"
    ))
    console.print("\n")

    # 1. RSS 源测试
    rss_results, total_rss = test_rss_sources()

    console.print("\n")

    # 2. AkShare 测试
    akshare_results = test_akshare()

    console.print("\n")

    # 3. 翻译服务测试
    translation_results = test_translation_service()

    console.print("\n")

    # 4. 展示示例文章
    display_sample_articles(rss_results)

    # 5. 汇总
    console.print("\n")
    console.print(Panel.fit("[bold yellow]📈 测试汇总[/bold yellow]", border_style="yellow"))

    summary_table = Table(box=box.ROUNDED)
    summary_table.add_column("数据源类型", style="cyan")
    summary_table.add_column("状态", style="green")
    summary_table.add_column("详情", style="dim")

    summary_table.add_row("RSS 海外源", f"{len([r for r in rss_results if '✅' in r['status']])}/{len(rss_results)} 正常", f"共 {total_rss} 条文章")
    summary_table.add_row("AkShare 金融", f"{len([r for r in akshare_results if '✅' in r['status']])}/{len(akshare_results)} 正常", "GDP/CPI/准备金率")
    summary_table.add_row("翻译服务", translation_results[0]['status'] if translation_results else "未测试", translation_results[0].get('provider', 'N/A') if translation_results else 'N/A')

    console.print(summary_table)

    # 返回测试结果
    return {
        "rss": rss_results,
        "akshare": akshare_results,
        "translation": translation_results,
        "total_rss": total_rss
    }


if __name__ == "__main__":
    results = main()
