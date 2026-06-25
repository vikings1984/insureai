"""API 服务器

提供 REST API 接口，参考 AIHOT 的 API 模式
支持: 日报查询、精选列表、分类查询、关键词搜索
"""

from __future__ import annotations
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import get_project_root, load_config


class ItemResponse(BaseModel):
    title: str
    url: str
    source_name: str
    source_type: str
    content: str = ""
    published_at: Optional[str] = None
    ai_score: float = 0.0
    insurance_relevance: float = 0.0
    category: str = ""
    ai_summary: str = ""
    ai_tags: list[str] = []
    whats_new: str = ""
    why_it_matters: str = ""
    key_details: str = ""
    background: str = ""


class DailyReportResponse(BaseModel):
    date: str
    total_items: int
    avg_score: float
    items: list[ItemResponse]
    highlights: list[ItemResponse]


class CategoryListResponse(BaseModel):
    categories: dict[str, dict]


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(
        title="InsureScope API",
        description="AI 驱动的保险信息聚合系统 API",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _load_summary(target_date: str) -> dict:
        """加载指定日期的摘要数据"""
        summary_dir = get_project_root() / "data" / "summaries"
        filepath = summary_dir / f"{target_date}.json"
        if not filepath.exists():
            raise HTTPException(status_code=404, detail=f"未找到 {target_date} 的数据")
        return json.loads(filepath.read_text(encoding="utf-8"))

    def _load_summaries_in_range(start: str, end: str) -> list[dict]:
        """加载日期范围内的摘要"""
        summary_dir = get_project_root() / "data" / "summaries"
        results = []
        try:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
            end_date = datetime.strptime(end, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

        current = start_date
        while current <= end_date:
            filepath = summary_dir / f"{current.isoformat()}.json"
            if filepath.exists():
                results.append(json.loads(filepath.read_text(encoding="utf-8")))
            current += timedelta(days=1)

        return results

    @app.get("/")
    async def root():
        return {
            "name": "InsureScope API",
            "version": "1.0.0",
            "description": "AI 驱动的保险信息聚合系统",
            "endpoints": [
                "/api/daily - 今日日报",
                "/api/daily/{date} - 指定日期日报",
                "/api/curated - 精选资讯",
                "/api/category/{category} - 按分类查询",
                "/api/search - 关键词搜索",
                "/api/categories - 分类列表",
            ],
        }

    @app.get("/api/daily", response_model=DailyReportResponse)
    async def get_daily_report(
        target_date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    ):
        """获取每日保险日报"""
        d = target_date or date.today().isoformat()
        data = _load_summary(d)

        items = [ItemResponse(**item) for item in data.get("items", [])]
        highlights = [ItemResponse(**item) for item in data.get("highlights", [])]

        return DailyReportResponse(
            date=data["date"],
            total_items=data["total_items"],
            avg_score=data["avg_score"],
            items=items,
            highlights=highlights,
        )

    @app.get("/api/daily/{target_date}", response_model=DailyReportResponse)
    async def get_daily_report_by_date(target_date: str):
        """获取指定日期的日报"""
        data = _load_summary(target_date)

        items = [ItemResponse(**item) for item in data.get("items", [])]
        highlights = [ItemResponse(**item) for item in data.get("highlights", [])]

        return DailyReportResponse(
            date=data["date"],
            total_items=data["total_items"],
            avg_score=data["avg_score"],
            items=items,
            highlights=highlights,
        )

    @app.get("/api/curated")
    async def get_curated(
        days: int = Query(1, description="回溯天数，最多7天", ge=1, le=7),
    ):
        """获取精选资讯（时间流）"""
        end = date.today()
        start = end - timedelta(days=days - 1)

        summaries = _load_summaries_in_range(start.isoformat(), end.isoformat())

        all_items = []
        for s in summaries:
            for item in s.get("items", []):
                if item.get("ai_score", 0) >= 7.0:
                    all_items.append(item)

        # 按分数降序
        all_items.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
        return {"total": len(all_items), "items": all_items}

    @app.get("/api/category/{category}")
    async def get_by_category(
        category: str,
        days: int = Query(1, description="回溯天数", ge=1, le=7),
    ):
        """按分类查询资讯"""
        valid_categories = ["regulation", "product", "industry", "research", "claims"]
        if category not in valid_categories:
            raise HTTPException(
                status_code=400,
                detail=f"无效分类: {category}，有效值: {valid_categories}",
            )

        end = date.today()
        start = end - timedelta(days=days - 1)

        summaries = _load_summaries_in_range(start.isoformat(), end.isoformat())

        items = []
        for s in summaries:
            cat_items = s.get("by_category", {}).get(category, [])
            items.extend(cat_items)

        items.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
        return {"category": category, "total": len(items), "items": items}

    @app.get("/api/search")
    async def search_items(
        q: str = Query(..., description="搜索关键词"),
        days: int = Query(7, description="回溯天数", ge=1, le=7),
    ):
        """关键词搜索"""
        end = date.today()
        start = end - timedelta(days=days - 1)

        summaries = _load_summaries_in_range(start.isoformat(), end.isoformat())

        q_lower = q.lower()
        results = []
        for s in summaries:
            for item in s.get("items", []):
                searchable = f"{item.get('title', '')} {item.get('ai_summary', '')} {' '.join(item.get('ai_tags', []))}".lower()
                if q_lower in searchable:
                    results.append(item)

        results.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
        return {"query": q, "total": len(results), "items": results}

    @app.get("/api/categories", response_model=CategoryListResponse)
    async def get_categories():
        """获取分类列表"""
        config = load_config()
        cats = config.get("categories", {})
        result = {}
        for key, val in cats.items():
            result[key] = {
                "name_zh": val.get("name_zh", key),
                "name_en": val.get("name_en", key),
                "description_zh": val.get("description_zh", ""),
                "keywords_zh": val.get("keywords_zh", []),
                "keywords_en": val.get("keywords_en", []),
            }
        return CategoryListResponse(categories=result)

    return app


def main():
    """启动 API 服务器"""
    import uvicorn

    config = load_config()
    output_config = config.get("output", {}).get("api", {})
    host = output_config.get("host", "0.0.0.0")
    port = output_config.get("port", 8080)

    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
