"""AkShare 金融数据采集器"""

from __future__ import annotations
import asyncio
from datetime import datetime, date
from typing import TYPE_CHECKING

from src.collectors import BaseCollector, register_collector
from src.models import NewsItem

if TYPE_CHECKING:
    pass


@register_collector("akshare")
class AkShareCollector(BaseCollector):
    """从 AkShare 获取金融数据并转换为保险行业资讯"""

    name = "akshare"

    def is_enabled(self, config: dict) -> bool:
        """检查 AkShare 是否启用"""
        return config.get("sources", {}).get("akshare", {}).get("enabled", False)

    async def fetch(self, config: dict) -> list[NewsItem]:
        """从 AkShare 获取金融数据"""
        items: list[NewsItem] = []

        akshare_config = config.get("sources", {}).get("akshare", {})
        enabled_data_sources = akshare_config.get("data_sources", [])

        # 在线程池中执行同步的 AkShare 调用
        loop = asyncio.get_event_loop()

        for data_source in enabled_data_sources:
            try:
                if data_source == "insurance_stocks":
                    stocks = await loop.run_in_executor(None, self._fetch_insurance_stocks)
                    items.extend(stocks)
                elif data_source == "macro_data":
                    macro = await loop.run_in_executor(None, self._fetch_macro_data)
                    items.extend(macro)
                elif data_source == "stock_news":
                    news = await loop.run_in_executor(None, self._fetch_stock_news)
                    items.extend(news)
                elif data_source == "concept_stocks":
                    concepts = await loop.run_in_executor(None, self._fetch_concept_stocks)
                    items.extend(concepts)
            except Exception as e:
                print(f"[AkShare] 采集 {data_source} 失败: {e}")

        return items

    def _fetch_insurance_stocks(self) -> list[NewsItem]:
        """获取保险板块股票行情数据"""
        items = []
        try:
            import akshare as ak

            # 获取保险行业股票列表
            stock_df = ak.insurance_stock_spot()
            if stock_df is not None and not stock_df.empty:
                today = date.today().isoformat()

                for _, row in stock_df.head(10).iterrows():
                    # 生成数据分析类资讯
                    title = f"【股票行情】{row.get('名称', '保险股')}: {row.get('最新价', 'N/A')}元"

                    summary = f"""保险板块个股行情播报：
• 股票名称：{row.get('名称', 'N/A')}
• 最新价：{row.get('最新价', 'N/A')}元
• 涨跌幅：{row.get('涨跌幅', 'N/A')}%
• 涨跌额：{row.get('涨跌额', 'N/A')}元
• 成交量：{row.get('成交量', 'N/A')}手
• 成交额：{row.get('成交额', 'N/A')}万元
• 换手率：{row.get('换手率', 'N/A')}%"""

                    item = NewsItem(
                        title=title,
                        url=f"https://quote.eastmoney.com/sz{row.get('代码', '0000')}.html",
                        source_name="AkShare-股票行情",
                        source_type="data_api",
                        content=summary,
                        published_at=datetime.now(),
                        category="industry",
                    )
                    item.ai_score = 75  # 基础分数
                    items.append(item)

        except Exception as e:
            print(f"[AkShare] 保险股票行情获取失败: {e}")

        return items

    def _fetch_macro_data(self) -> list[NewsItem]:
        """获取宏观数据（GDP、CPI等）"""
        items = []
        try:
            import akshare as ak

            # GDP 数据
            try:
                gdp_df = ak.macro_china_gdp()
                if gdp_df is not None and not gdp_df.empty:
                    latest = gdp_df.iloc[-1]
                    title = f"【宏观数据】中国{latest.get('季度', '当季')}GDP: {latest.get('国内生产总值-绝对值', 0)/10000:.2f}万亿元 同比+{latest.get('国内生产总值-同比增长', 0)}%"

                    summary = f"""宏观经济数据更新：
• 统计季度：{latest.get('季度', 'N/A')}
• GDP总量：{latest.get('国内生产总值-绝对值', 0)/10000:.2f}万亿元
• GDP同比增长：{latest.get('国内生产总值-同比增长', 'N/A')}%
• 第一产业：{latest.get('第一产业-绝对值', 0)/10000:.2f}万亿元 (同比+{latest.get('第一产业-同比增长', 0)}%)
• 第二产业：{latest.get('第二产业-绝对值', 0)/10000:.2f}万亿元 (同比+{latest.get('第二产业-同比增长', 0)}%)
• 第三产业：{latest.get('第三产业-绝对值', 0)/10000:.2f}万亿元 (同比+{latest.get('第三产业-同比增长', 0)}%)

宏观数据对保险行业的资产配置和负债端均有重要影响。"""

                    item = NewsItem(
                        title=title,
                        url="https://data.stats.gov.cn/easyquery.htm?cn=B01",
                        source_name="AkShare-宏观数据",
                        source_type="data_api",
                        content=summary,
                        published_at=datetime.now(),
                        category="research",
                    )
                    item.ai_score = 80
                    items.append(item)
            except Exception as e:
                print(f"[AkShare] GDP数据获取失败: {e}")

            # CPI 数据
            try:
                cpi_df = ak.macro_china_cpi()
                if cpi_df is not None and not cpi_df.empty:
                    latest = cpi_df.iloc[-1]
                    title = f"【宏观数据】中国CPI数据: {latest.get('月份', '当月')}CPI同比+{latest.get('全国-同比增长', 0)}%"

                    summary = f"""居民消费价格指数(CPI)数据：
• 统计月份：{latest.get('月份', 'N/A')}
• CPI当月：{latest.get('全国-当月', 'N/A')}
• CPI当月同比：+{latest.get('全国-同比增长', 'N/A')}%
• CPI当月环比：{latest.get('全国-环比增长', 'N/A')}%
• CPI累计：{latest.get('全国-累计', 'N/A')}

CPI数据是保险产品定价的重要参考，影响预定利率调整预期。"""

                    item = NewsItem(
                        title=title,
                        url="https://data.stats.gov.cn/easyquery.htm?cn=A01",
                        source_name="AkShare-宏观数据",
                        source_type="data_api",
                        content=summary,
                        published_at=datetime.now(),
                        category="research",
                    )
                    item.ai_score = 78
                    items.append(item)
            except Exception as e:
                print(f"[AkShare] CPI数据获取失败: {e}")

            # 存款准备金率
            try:
                reserve_df = ak.macro_china_reserve_requirement_ratio()
                if reserve_df is not None and not reserve_df.empty:
                    latest = reserve_df.iloc[-1]
                    title = f"【宏观数据】存款准备金率: {latest.get('公布日期', '最新')}调整至{latest.get('大型金融机构存款准备金率', 'N/A')}%"

                    summary = f"""存款准备金率(RRR)调整：
• 公布日期：{latest.get('公布日期', 'N/A')}
• 大型金融机构：{latest.get('大型金融机构存款准备金率', 'N/A')}%
• 中小金融机构：{latest.get('中小金融机构存款准备金率', 'N/A')}%
• 调整幅度：{latest.get('调整幅度(bp)', 'N/A')}bp

准备金率影响银行资金面，间接影响保险资金运用收益率。"""

                    item = NewsItem(
                        title=title,
                        url="https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125440/125497/index.html",
                        source_name="AkShare-宏观数据",
                        source_type="data_api",
                        content=summary,
                        published_at=datetime.now(),
                        category="research",
                    )
                    item.ai_score = 82
                    items.append(item)
            except Exception as e:
                print(f"[AkShare] 准备金率数据获取失败: {e}")

        except Exception as e:
            print(f"[AkShare] 宏观数据获取失败: {e}")

        return items

    def _fetch_stock_news(self) -> list[NewsItem]:
        """获取财经新闻"""
        items = []
        try:
            import akshare as ak

            # 获取财经新闻
            news_df = ak.stock_news_em(symbol="保险")
            if news_df is not None and not news_df.empty:
                for _, row in news_df.head(5).iterrows():
                    item = NewsItem(
                        title=row.get("新闻标题", "财经新闻"),
                        url=row.get("新闻链接", ""),
                        source_name="AkShare-财经新闻",
                        source_type="data_api",
                        content=row.get("新闻内容", ""),
                        published_at=datetime.now(),
                        category="industry",
                    )
                    item.ai_score = 70
                    items.append(item)

        except Exception as e:
            print(f"[AkShare] 财经新闻获取失败: {e}")

        return items

    def _fetch_concept_stocks(self) -> list[NewsItem]:
        """获取概念板块数据"""
        items = []
        try:
            import akshare as ak

            # 获取保险概念板块
            concept_df = ak.stock_board_concept_name_em()
            if concept_df is not None and not concept_df.empty:
                # 查找保险相关概念
                insurance_concepts = concept_df[
                    concept_df["板块名称"].str.contains("保险|养老金|健康险|人寿", na=False)
                ]

                for _, row in insurance_concepts.head(5).iterrows():
                    title = f"【概念板块】{row.get('板块名称', '保险概念')}: {row.get('涨跌幅', 'N/A')}%"

                    summary = f"""保险相关概念板块行情：
• 板块名称：{row.get('板块名称', 'N/A')}
• 涨跌幅：{row.get('涨跌幅', 'N/A')}%
• 上涨家数：{row.get('上涨家数', 'N/A')}
• 下跌家数：{row.get('下跌家数', 'N/A')}
• 总市值：{row.get('总市值', 'N/A')}亿
• 成交额：{row.get('成交额', 'N/A')}亿

概念板块表现反映市场对细分赛道的关注度。"""

                    item = NewsItem(
                        title=title,
                        url=f"https://quote.eastmoney.com/center/boardlist.html#board_type=concept",
                        source_name="AkShare-概念板块",
                        source_type="data_api",
                        content=summary,
                        published_at=datetime.now(),
                        category="industry",
                    )
                    item.ai_score = 72
                    items.append(item)

        except Exception as e:
            print(f"[AkShare] 概念板块获取失败: {e}")

        return items


# 便捷函数：测试 AkShare 连接
def test_akshare_connection() -> dict:
    """测试 AkShare 连接并返回可用数据源"""
    result = {
        "connected": False,
        "data_sources": [],
        "error": None,
    }

    try:
        import akshare as ak

        result["connected"] = True
        result["data_sources"] = [
            "insurance_stocks - 保险股票行情",
            "macro_data - 宏观数据(GDP/CPI/准备金率)",
            "stock_news - 财经新闻",
            "concept_stocks - 概念板块",
        ]

        # 测试基础数据获取
        try:
            gdp_df = ak.macro_china_gdp()
            result["gdp_available"] = True
            result["gdp_latest"] = gdp_df.iloc[-1].to_dict() if not gdp_df.empty else None
        except:
            result["gdp_available"] = False

        try:
            cpi_df = ak.macro_china_cpi()
            result["cpi_available"] = True
            result["cpi_latest"] = cpi_df.iloc[-1].to_dict() if not cpi_df.empty else None
        except:
            result["cpi_available"] = False

    except ImportError:
        result["error"] = "akshare 未安装，请运行: pip install akshare"
    except Exception as e:
        result["error"] = str(e)

    return result
