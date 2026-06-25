#!/usr/bin/env python3
"""测试 Skill 模式"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.skill import InsureScopeSkill, get_daily, search, get_by_category

def test_skill():
    print("\n" + "="*60)
    print("🧪 测试 InsureScope Skill 模式")
    print("="*60 + "\n")
    
    skill = InsureScopeSkill()
    
    # 测试 1: 获取日报
    print("📋 测试 1: 获取日报")
    result = skill.get_daily("2026-05-11")
    print(f"  日期: {result.date_range}")
    print(f"  总数: {result.total}")
    print(f"  信息: {result.query_info}")
    print()
    
    # 测试 2: 获取精选
    print("⭐ 测试 2: 获取精选资讯")
    result = skill.get_curated(days=7, min_score=7.0)
    print(f"  总数: {result.total}")
    print(f"  日期范围: {result.date_range}")
    if result.items:
        print(f"  第一条: {result.items[0]['title'][:50]}...")
    print()
    
    # 测试 3: 按分类查询
    print("🏛️ 测试 3: 按分类查询 (regulation)")
    result = skill.query_by_category("regulation", days=7)
    print(f"  分类: {result.query_info.get('category_name_zh')}")
    print(f"  总数: {result.total}")
    print()
    
    # 测试 4: 关键词搜索
    print("🔍 测试 4: 关键词搜索")
    result = skill.search("人工智能", days=7)
    print(f"  关键词: {result.query_info.get('keyword')}")
    print(f"  匹配数: {result.total}")
    print()
    
    # 测试 5: 获取高分资讯
    print("🌟 测试 5: 获取高分资讯")
    result = skill.get_highlights(days=7)
    print(f"  高分资讯数: {result.total}")
    print()
    
    # 测试 6: 获取统计
    print("📊 测试 6: 获取统计信息")
    stats = skill.get_stats(days=7)
    print(f"  总资讯数: {stats.get('total_items')}")
    print(f"  平均分: {stats.get('avg_score')}")
    print(f"  分类分布: {stats.get('category_distribution')}")
    print()
    
    # 测试 7: 便捷函数
    print("⚡ 测试 7: 便捷函数")
    result = get_daily("2026-05-11")
    print(f"  get_daily: {result.total} 条")
    
    result = search("保险", days=7)
    print(f"  search: {result.total} 条")
    
    result = get_by_category("product", days=7)
    print(f"  get_by_category: {result.total} 条")
    print()
    
    print("="*60)
    print("✅ Skill 模式测试完成!")
    print("="*60 + "\n")

if __name__ == "__main__":
    test_skill()
