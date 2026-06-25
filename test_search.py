#!/usr/bin/env python3
"""测试搜索引擎采集"""

import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.search_collector import SearchCollector

async def test_search():
    print("\n" + "="*60)
    print("🔍 测试搜索引擎采集")
    print("="*60 + "\n")
    
    collector = SearchCollector()
    
    # 测试单个关键词搜索
    print("📌 测试单个关键词搜索...")
    results = await collector.search("保险 监管 政策 2026")
    print(f"   找到 {len(results)} 条结果")
    for r in results[:3]:
        print(f"   - {r.title[:50]}...")
        print(f"     来源: {r.source}")
    print()
    
    # 测试保险新闻搜索
    print("📌 测试保险新闻搜索...")
    items = await collector.search_insurance_news(num_results_per_query=5)
    print(f"   共获取 {len(items)} 条新闻")
    for item in items[:5]:
        print(f"   - {item.title[:50]}...")
        print(f"     来源: {item.source_name}")
    print()
    
    await collector.close()
    
    print("="*60)
    print("✅ 搜索引擎采集测试完成!")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(test_search())
