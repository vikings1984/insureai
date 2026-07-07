#!/usr/bin/env python3
"""每日采集质量自动评分（ce-optimize 框架）。

运行两套只读评测（采集全面性 / 渠道多样化），归档：
  - data/quality/<YYYY-MM-DD>.json  当日摘要（用于历史趋势）
  - data/quality/latest.json        最新全量（覆盖写，体积有界）
并输出是否通过 ce-optimize 门禁（分类覆盖≥4 / 信源多样≥8 / 最大单源≤40% / 股市噪声=0）。
"""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL_COLLECT = ROOT / ".context/compound-engineering/ce-optimize/collection-comprehensiveness/evaluate_collection.py"
EVAL_SOURCES = ROOT / ".context/compound-engineering/ce-optimize/source-diversification/evaluate_sources.py"
OUT_DIR = ROOT / "data" / "quality"


def run_eval(script: Path):
    r = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, cwd=str(ROOT), timeout=120)
    if r.returncode != 0:
        return {"error": r.stderr[-300:]}
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"error": "bad_json", "stdout": r.stdout[:300]}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    d = date.today().isoformat()
    col = run_eval(EVAL_COLLECT)
    src = run_eval(EVAL_SOURCES)

    summary = {
        "date": d,
        "total_items": col.get("total_items"),
        "category_diversity": col.get("category_diversity"),
        "source_diversity": col.get("source_diversity"),
        "max_single_source_pct": col.get("max_single_source_pct"),
        "avg_score": col.get("avg_score"),
        "distinct_channels": src.get("distinct_channels"),
        "new_channel_items": src.get("new_channel_items"),
        "stock_noise_count": src.get("stock_noise_count"),
        "source_distribution": src.get("source_distribution"),
        "category_distribution": col.get("category_distribution"),
    }

    # ce-optimize 门禁（来自 spec.yaml）
    summary["pass"] = bool(
        summary["category_diversity"] and summary["category_diversity"] >= 4
        and summary["source_diversity"] and summary["source_diversity"] >= 8
        and summary["max_single_source_pct"] is not None and summary["max_single_source_pct"] <= 40
        and summary["stock_noise_count"] == 0
    )

    (OUT_DIR / f"{d}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    full = {"date": d, "collection": col, "sources": src, "summary": summary}
    (OUT_DIR / "latest.json").write_text(
        json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    main()
