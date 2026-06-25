"""Reddit 采集器 - 采集保险相关子版块"""

from __future__ import annotations
import httpx
from datetime import datetime

from src.collectors import BaseCollector, register_collector
from src.models import NewsItem
from src.config import get_env_var


@register_collector("reddit")
class RedditCollector(BaseCollector):
    """从 Reddit 保险相关子版块采集内容"""

    name = "reddit"

    async def fetch(self, config: dict) -> list[NewsItem]:
        reddit_config = config.get("sources", {}).get("reddit", {})
        if not reddit_config.get("enabled", False):
            return []

        subreddits = reddit_config.get("subreddits", [])
        min_score = reddit_config.get("min_score", 10)
        fetch_top = reddit_config.get("fetch_top_posts", 20)

        items: list[NewsItem] = []

        # 使用公开 JSON 端点（无需 OAuth）
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            headers = {"User-Agent": "InsureScope/1.0"}

            for sub in subreddits:
                try:
                    url = f"https://www.reddit.com/r/{sub}/hot.json?limit={fetch_top}"
                    resp = await client.get(url, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()

                    for post in data.get("data", {}).get("children", []):
                        d = post.get("data", {})
                        score = d.get("score", 0)
                        if score < min_score:
                            continue

                        item = NewsItem(
                            title=d.get("title", ""),
                            url=f"https://reddit.com{d.get('permalink', '')}",
                            source_name=f"r/{sub}",
                            source_type="reddit",
                            content=d.get("selftext", "")[:2000],
                            published_at=datetime.fromtimestamp(d.get("created_utc", 0)),
                            language="en",
                            engagement_score=float(score),
                            comment_count=d.get("num_comments", 0),
                            upvote_ratio=d.get("upvote_ratio"),
                        )
                        items.append(item)

                except Exception as e:
                    print(f"[Reddit] 采集 r/{sub} 失败: {e}")

        return items
