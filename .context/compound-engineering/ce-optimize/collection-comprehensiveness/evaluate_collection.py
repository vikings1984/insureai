#!/usr/bin/env python3
"""采集全面性评估脚本 — 输出 JSON 指标供 ce-optimize 使用"""
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
DATA_FILE = PROJECT_ROOT / "docs" / "data.json"

def run_collection():
    """运行采集脚本"""
    result = subprocess.run(
        [sys.executable, "run_collect.py"],
        capture_output=True, text=True, timeout=120,
        cwd=str(PROJECT_ROOT)
    )
    if result.returncode != 0:
        print(json.dumps({"error": "collection_failed", "stderr": result.stderr[-500:]}))
        sys.exit(1)

def evaluate():
    run_collection()
    
    if not DATA_FILE.exists():
        print(json.dumps({"error": "no_data_file"}))
        sys.exit(1)
    
    data = json.loads(DATA_FILE.read_text("utf-8"))
    news = data.get("news", [])
    
    if not news:
        print(json.dumps({
            "total_items": 0, "category_diversity": 0,
            "source_diversity": 0, "max_single_source_pct": 0,
            "date_coverage": 0, "avg_score": 0,
            "items": []
        }))
        return
    
    cats = {}
    srcs = {}
    dates = {}
    for n in news:
        c = n.get("category", "unknown")
        cats[c] = cats.get(c, 0) + 1
        s = n.get("source_name", "unknown")
        srcs[s] = srcs.get(s, 0) + 1
        dt = n.get("published_at", "")[:10]
        if dt:
            dates[dt] = dates.get(dt, 0) + 1
    
    scores = [n.get("ai_score", 0) for n in news]
    
    # 输出指标 + 条目摘要供 judge 评估
    output = {
        "total_items": len(news),
        "category_diversity": len(cats),
        "source_diversity": len(srcs),
        "max_single_source_pct": round(max(srcs.values()) / len(news) * 100, 1),
        "date_coverage": len(dates),
        "avg_score": round(sum(scores) / len(scores), 1),
        "category_distribution": cats,
        "source_distribution": srcs,
        "date_distribution": dates,
        "score_range": [min(scores), max(scores)],
        # 供 judge 评估的条目摘要
        "items": [
            {
                "title": n.get("title", ""),
                "category": n.get("category", ""),
                "source_name": n.get("source_name", ""),
                "source_type": n.get("source_type", ""),
                "published_at": n.get("published_at", ""),
                "ai_score": n.get("ai_score", 0),
                "summary": n.get("summary", "")[:150],
                "tags": n.get("tags", ""),
            }
            for n in news
        ]
    }
    print(json.dumps(output, ensure_ascii=False))

if __name__ == "__main__":
    evaluate()
