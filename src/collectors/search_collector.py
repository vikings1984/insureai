"""搜索引擎采集器 (SerpAPI)

通过 SerpAPI 搜索获取保险相关新闻
支持 Google、Bing、DuckDuckGo 等搜索引擎
"""

from __future__ import annotations
import asyncio
import os
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

import httpx

from src.models import NewsItem
from src.config import get_project_root


@dataclass
class SearchConfig:
    """搜索配置"""
    engine: str = "google"  # google, bing, duckduckgo
    num_results: int = 20  # 每次搜索返回的结果数
    language: str = "zh-CN"  # 搜索语言
    country: str = "cn"  # 搜索国家
    time_range: str = "d"  # d=今天, w=本周, m=本月


@dataclass
class SearchResult:
    """搜索结果"""
    title: str
    url: str
    snippet: str
    source: str
    date: Optional[str] = None


class SearchCollector:
    """
    基于 SerpAPI 的搜索引擎采集器
    
    SerpAPI 提供了统一的接口来访问 Google、Bing、DuckDuckGo 等搜索引擎的结果
    免费额度: 每月 100 次搜索
    
    使用方式:
        collector = SearchCollector()
        results = await collector.search("保险 监管 政策")
    """

    BASE_URL = "https://serpapi.com/search"

    # 保险行业搜索关键词
    INSURANCE_KEYWORDS = [
        "保险 监管 政策 金融监管总局",
        "保险 行业动态 市场",
        "保险 科技 InsurTech",
        "保险 产品 新规",
        "保险 理赔 纠纷",
        "车险 健康险 寿险",
    ]

    # 排除的域名（低质量或非新闻源）
    EXCLUDE_DOMAINS = [
        "baike.baidu.com",  # 百度百科
        "zhidao.baidu.com",  # 百度知道
        "wenku.baidu.com",  # 百度文库
        "tieba.baidu.com",  # 百度贴吧
    ]

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化采集器
        
        Args:
            api_key: SerpAPI Key，若不提供则从环境变量 SERPAPI_API_KEY 获取
        """
        self.api_key = api_key or os.getenv("SERPAPI_API_KEY")
        self.client = httpx.AsyncClient(timeout=30.0)

    async def search(
        self,
        query: str,
        config: Optional[SearchConfig] = None,
    ) -> list[SearchResult]:
        """
        执行搜索查询
        
        Args:
            query: 搜索关键词
            config: 搜索配置
            
        Returns:
            搜索结果列表
        """
        if not self.api_key:
            print("[SearchCollector] 警告: 未配置 SERPAPI_API_KEY，使用模拟数据")
            return self._get_mock_results(query)

        config = config or SearchConfig()
        
        params = {
            "q": query,
            "api_key": self.api_key,
            "engine": config.engine,
            "num": config.num_results,
            "gl": config.country,
            "hl": config.language,
        }
        
        # 添加时间范围（仅 Google 支持）
        if config.time_range and config.engine == "google":
            params["tbs"] = f"qdr:{config.time_range}"
        
        try:
            response = await self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
            
            return self._parse_results(data, config.engine)
            
        except httpx.HTTPError as e:
            print(f"[SearchCollector] 搜索失败: {e}")
            return self._get_mock_results(query)
        except Exception as e:
            print(f"[SearchCollector] 解析失败: {e}")
            return self._get_mock_results(query)

    def _parse_results(self, data: dict, engine: str) -> list[SearchResult]:
        """解析搜索结果"""
        results = []
        
        if engine == "google":
            news_results = data.get("news_results", [])
            organic_results = data.get("organic_results", [])
            
            for item in news_results:
                if self._is_valid_result(item):
                    results.append(SearchResult(
                        title=item.get("title", ""),
                        url=item.get("link", ""),
                        snippet=item.get("snippet", ""),
                        source=item.get("source", ""),
                        date=item.get("date", ""),
                    ))
            
            # 也从有机结果中提取新闻
            for item in organic_results:
                if self._is_valid_result(item):
                    results.append(SearchResult(
                        title=item.get("title", ""),
                        url=item.get("link", ""),
                        snippet=item.get("snippet", ""),
                        source=item.get("source", ""),
                    ))
        
        elif engine == "bing":
            news_results = data.get("news", {}).get("value", [])
            for item in news_results:
                if self._is_valid_result(item):
                    results.append(SearchResult(
                        title=item.get("name", ""),
                        url=item.get("url", ""),
                        snippet=item.get("description", ""),
                        source=item.get("provider", [{}])[0].get("name", ""),
                        date=item.get("datePublished", ""),
                    ))
        
        elif engine == "duckduckgo":
            news_results = data.get("news_results", [])
            for item in news_results:
                if self._is_valid_result(item):
                    results.append(SearchResult(
                        title=item.get("title", ""),
                        url=item.get("link", ""),
                        snippet=item.get("snippet", ""),
                        source=item.get("source", ""),
                    ))
        
        # 去重（按URL）
        seen = set()
        unique_results = []
        for r in results:
            if r.url not in seen:
                seen.add(r.url)
                unique_results.append(r)
        
        return unique_results

    def _is_valid_result(self, item: dict) -> bool:
        """检查结果是否有效"""
        url = item.get("link", "") or item.get("url", "")
        if not url:
            return False
        
        # 排除低质量域名
        for domain in self.EXCLUDE_DOMAINS:
            if domain in url:
                return False
        
        return True

    async def search_insurance_news(
        self,
        num_results_per_query: int = 10,
    ) -> list[NewsItem]:
        """
        搜索保险行业新闻
        
        Args:
            num_results_per_query: 每个关键词返回的结果数
            
        Returns:
            NewsItem 列表
        """
        config = SearchConfig(num_results=num_results_per_query)
        all_results: list[SearchResult] = []
        
        print(f"[SearchCollector] 开始搜索保险新闻 ({len(self.INSURANCE_KEYWORDS)} 个关键词)...")
        
        for keyword in self.INSURANCE_KEYWORDS:
            results = await self.search(keyword, config)
            all_results.extend(results)
            print(f"  关键词 '{keyword}': {len(results)} 条")
            await asyncio.sleep(0.5)  # 避免请求过快
        
        # 去重
        seen = set()
        unique_results = []
        for r in all_results:
            if r.url not in seen:
                seen.add(r.url)
                unique_results.append(r)
        
        print(f"[SearchCollector] 共获取 {len(unique_results)} 条去重后结果")
        
        # 转换为 NewsItem
        items = []
        for r in unique_results:
            item = NewsItem(
                title=r.title,
                url=r.url,
                content=r.snippet,
                source_name=r.source,
                source_type="search",
            )
            items.append(item)
        
        return items

    def _get_mock_results(self, query: str) -> list[SearchResult]:
        """获取模拟结果（用于测试或无API Key时）"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        return [
            SearchResult(
                title=f"金融监管总局发布保险资金运用管理办法",
                url="https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId=1234567",
                snippet="国家金融监督管理总局今日发布《保险资金运用管理办法》修订版，进一步完善保险资金运用监管制度...",
                source="金融监管总局",
                date=today,
            ),
            SearchResult(
                title=f"多家保险公司发布一季度业绩报告",
                url="https://www.cbimc.cn/news/2026/05/insurance-report",
                snippet="中国人寿、平安保险、太平洋保险等多家上市保险公司发布2026年一季度业绩报告，整体保费收入稳步增长...",
                source="中国银行保险报",
                date=today,
            ),
            SearchResult(
                title=f"新能源车险市场规模突破千亿",
                url="https://www.cbimc.cn/news/2026/05/ev-insurance",
                snippet="随着新能源汽车渗透率持续提升，新能源车险市场快速增长，2026年市场规模有望突破千亿元...",
                source="中国银行保险报",
                date=today,
            ),
        ]

    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
