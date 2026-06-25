"""微信公众号采集器（通过 RSS Bridge）"""

from __future__ import annotations
import httpx
import feedparser
from datetime import datetime

from src.collectors import BaseCollector, register_collector
from src.models import NewsItem
from src.config import get_env_var


@register_collector("wechat")
class WeChatCollector(BaseCollector):
    """通过 RSS Bridge 采集微信公众号内容"""

    name = "wechat"

    async def fetch(self, config: dict) -> list[NewsItem]:
        wechat_config = config.get("sources", {}).get("wechat", {})
        if not wechat_config.get("enabled", False):
            return []

        bridge_url = get_env_var("WECHAT_RSS_BRIDGE_URL", "")
        if not bridge_url:
            print("[WeChat] 未配置 RSS Bridge URL，跳过")
            return []

        accounts = wechat_config.get("accounts", [])
        items: list[NewsItem] = []

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for account in accounts:
                try:
                    # 使用 RSS Bridge 的微信频道端点
                    url = f"{bridge_url}?action=display&bridge=WeChat&context=By+ID&id={account}&format=Atom"
                    resp = await client.get(url)
                    resp.raise_for_status()
                    feed = feedparser.parse(resp.text)

                    for entry in feed.entries[:10]:
                        content = ""
                        if hasattr(entry, "summary"):
                            content = entry.summary
                        elif hasattr(entry, "content"):
                            content = entry.content[0].value if entry.content else ""

                        published = None
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            published = datetime(*entry.published_parsed[:6])

                        item = NewsItem(
                            title=getattr(entry, "title", "Untitled"),
                            url=getattr(entry, "link", ""),
                            source_name=f"微信公众号: {account}",
                            source_type="wechat",
                            content=content[:2000],
                            published_at=published,
                            language="zh",
                        )
                        items.append(item)

                except Exception as e:
                    print(f"[WeChat] 采集 {account} 失败: {e}")

        return items
