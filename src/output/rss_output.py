"""RSS 输出模块

生成 RSS Feed 供外部订阅，参考 AIHOT 的 RSS 模式
"""

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.config import get_project_root, load_config

if TYPE_CHECKING:
    from src.models import NewsItem


RSS_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{title}</title>
    <description>{description}</description>
    <link>{link}</link>
    <atom:link href="{link}/rss.xml" rel="self" type="application/rss+xml"/>
    <language>{language}</language>
    <lastBuildDate>{last_build_date}</lastBuildDate>
    <generator>InsureScope v1.0.0</generator>
{items}
  </channel>
</rss>"""

RSS_ITEM = """    <item>
      <title>{title}</title>
      <link>{url}</link>
      <description>{description}</description>
      <source>{source_name}</source>
      <category>{category}</category>
      <pubDate>{pub_date}</pubDate>
    </item>"""


class RSSFeedGenerator:
    """RSS Feed 生成器"""

    def __init__(self, config: dict):
        self.config = config
        rss_config = config.get("output", {}).get("rss_output", {})
        self.feed_title_zh = rss_config.get("feed_title_zh", "InsureScope 保险资讯")
        self.feed_title_en = rss_config.get("feed_title_en", "InsureScope Insurance News")
        self.feed_description_zh = rss_config.get("feed_description_zh", "AI 驱动的每日保险信息聚合")
        self.feed_description_en = rss_config.get("feed_description_en", "AI-Curated Daily Insurance Information Digest")

    def generate_curated_feed(self, items: list["NewsItem"], lang: str = "zh") -> str:
        """生成精选资讯 RSS Feed"""
        title = self.feed_title_zh if lang == "zh" else self.feed_title_en
        description = self.feed_description_zh if lang == "zh" else self.feed_description_en
        language = "zh-cn" if lang == "zh" else "en"

        items_xml = []
        for item in items:
            desc = item.ai_summary or item.content[:200]
            category_name = item.category
            if lang == "zh" and item.category in self.config.get("categories", {}):
                category_name = self.config["categories"][item.category].get("name_zh", item.category)

            items_xml.append(RSS_ITEM.format(
                title=item.title.replace("&", "&amp;").replace("<", "&lt;"),
                url=item.url,
                description=desc.replace("&", "&amp;").replace("<", "&lt;"),
                source_name=item.source_name,
                category=category_name,
                pub_date=item.published_at.strftime("%a, %d %b %Y %H:%M:%S +0800") if item.published_at else "",
            ))

        return RSS_TEMPLATE.format(
            title=title,
            description=description,
            link="https://insure-scope.example.com",
            language=language,
            last_build_date=datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0800"),
            items="\n".join(items_xml),
        )

    def generate_daily_feed(self, items: list["NewsItem"], report_date: str, lang: str = "zh") -> str:
        """生成日报 RSS Feed"""
        suffix = "日报" if lang == "zh" else "Daily"
        title = f"{self.feed_title_zh if lang == 'zh' else self.feed_title_en} - {suffix} {report_date}"

        return self.generate_curated_feed(items, lang)

    def save_feed(self, feed_content: str, filename: str) -> Path:
        """保存 RSS Feed 到文件"""
        output_dir = get_project_root() / "data" / "rss"
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / filename
        filepath.write_text(feed_content, encoding="utf-8")
        return filepath
