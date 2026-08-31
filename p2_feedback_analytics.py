#!/usr/bin/env python3
"""P2.2 Decision Feedback Analytics — 把累积反馈变成可解释的产品指标。

按 Vikings 评估的边界：**先积累数据，不要训练模型**。本模块只做描述性分析，
回答一个核心问题——「InsureAI 到底有没有帮助用户更快、更好地做决定？」

指标定义（来自评估报告的 Feedback Analytics 表）：
  Hit Rate         推荐是否被采纳  = (acted_on + important + useful) / total
  Dismiss Rate     噪声比例        = (noise + irrelevant) / total
  Action Rate      是否真正推动行动 = acted_on / total
  Repeat Exposure  是否反复被推荐    = 被反馈 >1 次的事件数 / 去重事件数
  False Positive   错误关注        = incorrect / total
  Time to Decision 从事件到决策的时延（需事件时间线，v1 暂未接入，见下）

Time to Decision 需要「事件首见时间」与「用户反馈时间」的对齐，依赖 P2.1 的
canonical 事件时间线，v1 先不实现，避免在没有事件时间线时编造时延。
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from p2_intelligence import load_state

ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = ROOT / "p2_feedback_analytics.json"

POSITIVE = {"acted_on", "important", "useful"}
DISMISS = {"noise", "irrelevant"}


def feedback_analytics(feedback: list[dict]) -> dict[str, Any]:
    n = len(feedback)
    if n == 0:
        return {
            "total": 0,
            "distinct_events": 0,
            "by_label": {},
            "hit_rate": 0.0,
            "dismiss_rate": 0.0,
            "action_rate": 0.0,
            "repeat_exposure_rate": 0.0,
            "false_positive_rate": 0.0,
            "scored_coverage": 0.0,
        }
    labels = [f.get("label") for f in feedback]
    by_label = dict(Counter(labels))
    positive = sum(1 for l in labels if l in POSITIVE)
    dismiss = sum(1 for l in labels if l in DISMISS)
    action = sum(1 for l in labels if l == "acted_on")
    false_pos = sum(1 for l in labels if l == "incorrect")
    events = [f.get("event_id") for f in feedback if f.get("event_id")]
    per_event = Counter(events)
    repeat = sum(1 for c in per_event.values() if c > 1)
    distinct = len(per_event)
    # 评分覆盖：有多少条带了 importance/confidence（衡量数据集是否可用于后续分析）
    with_score = sum(1 for f in feedback if f.get("importance") is not None or f.get("confidence") is not None)
    return {
        "total": n,
        "distinct_events": distinct,
        "by_label": by_label,
        "hit_rate": round(positive / n, 3),
        "dismiss_rate": round(dismiss / n, 3),
        "action_rate": round(action / n, 3),
        "repeat_exposure_rate": round(repeat / max(distinct, 1), 3),
        "false_positive_rate": round(false_pos / n, 3),
        "scored_coverage": round(with_score / n, 3),
    }


def run(state: dict | None = None, persist: bool = True) -> dict[str, Any]:
    state = state or load_state()
    result = {
        "version": "p2.2-v1.0",
        "analytics": feedback_analytics(state.get("feedback", [])),
    }
    if persist:
        OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default=None, help="可选 p2_state.json 路径")
    args = parser.parse_args()
    state = load_state() if not args.state else json.loads(Path(args.state).read_text(encoding="utf-8"))
    result = run(state)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
