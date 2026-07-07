#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分类均衡评估脚本 — ce-optimize category-balance

度量 InsureAI 资讯采集结果的「分类均衡度」。

用法：
    python3 scripts/evaluate_balance.py            # 仅评测当前 data.json
    python3 scripts/evaluate_balance.py --run      # 受控重置基线 → 跑 collect.py → 评测

设计：
    --run 模式会先把 data.json 受控重置为固定基线快照 data.baseline.json（确保各实验
    从同一基准出发、可比），再运行 collect.py 重新采集并合并，最后评测合并后的 data.json。
    这样分类逻辑改进（确定性）与关键词扩展（采集新内容）的效果都能被度量。

输出 JSON 指标（含 ce-optimize 门禁所需键）：
    total_items, category_diversity, min_category_count, max_category_pct,
    category_distribution, max_single_source_pct, source_diversity,
    avg_score, stock_noise_count
"""
import json
import subprocess
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data.json"
BASELINE_FILE = ROOT / "data.baseline.json"
COLLECT = ROOT / "collect.py"

# 与 source-diversification/evaluate_sources.py 保持一致的股市噪声词表
STOCK_NOISE_KEYWORDS = [
    "板块拉升", "板块走强", "板块反弹", "板块震荡", "板块大涨", "板块下跌",
    "涨停", "跌停", "涨幅", "跌幅", "融资客", "净买入", "净卖出",
]

# 现有 5 类分类体系（与 collect.py _category 一致）
CATEGORIES = ["regulation", "product", "industry", "research", "claims"]


def restore_baseline():
    """受控重置：基线快照不存在则从当前 data.json 创建；否则用快照覆盖 data.json。"""
    if not BASELINE_FILE.exists():
        if DATA_FILE.exists():
            BASELINE_FILE.write_text(DATA_FILE.read_text("utf-8"), encoding="utf-8")
            print(f"[baseline] 创建基线快照 {BASELINE_FILE.name}", file=sys.stderr)
        else:
            print("[baseline] 无 data.json 也无基线，无法重置", file=sys.stderr)
            return
    else:
        DATA_FILE.write_text(BASELINE_FILE.read_text("utf-8"), encoding="utf-8")
        print(f"[baseline] 已重置 data.json <- {BASELINE_FILE.name}", file=sys.stderr)


def run_collection():
    print("运行采集脚本...", file=sys.stderr)
    try:
        r = subprocess.run([sys.executable, str(COLLECT)], capture_output=True,
                           text=True, timeout=240, cwd=str(ROOT))
        if r.returncode != 0:
            print(f"采集失败(returncode={r.returncode}): {r.stderr[-500:]}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("采集超时(>240s)", file=sys.stderr)


def evaluate():
    if not DATA_FILE.exists():
        print(json.dumps({"error": "no_data_file"}))
        return
    data = json.loads(DATA_FILE.read_text("utf-8"))
    news = data.get("news", [])
    if not news:
        out = {"total_items": 0, "category_diversity": 0, "min_category_count": 0,
               "max_category_pct": 0.0, "category_distribution": {},
               "max_single_source_pct": 0.0, "source_diversity": 0,
               "avg_score": 0.0, "stock_noise_count": 0}
        print(json.dumps(out, ensure_ascii=False))
        return

    cat_counts = Counter(n.get("category", "unknown") for n in news)
    src_counts = Counter(n.get("source_name", "unknown") for n in news)
    scores = [n.get("ai_score", 0) for n in news]
    stock_noise = sum(1 for n in news
                      if any(k in n.get("title", "") for k in STOCK_NOISE_KEYWORDS))

    # 分类均衡核心指标：5 类中数量最少的那一类（缺失计 0）
    min_count = min(cat_counts.get(c, 0) for c in CATEGORIES)
    max_cat = max(cat_counts.values())
    present = sum(1 for c in CATEGORIES if cat_counts.get(c, 0) > 0)

    out = {
        "total_items": len(news),
        "category_diversity": len(cat_counts),
        "min_category_count": min_count,
        "max_category_pct": round(max_cat / len(news) * 100, 1),
        "category_distribution": dict(cat_counts.most_common()),
        "max_single_source_pct": round(max(src_counts.values()) / len(news) * 100, 1),
        "source_diversity": len(src_counts),
        "avg_score": round(sum(scores) / len(scores), 1),
        "stock_noise_count": stock_noise,
        # 诊断：5 类的实际覆盖数（用于人工核对均衡目标）
        "category_coverage": {c: cat_counts.get(c, 0) for c in CATEGORIES},
        "present_expected_categories": present,
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    if "--run" in sys.argv:
        restore_baseline()
        run_collection()
    evaluate()
