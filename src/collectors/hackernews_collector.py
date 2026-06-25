"""Hacker News 采集器 - 过滤保险相关内容"""

from __future__ import annotations
import httpx
from datetime import datetime

from src.collectors import BaseCollector, register_collector
from src.models import NewsItem


@register_collector("hackernews")
class HackerNewsCollector(BaseCollector):
    """从 Hacker News 采集保险科技相关内容"""

    name = "hackernews"
    BASE_URL = "https://hacker-news.firebaseio.com/v0"

    async def fetch(self, config: dict) -> list[NewsItem]:
        hn_config = config.get("sources", {}).get("hackernews", {})
        if not hn_config.get("enabled", False):
            return []

        min_score = hn_config.get("min_score", 50)
        fetch_top = hn_config.get("fetch_top_stories", 30)
        keywords = [kw.lower() for kw in hn_config.get("insurance_keywords", [])]

        items: list[NewsItem] = []

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                # 获取 Top Stories
                resp = await client.get(f"{self.BASE_URL}/topstories.json")
                story_ids = resp.json()[:fetch_top]

                for sid in story_ids:
                    try:
                        story_resp = await client.get(f"{self.BASE_URL}/item/{sid}.json")
                        story = story_resp.json()
                        if not story:
                            continue

                        score = story.get("score", 0)
                        if score < min_score:
                            continue

                        title = story.get("title", "")
                        text = story.get("text", "") or ""

                        # 关键词匹配
                        combined = f"{title} {text}".lower()
                        if not any(kw in combined for kw in keywords):
                            continue

                        item = NewsItem(
                            title=title,
                            url=f"https://news.ycombinator.com/item?id={sid}",
                            source_name="Hacker News",
                            source_type="hackernews",
                            content=text[:2000] if text else title,
                            published_at=datetime.fromtimestamp(story.get("time", 0)),
                            language="en",
                            engagement_score=float(score),
                            comment_count=story.get("descendants", 0),
                        )
                        items.append(item)

                    except Exception:
                        continue

            except Exception as e:
                print(f"[HN] 采集失败: {e}")

        return items
