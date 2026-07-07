#!/usr/bin/env python3
"""渠道多样化评估脚本 — ce-optimize source-diversification"""
import json
import subprocess
import sys
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
DATA_FILE = PROJECT_ROOT / "data.json"

# 已知渠道类型映射
CHANNEL_MAP = {
    "东方财富": "财经API",
    "中国保险行业协会": "行业协会",
    "中国平安": "个股新闻",
    "中国人寿": "个股新闻",
    "中国太保": "个股新闻",
    "新华保险": "个股新闻",
    "中国人保": "个股新闻",
    "CCTV": "央视新闻",
}

# 新渠道关键词识别
NEW_CHANNEL_MARKERS = {
    "百度": "搜索引擎",
    "Baidu": "搜索引擎",
    "Bing": "搜索引擎",
    "Google": "搜索引擎",
    "搜狗": "微信公众号",
    "微信": "微信公众号",
    "公众号": "微信公众号",
    "头条": "头条",
    "今日头条": "头条",
    "Brave": "搜索引擎",
}

# source_type 字段到渠道的映射（data.json 中的 source_type 已被映射为中文标签）
SOURCE_TYPE_CHANNEL_MAP = {
    "搜索引擎": "搜索引擎",
    "微信公众号": "微信公众号",
    "头条资讯": "头条",
    "财经媒体": "财经API",
    "行业协会": "行业协会",
    "监管机构": "监管机构",
    "保险公司": "保险公司",
    "兜底数据": "兜底数据",
}

STOCK_NOISE_KEYWORDS = [
    "板块拉升", "板块走强", "板块反弹", "板块震荡", "板块大涨", "板块下跌",
    "涨停", "跌停", "涨幅", "跌幅", "融资客", "净买入", "净卖出",
]


def run_collection():
    """运行采集脚本（可选；默认只读评估现有 data.json；collect.py 为增量合并，不清空）"""
    print("运行采集脚本...", file=sys.stderr)
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "collect.py")],
        capture_output=True, text=True, timeout=180, cwd=str(PROJECT_ROOT)
    )
    if result.returncode != 0:
        print(f"采集脚本失败: {result.stderr[-500:]}", file=sys.stderr)
    return result.stdout + result.stderr


def identify_channel(source_name: str, source_type: str = "") -> str:
    """识别新闻来源对应的渠道类型，优先使用 source_type 字段"""
    # 优先使用 source_type 字段
    if source_type and source_type in SOURCE_TYPE_CHANNEL_MAP:
        return SOURCE_TYPE_CHANNEL_MAP[source_type]
    for marker, channel in NEW_CHANNEL_MARKERS.items():
        if marker in source_name:
            return channel
    for name, channel in CHANNEL_MAP.items():
        if name in source_name:
            return channel
    return "其他财经媒体"


def evaluate(run_first=False):
    """主评估函数"""
    if run_first:
        run_collection()

    if not DATA_FILE.exists():
        print(json.dumps({"error": "data.json not found"}))
        return

    data = json.loads(DATA_FILE.read_text("utf-8"))
    news = data.get("news", [])

    # 基本指标
    total_items = len(news)
    categories = set(n.get("category", "") for n in news)
    category_diversity = len(categories)

    source_names = [n.get("source_name", "未知") for n in news]
    unique_sources = set(source_names)
    source_diversity = len(unique_sources)

    # 股市噪声检测
    stock_noise_count = sum(1 for n in news if any(kw in n.get("title", "") for kw in STOCK_NOISE_KEYWORDS))

    # 渠道多样性
    channel_map = {}
    for n in news:
        src = n.get("source_name", "未知")
        stype = n.get("source_type", "")
        channel = identify_channel(src, stype)
        if channel not in channel_map:
            channel_map[channel] = 0
        channel_map[channel] += 1

    distinct_channels = len(channel_map)

    # 新渠道条目数
    existing_channels = {"财经API", "行业协会", "个股新闻", "央视新闻", "其他财经媒体"}
    new_channel_items = sum(count for ch, count in channel_map.items() if ch not in existing_channels)

    # 评分统计
    scores = [n.get("ai_score", 0) for n in news]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    # 分类分布
    cat_dist = dict(Counter(n.get("category", "?") for n in news))

    # 最大单一来源占比
    source_counter = Counter(source_names)
    max_single_source_pct = round(max(source_counter.values()) / total_items * 100, 1) if total_items else 0

    # 构建输出
    output = {
        "total_items": total_items,
        "category_diversity": category_diversity,
        "source_diversity": source_diversity,
        "stock_noise_count": stock_noise_count,
        "distinct_channels": distinct_channels,
        "new_channel_items": new_channel_items,
        "avg_score": avg_score,
        "max_single_source_pct": max_single_source_pct,
        "category_distribution": cat_dist,
        "channel_distribution": channel_map,
        "source_distribution": dict(source_counter.most_common(10)),
        "items": [
            {
                "title": n.get("title", "")[:50],
                "source_name": n.get("source_name", ""),
                "channel": identify_channel(n.get("source_name", ""), n.get("source_type", "")),
                "category": n.get("category", ""),
                "ai_score": n.get("ai_score", 0),
                "published_at": n.get("published_at", ""),
                "summary": n.get("summary", "")[:100],
            }
            for n in news[:20]
        ],
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    evaluate(run_first="--run" in sys.argv)
