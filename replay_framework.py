#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1-5 Replay Framework：把「生产数据重放」升级为可存档、可对比、可判定回归的框架（零依赖）。

``production_replay.py`` 已经能做一件事：用真实生产数据跑一遍确定性情报管线，
并通过「打乱输入顺序后事件分区是否一致」来检验稳定性。但它只能**当场看一眼**——
没有基线、无法回答「这次改动相比上次是变好还是变坏」。

本模块补上框架层（不重复实现重放逻辑，直接复用 production_replay.run_replay）：

    run        执行重放 → 写 replay_result.json（含 commit / 时间 / 扁平指标）
    baseline   把当前结果存档为 replay_baseline.json（回归比对的锚点）
    compare    当前结果 vs 基线 → 逐指标 delta + worse + regression

回归判定口径（与 P0-6 quality_registry 保持一致的心智模型）：

    replay_stability 下降            → 劣化（确定性变差）
    article_coverage 下降            → 劣化（有文章没被任何事件覆盖）
    duplicate_event_ids 上升          → 劣化
    duplicate_article_assignments 上升 → 劣化
    status 由 ok 退化为 unavailable   → 劣化（且属 critical：说明生产数据或管线出了问题）

``event_count`` / ``sample_count`` / ``source_diversity`` 只记录 delta，**不参与回归判定**：
它们随数据量自然波动，拿来判回归会产生大量假告警。

用法::

    python3 replay_framework.py run                 # 执行重放并写 replay_result.json
    python3 replay_framework.py baseline            # 重放并存档为基线
    python3 replay_framework.py compare             # 当前结果 vs 基线（劣化则 exit 1）
    python3 replay_framework.py compare --json      # 输出 JSON
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE_PATH = os.path.join(HERE, "replay_baseline.json")
RESULT_PATH = os.path.join(HERE, "replay_result.json")

VERSION = "1.0"

# 参与回归判定的指标：True = 越低越好，False = 越高越好
REGRESSION_METRICS = {
    "replay_stability": False,
    "article_coverage": False,
    "duplicate_event_ids": True,
    "duplicate_article_assignments": True,
}

# 只记录 delta、不参与判定的指标
INFORMATIONAL_METRICS = ("event_count", "sample_count", "source_diversity", "top_source_share")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _commit_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                             capture_output=True, text=True)
        if out.returncode == 0:
            return out.stdout.strip()[:12]
    except Exception:
        pass
    return "unknown"


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def flatten(result: dict) -> dict:
    """把 production_replay 的嵌套结果压平为可比对的标量指标。"""
    quality = (result or {}).get("quality") or {}
    integrity = quality.get("event_integrity") or {}
    return {
        "status": (result or {}).get("status", "unknown"),
        "replay_stability": _f(quality.get("replay_stability")),
        "article_coverage": _f(integrity.get("article_coverage")),
        "duplicate_event_ids": _f(integrity.get("duplicate_event_ids")),
        "duplicate_article_assignments": _f(integrity.get("duplicate_article_assignments")),
        "event_count": _f((result or {}).get("event_count")),
        "sample_count": _f((result or {}).get("sample_count")),
        "source_diversity": _f(quality.get("source_diversity")),
        "top_source_share": _f(quality.get("top_source_share")),
    }


def execute_replay() -> dict:
    """执行一次真实重放（复用 production_replay，不重复实现）。"""
    import production_replay
    return production_replay.run_replay()


def build_document(result: dict) -> dict:
    return {
        "version": VERSION,
        "generated_at": _now(),
        "commit": _commit_sha(),
        "metrics": flatten(result),
        "result": result,
    }


def save_result(doc: dict, path: str | None = None) -> None:
    with open(path or RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")


def save_baseline(doc: dict, path: str | None = None) -> None:
    save_result(doc, path or BASELINE_PATH)


def load_document(path: str | None = None):
    p = path or RESULT_PATH
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_baseline(path: str | None = None):
    return load_document(path or BASELINE_PATH)


def compare(current: dict, baseline: dict) -> dict:
    """对比当前结果与基线，返回逐指标 delta 与 regression 标记。"""
    if not current or not baseline:
        return {"error": "missing_document",
                "has_current": bool(current), "has_baseline": bool(baseline)}
    cur, base = current.get("metrics", {}), baseline.get("metrics", {})
    deltas: dict[str, dict] = {}
    regression = False

    for key, lower_is_better in REGRESSION_METRICS.items():
        a, b = _f(base.get(key)), _f(cur.get(key))
        delta = round(b - a, 6)
        worse = (delta > 0) if lower_is_better else (delta < 0)
        if worse:
            regression = True
        deltas[key] = {"baseline": a, "current": b, "delta": delta, "worse": worse}

    for key in INFORMATIONAL_METRICS:
        a, b = _f(base.get(key)), _f(cur.get(key))
        deltas[key] = {"baseline": a, "current": b, "delta": round(b - a, 6),
                       "worse": False, "informational": True}

    # 状态退化（ok → unavailable）单独判定，属最严重的一档
    status_regressed = (base.get("status") == "ok" and cur.get("status") != "ok")
    if status_regressed:
        regression = True

    return {
        "version": VERSION,
        "baseline": {"commit": baseline.get("commit"), "generated_at": baseline.get("generated_at")},
        "current": {"commit": current.get("commit"), "generated_at": current.get("generated_at")},
        "deltas": deltas,
        "status_regressed": status_regressed,
        "regression": regression,
    }


def main(argv: list[str]) -> int:
    if not argv:
        argv = ["run"]
    cmd = argv[0]
    to_stdout = "--json" in argv

    if cmd == "run":
        doc = build_document(execute_replay())
        if "--baseline" in argv or "--save-baseline" in argv:
            save_baseline(doc)
            print(f"[replay] baseline saved -> replay_baseline.json", file=sys.stderr)
        save_result(doc)
        if to_stdout:
            print(json.dumps(doc, ensure_ascii=False, indent=2))
        else:
            m = doc["metrics"]
            print(f"[replay] status={m['status']} stability={m['replay_stability']} "
                  f"events={m['event_count']} coverage={m['article_coverage']}")
        return 0

    if cmd == "baseline":
        doc = build_document(execute_replay())
        save_baseline(doc)
        save_result(doc)
        print(f"[replay] baseline saved (commit={doc['commit']}, "
              f"stability={doc['metrics']['replay_stability']})")
        return 0

    if cmd == "compare":
        current = load_document()
        baseline = load_baseline()
        if current is None or baseline is None:
            print("[replay] 缺少 replay_result.json 或 replay_baseline.json；"
                  "先执行 `python3 replay_framework.py baseline`", file=sys.stderr)
            return 2
        out = compare(current, baseline)
        if to_stdout:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(f"[replay] baseline={out['baseline']['commit']} "
                  f"current={out['current']['commit']} regression={out['regression']}")
            for k, v in out["deltas"].items():
                flag = "WORSE" if v.get("worse") else ("info" if v.get("informational") else "ok")
                print(f"  - {k}: {v['baseline']} -> {v['current']} (delta={v['delta']}) [{flag}]")
        return 1 if out.get("regression") else 0

    print("usage: replay_framework.py [run|baseline|compare] [--baseline] [--json]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
