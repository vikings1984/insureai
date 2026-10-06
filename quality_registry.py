#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-6 Quality Registry：把 benchmark 输出固化为每次 commit 的质量档案，并支持版本比较。

零依赖（仅标准库），可在 CI（python 3.11）与本地（managed 3.13）一致运行。

职责：
  - record(results, commit, when)：把一次 benchmark 结果写入 quality/<commit>.json，
    并在 quality/index.json 中追加一条轻量索引（commit / when / 关键指标），
    同时刷新 quality/latest.json。幂等：同 commit 重复 record 覆盖。
  - compare(commit_a, commit_b)：加载两条档案，逐指标比较，返回 delta 与 regression 标记。
  - latest() / load(commit) / list_records()：查询。

质量档案存放在仓库内 quality/ 目录（由手动 Git Data API 推送提交，与本项目其它产物一致；
benchmark.yml 当前为 contents: read，不在 CI 内自动提交，故档案随代码改动一并推送）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
QUALITY_DIR = os.path.join(HERE, "quality")
INDEX_PATH = os.path.join(QUALITY_DIR, "index.json")
LATEST_PATH = os.path.join(QUALITY_DIR, "latest.json")

# 参与版本比较、且「越低越好」的指标（其余越高越好）
_LOWER_IS_BETTER = {
    "event.false_merge_rate": True,
    "split.false_merge_rate": True,
    "split.false_split_rate": True,
    "claim_evidence.single_source_false_cross_check_rate": True,
    "decision.unsafe_now_rate": True,
}


def _metric(results: dict, dotted: str):
    """从 benchmark_results 取嵌套指标，缺失返回 None。"""
    cur = results
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _key_metrics(results: dict) -> dict:
    """抽取参与索引/比较的关键指标（扁平 dotted 键）。"""
    keys = [
        "macro_quality",
        "safety_pass",
        "event.precision",
        "event.recall",
        "event.false_merge_rate",
        "split.false_split_rate",
        "split.false_merge_rate",
        "claim_evidence.cross_check_accuracy",
        "claim_evidence.single_source_state_accuracy",
        "claim_evidence.single_source_false_cross_check_rate",
        "decision.unsafe_now_rate",
        "decision.human_review_recall",
    ]
    return {k: _metric(results, k) for k in keys}


def _commit_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True
        )
        if out.returncode == 0:
            return out.stdout.strip()[:12]
    except Exception:
        pass
    return "unknown"


def _ensure_dir() -> None:
    os.makedirs(QUALITY_DIR, exist_ok=True)


def record(results: dict, commit: str | None = None, when: str | None = None) -> str:
    """写入一次质量档案，返回 commit 标识。

    results：benchmark.py 输出的 dict（含 macro_quality / safety_pass / event / split / ...）。
    commit：默认取 git HEAD 前 12 位；when：默认取当前 ISO 时间。
    """
    commit = (commit or _commit_sha() or "unknown")[:12]
    if when is None:
        from datetime import datetime, timezone
        when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _ensure_dir()

    metrics = _key_metrics(results)
    record_doc = {
        "commit": commit,
        "when": when,
        "metrics": metrics,
        "results": results,
    }
    rec_path = os.path.join(QUALITY_DIR, f"{commit}.json")
    with open(rec_path, "w", encoding="utf-8") as f:
        json.dump(record_doc, f, ensure_ascii=False, indent=2)

    # 刷新 latest
    with open(LATEST_PATH, "w", encoding="utf-8") as f:
        json.dump(record_doc, f, ensure_ascii=False, indent=2)

    # 更新索引
    index = []
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                index = json.load(f)
        except Exception:
            index = []
    index = [r for r in index if r.get("commit") != commit]
    index.append({
        "commit": commit,
        "when": when,
        "macro_quality": metrics.get("macro_quality"),
        "safety_pass": metrics.get("safety_pass"),
        "event_false_merge_rate": metrics.get("event.false_merge_rate"),
        "split_false_split_rate": metrics.get("split.false_split_rate"),
        "single_source_false_cross_check_rate": metrics.get("claim_evidence.single_source_false_cross_check_rate"),
    })
    index.sort(key=lambda r: r.get("when", ""))
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    return commit


def load(commit: str) -> dict | None:
    path = os.path.join(QUALITY_DIR, f"{commit[:12]}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def latest() -> dict | None:
    if not os.path.exists(LATEST_PATH):
        return None
    with open(LATEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def list_records() -> list[dict]:
    if not os.path.exists(INDEX_PATH):
        return []
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def compare(commit_a: str, commit_b: str) -> dict:
    """比较两条质量档案，返回逐指标 delta 与 regression 标记。

    a 视为「旧基线」、b 视为「新提交」；regression=True 表示新提交在任一跟踪指标上劣化。
    """
    ra, rb = load(commit_a), load(commit_b)
    if ra is None or rb is None:
        return {"error": "missing_record", "a": commit_a, "b": commit_b}
    ma, mb = ra.get("metrics", {}), rb.get("metrics", {})
    deltas = {}
    regression = False
    for key in sorted(set(ma) | set(mb)):
        va, vb = ma.get(key), mb.get(key)
        if va is None or vb is None:
            continue
        delta = round((vb - va), 6) if isinstance(vb, (int, float)) and isinstance(va, (int, float)) else None
        worse = False
        if delta is not None and key in _LOWER_IS_BETTER:
            worse = delta > 0  # 越高越差
        elif delta is not None and key == "safety_pass":
            worse = (va is True and vb is False)
        elif delta is not None and key == "macro_quality":
            worse = delta < 0  # 越低越差
        # 布尔类（safety_pass 已处理）；precision/recall/accuracy 越高越好
        elif delta is not None and isinstance(vb, (int, float)):
            worse = delta < 0
        if worse:
            regression = True
        deltas[key] = {"old": va, "new": vb, "delta": delta, "worse": worse}
    return {
        "a": commit_a, "b": commit_b,
        "a_when": ra.get("when"), "b_when": rb.get("when"),
        "deltas": deltas, "regression": regression,
    }


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "record":
        # 读取 benchmark_results.json（若存在），否则从参数指定的文件
        src = "benchmark_results.json"
        if len(argv) > 1 and os.path.exists(argv[1]):
            src = argv[1]
        if not os.path.exists(src):
            print(f"[warn] 未找到 {src}，跳过记录", file=sys.stderr)
            return 0
        with open(src, "r", encoding="utf-8") as f:
            results = json.load(f)
        commit = argv[2] if len(argv) > 2 else None
        when = argv[3] if len(argv) > 3 else None
        recorded = record(results, commit, when)
        print(f"recorded quality for commit {recorded}")
        return 0
    if argv[0] == "compare":
        if len(argv) < 3:
            print("usage: quality_registry.py compare <commit_a> <commit_b>", file=sys.stderr)
            return 2
        out = compare(argv[1], argv[2])
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 1 if out.get("regression") else 0
    if argv[0] == "list":
        print(json.dumps(list_records(), ensure_ascii=False, indent=2))
        return 0
    if argv[0] == "latest":
        print(json.dumps(latest() or {}, ensure_ascii=False, indent=2, default=str))
        return 0
    print("usage: quality_registry.py [record|compare|list|latest] ...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
