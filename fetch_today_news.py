#!/usr/bin/env python3
"""采集今日真实保险新闻"""

import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.rss_collector import RSSCollector
from src.config import load_config
from datetime import datetime

async def fetch_today_news():
    """从RSS源采集今日新闻"""
    config = load_config()
    
    print("📡 正在从RSS源采集保险新闻...\n")
    
    collector = RSSCollector()
    items = await collector.fetch(config)
    
    print(f"✅ 共采集到 {len(items)} 条资讯\n")
    
    # 按来源分组
    by_source = {}
    for item in items:
        source = item.source_name
        by_source.setdefault(source, []).append(item)
    
    # 显示结果
    for source, items_list in by_source.items():
        print(f"📰 {source}: {len(items_list)} 条")
        for i, item in enumerate(items_list[:3], 1):  # 只显示前3条
            print(f"   {i}. {item.title[:60]}...")
        if len(items_list) > 3:
            print(f"   ... 还有 {len(items_list) - 3} 条")
        print()
    
    return items

if __name__ == "__main__":
    items = asyncio.run(fetch_today_news())
