"""InsureScope Skill 封装

借鉴 AIHOT 的 Skill 模式，提供标准化的 Agent 调用接口
支持: 查询日报、搜索资讯、获取分类等
"""

from __future__ import annotations
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Literal
from dataclasses import dataclass

from src.config import get_project_root, load_config


@dataclass
class QueryResult:
    """查询结果"""
    items: list[dict]
    total: int
    date_range: str
    query_info: dict


class InsureScopeSkill:
    """InsureScope Skill - 保险资讯查询 Skill
    
    使用示例:
        skill = InsureScopeSkill()
        
        # 查询今日日报
        result = skill.get_daily()
        
        # 搜索关键词
        result = skill.search("人工智能", days=7)
        
        # 按分类查询
        result = skill.query_by_category("regulation", days=3)
    """

    def __init__(self, data_dir: Optional[Path] = None):
        """初始化 Skill
        
        Args:
            data_dir: 数据目录，默认为项目 data/summaries
        """
        if data_dir is None:
            data_dir = get_project_root() / "data" / "summaries"
        self.data_dir = data_dir
        self.config = load_config()

    def _load_summary(self, target_date: str) -> Optional[dict]:
        """加载指定日期的摘要数据"""
        filepath = self.data_dir / f"{target_date}.json"
        if not filepath.exists():
            return None
        return json.loads(filepath.read_text(encoding="utf-8"))

    def _load_summaries_in_range(self, start: str, end: str) -> list[dict]:
        """加载日期范围内的摘要"""
        results = []
        try:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
            end_date = datetime.strptime(end, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("日期格式错误，应为 YYYY-MM-DD")

        current = start_date
        while current <= end_date:
            data = self._load_summary(current.isoformat())
            if data:
                results.append(data)
            current += timedelta(days=1)

        return results

    def get_daily(self, target_date: Optional[str] = None) -> QueryResult:
        """获取每日保险日报
        
        Args:
            target_date: 日期 YYYY-MM-DD，默认为今天
            
        Returns:
            QueryResult 包含当日所有资讯
        """
        d = target_date or date.today().isoformat()
        data = self._load_summary(d)
        
        if not data:
            return QueryResult(
                items=[],
                total=0,
                date_range=d,
                query_info={"type": "daily", "date": d}
            )
        
        return QueryResult(
            items=data.get("items", []),
            total=data.get("total_items", 0),
            date_range=d,
            query_info={
                "type": "daily",
                "date": d,
                "avg_score": data.get("avg_score", 0),
                "highlights_count": len(data.get("highlights", []))
            }
        )

    def get_curated(self, days: int = 1, min_score: float = 7.0) -> QueryResult:
        """获取精选资讯（高分内容）
        
        Args:
            days: 回溯天数，最多30天
            min_score: 最低评分阈值
            
        Returns:
            QueryResult 包含精选资讯
        """
        days = min(days, 30)  # 限制最大天数
        end = date.today()
        start = end - timedelta(days=days - 1)
        
        summaries = self._load_summaries_in_range(start.isoformat(), end.isoformat())
        
        all_items = []
        for s in summaries:
            for item in s.get("items", []):
                if item.get("ai_score", 0) >= min_score:
                    all_items.append(item)
        
        # 按分数降序
        all_items.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
        
        return QueryResult(
            items=all_items,
            total=len(all_items),
            date_range=f"{start.isoformat()} to {end.isoformat()}",
            query_info={
                "type": "curated",
                "days": days,
                "min_score": min_score
            }
        )

    def query_by_category(
        self,
        category: Literal["regulation", "product", "industry", "research", "claims"],
        days: int = 7
    ) -> QueryResult:
        """按分类查询资讯
        
        Args:
            category: 分类名称
                - regulation: 监管政策
                - product: 产品发布
                - industry: 行业动态
                - research: 论文研究
                - claims: 理赔案例
            days: 回溯天数
            
        Returns:
            QueryResult 包含该分类的资讯
        """
        valid_categories = ["regulation", "product", "industry", "research", "claims"]
        if category not in valid_categories:
            raise ValueError(f"无效分类: {category}，有效值: {valid_categories}")
        
        days = min(days, 30)
        end = date.today()
        start = end - timedelta(days=days - 1)
        
        summaries = self._load_summaries_in_range(start.isoformat(), end.isoformat())
        
        items = []
        for s in summaries:
            cat_items = s.get("by_category", {}).get(category, [])
            items.extend(cat_items)
        
        items.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
        
        # 获取分类信息
        cat_config = self.config.get("categories", {}).get(category, {})
        
        return QueryResult(
            items=items,
            total=len(items),
            date_range=f"{start.isoformat()} to {end.isoformat()}",
            query_info={
                "type": "category",
                "category": category,
                "category_name_zh": cat_config.get("name_zh", category),
                "category_name_en": cat_config.get("name_en", category),
                "days": days
            }
        )

    def search(
        self,
        keyword: str,
        days: int = 7,
        category: Optional[str] = None
    ) -> QueryResult:
        """关键词搜索
        
        Args:
            keyword: 搜索关键词
            days: 回溯天数
            category: 可选，限制分类
            
        Returns:
            QueryResult 包含匹配资讯
        """
        if not keyword or len(keyword.strip()) == 0:
            raise ValueError("关键词不能为空")
        
        days = min(days, 30)
        end = date.today()
        start = end - timedelta(days=days - 1)
        
        summaries = self._load_summaries_in_range(start.isoformat(), end.isoformat())
        
        q_lower = keyword.lower()
        results = []
        
        for s in summaries:
            for item in s.get("items", []):
                # 分类过滤
                if category and item.get("category") != category:
                    continue
                
                # 搜索匹配
                searchable = f"{item.get('title', '')} {item.get('ai_summary', '')} {' '.join(item.get('ai_tags', []))} {item.get('why_it_matters', '')}".lower()
                if q_lower in searchable:
                    results.append(item)
        
        results.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
        
        return QueryResult(
            items=results,
            total=len(results),
            date_range=f"{start.isoformat()} to {end.isoformat()}",
            query_info={
                "type": "search",
                "keyword": keyword,
                "days": days,
                "category": category
            }
        )

    def get_highlights(self, days: int = 7) -> QueryResult:
        """获取高分资讯（AI评分 >= 9.0）
        
        Args:
            days: 回溯天数
            
        Returns:
            QueryResult 包含高分资讯
        """
        days = min(days, 30)
        end = date.today()
        start = end - timedelta(days=days - 1)
        
        summaries = self._load_summaries_in_range(start.isoformat(), end.isoformat())
        
        highlights = []
        for s in summaries:
            for item in s.get("highlights", []):
                highlights.append(item)
        
        # 去重（按 URL）
        seen_urls = set()
        unique_highlights = []
        for item in highlights:
            url = item.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                unique_highlights.append(item)
        
        unique_highlights.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
        
        return QueryResult(
            items=unique_highlights,
            total=len(unique_highlights),
            date_range=f"{start.isoformat()} to {end.isoformat()}",
            query_info={
                "type": "highlights",
                "days": days,
                "min_score": 9.0
            }
        )

    def get_stats(self, days: int = 7) -> dict:
        """获取统计信息
        
        Args:
            days: 回溯天数
            
        Returns:
            统计信息字典
        """
        days = min(days, 30)
        end = date.today()
        start = end - timedelta(days=days - 1)
        
        summaries = self._load_summaries_in_range(start.isoformat(), end.isoformat())
        
        total_items = sum(s.get("total_items", 0) for s in summaries)
        avg_scores = [s.get("avg_score", 0) for s in summaries if s.get("avg_score", 0) > 0]
        
        # 分类统计
        category_counts = {}
        for s in summaries:
            for cat, items in s.get("by_category", {}).items():
                category_counts[cat] = category_counts.get(cat, 0) + len(items)
        
        return {
            "date_range": f"{start.isoformat()} to {end.isoformat()}",
            "days": days,
            "total_summaries": len(summaries),
            "total_items": total_items,
            "avg_score": round(sum(avg_scores) / len(avg_scores), 1) if avg_scores else 0,
            "category_distribution": category_counts,
            "daily_average": round(total_items / days, 1) if days > 0 else 0
        }


# 便捷函数接口
def get_daily(date: Optional[str] = None) -> QueryResult:
    """获取日报"""
    return InsureScopeSkill().get_daily(date)


def search(keyword: str, days: int = 7) -> QueryResult:
    """搜索资讯"""
    return InsureScopeSkill().search(keyword, days)


def get_by_category(category: str, days: int = 7) -> QueryResult:
    """按分类查询"""
    return InsureScopeSkill().query_by_category(category, days)


def get_highlights(days: int = 7) -> QueryResult:
    """获取高分资讯"""
    return InsureScopeSkill().get_highlights(days)
