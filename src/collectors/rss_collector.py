"""RSS 信息源采集器"""

from __future__ import annotations
import httpx
import feedparser
import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from src.collectors import BaseCollector, register_collector
from src.models import NewsItem

if TYPE_CHECKING:
    pass


@register_collector("rss")
class RSSCollector(BaseCollector):
    """从 RSS 订阅源采集保险资讯"""

    name = "rss"

    def __init__(self):
        super().__init__()
        self._translator = None
        self._translation_enabled = False

    def _get_translator(self):
        """延迟加载翻译器"""
        if self._translator is None:
            try:
                from src.translation import get_translation_service
                # 自动选择最佳翻译服务
                self._translator = get_translation_service("auto")
                print(f"[RSS] 翻译服务已就绪")
            except Exception as e:
                print(f"[RSS] 翻译模块加载失败: {e}")
                self._translator = None
        return self._translator

    async def _translate_text(self, text: str, source_lang: str = "en") -> str:
        """翻译文本"""
        if not text or not text.strip():
            return text

        translator = self._get_translator()
        if translator is None:
            return text

        # 检查是否需要翻译（非中文语言才翻译）
        if source_lang == "zh":
            return text

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: translator.translate(text, source_lang, "zh")
            )
            if result.success:
                return result.translated
            else:
                print(f"[RSS] 翻译失败: {result.error}")
                return text
        except Exception as e:
            print(f"[RSS] 翻译异常: {e}")
            return text

    async def fetch(self, config: dict) -> list[NewsItem]:
        items: list[NewsItem] = []
        rss_sources = config.get("sources", {}).get("rss", [])

        # 检查是否启用翻译
        self._translation_enabled = any(
            source.get("translate", False) for source in rss_sources
        )

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for source in rss_sources:
                if not source.get("enabled", True):
                    continue

                try:
                    print(f"[RSS] 采集 {source['name']}...")
                    resp = await client.get(source["url"])
                    resp.raise_for_status()
                    feed = feedparser.parse(resp.text)

                    need_translate = source.get("translate", False)
                    source_lang = source.get("language", "en")

                    for entry in feed.entries[:20]:
                        content = ""
                        if hasattr(entry, "summary"):
                            content = entry.summary
                        elif hasattr(entry, "content"):
                            content = entry.content[0].value if entry.content else ""

                        published = None
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            published = datetime(*entry.published_parsed[:6])

                        title = getattr(entry, "title", "Untitled")

                        # 翻译标题和内容
                        if need_translate and source_lang != "zh":
                            print(f"[RSS] 翻译: {title[:30]}...")
                            title = await self._translate_text(title, source_lang)
                            if content:
                                content = await self._translate_text(content[:3000], source_lang)

                        item = NewsItem(
                            title=title,
                            url=getattr(entry, "link", ""),
                            source_name=source["name"],
                            source_type="rss",
                            content=content[:2000],
                            published_at=published,
                            language="zh" if need_translate else source_lang,
                        )
                        if source.get("category_hint"):
                            item.category = source["category_hint"]
                        items.append(item)

                except Exception as e:
                    print(f"[RSS] 采集 {source['name']} 失败: {e}")

        return items
