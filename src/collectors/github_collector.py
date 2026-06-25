"""GitHub 采集器 - 采集保险科技相关仓库动态"""

from __future__ import annotations
import httpx
from datetime import datetime

from src.collectors import BaseCollector, register_collector
from src.models import NewsItem
from src.config import get_env_var


@register_collector("github")
class GitHubCollector(BaseCollector):
    """从 GitHub 采集保险科技相关仓库 Release"""

    name = "github"

    async def fetch(self, config: dict) -> list[NewsItem]:
        github_sources = config.get("sources", {}).get("github", [])
        token = get_env_var("GITHUB_TOKEN")

        items: list[NewsItem] = []
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "InsureScope/1.0",
        }
        if token:
            headers["Authorization"] = f"token {token}"

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for source in github_sources:
                if not source.get("enabled", True):
                    continue

                try:
                    if source["type"] == "repo_releases":
                        owner = source["owner"]
                        repo = source["repo"]
                        url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=10"
                        resp = await client.get(url)
                        resp.raise_for_status()

                        for release in resp.json():
                            item = NewsItem(
                                title=f"[{owner}/{repo}] {release.get('name') or release.get('tag_name', 'Release')}",
                                url=release.get("html_url", ""),
                                source_name=f"GitHub: {owner}/{repo}",
                                source_type="github",
                                content=release.get("body", "")[:2000] or "No release notes.",
                                published_at=datetime.fromisoformat(
                                    release["published_at"].replace("Z", "+00:00")
                                ) if release.get("published_at") else None,
                                language="en",
                            )
                            items.append(item)

                    elif source["type"] == "user_events":
                        username = source["username"]
                        url = f"https://api.github.com/users/{username}/events?per_page=10"
                        resp = await client.get(url)
                        resp.raise_for_status()

                        for event in resp.json():
                            if event.get("type") != "ReleaseEvent":
                                continue
                            repo_name = event.get("repo", {}).get("name", "")
                            payload = event.get("payload", {})
                            release = payload.get("release", {})
                            item = NewsItem(
                                title=f"[{repo_name}] {release.get('tag_name', 'Release')}",
                                url=release.get("html_url", ""),
                                source_name=f"GitHub: {username}",
                                source_type="github",
                                content=release.get("body", "")[:2000] or "",
                                published_at=datetime.fromisoformat(
                                    event["created_at"].replace("Z", "+00:00")
                                ) if event.get("created_at") else None,
                                language="en",
                            )
                            items.append(item)

                except Exception as e:
                    print(f"[GitHub] 采集 {source} 失败: {e}")

        return items
