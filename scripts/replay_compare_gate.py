#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1-A Replay 发布门（Event OS 第四阶段「生产验证」）。

把 ``replay_framework`` 的「重放 + 比对」接入 DAG 流水线，作为一道发布门：
在**观察期（trial）内**发现回归或重放失败只写报告、打印 warning、exit 0（不阻断流水线）；
观察期结束后「回归」与「重放失败（代码/回归错误）」都直接 fail-closed（exit 1），成为真正的
发布硬门——落实「不能证明没回归 ≠ 可发布」。唯一豁免：数据不可达（data.json 缺失等基础
设施抖动）时重放失败始终 warn-only，避免数据临时不可用误伤发布。

观察期截止由 ``REPLAY_GATE_ENFORCE_FROM`` 控制：当前日期 < 该日期 → trial（warn-only）；
否则 → enforced（fail-closed）。落地默认值 2026-10-14（相对实施日 2026-10-07 约一周），
上线后若需延长观察期，直接调大该日期即可。

编排（全部复用 replay_framework，不重复实现重放逻辑）：
  1. 若缺少 replay_baseline.json，先以当前结果播种基线（首次运行自我校准，避免误报）；
  2. 跑一次重放 → 写 replay_result.json；
  3. 与基线比对 → 写 replay_compare_report.json；
  4. 按观察期判定 gate 模式与退出码。

用法（由 dag.py 节点调用）::

    python3 scripts/replay_compare_gate.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

REPLAY_FRAMEWORK = os.path.join(ROOT, "replay_framework.py")
BASELINE_PATH = os.path.join(ROOT, "replay_baseline.json")
RESULT_PATH = os.path.join(ROOT, "replay_result.json")
REPORT_PATH = os.path.join(ROOT, "replay_compare_report.json")

# 观察期截止：在此之前 replay 回归只告警不阻断；之后成为发布硬门。
REPLAY_GATE_ENFORCE_FROM = "2026-10-14"


def _in_trial() -> bool:
    try:
        cutoff = datetime.fromisoformat(REPLAY_GATE_ENFORCE_FROM).date()
        return datetime.now(timezone.utc).date() < cutoff
    except Exception:
        # 日期解析失败保守按观察期处理（不误杀发布）
        return True


def _load_rf():
    spec = importlib.util.spec_from_file_location("replay_framework", REPLAY_FRAMEWORK)
    rf = importlib.util.module_from_spec(spec)
    sys.path.insert(0, ROOT)
    spec.loader.exec_module(rf)
    return rf


def decide(trial: bool, regression: bool, replay_ok: bool,
           data_unavailable: bool = False) -> tuple[int, str]:
    """纯判定函数（便于单测）：返回 (exit_code, gating_label)。

    P1-1 fail-closed 修正（第五阶段）：落实「不能证明没回归 ≠ 可发布」。

    - replay 失败 + 数据不可达（data.json 缺失等基础设施抖动）：始终 warn-only，
      不因数据临时不可用误伤发布；
    - replay 失败（代码/回归错误）：观察期内 warn-only；观察期后 fail-closed（exit 1）；
    - 观察期内检测到回归：warn-only（exit 0）；
    - 观察期后检测到回归：fail-closed（exit 1）；
    - 无回归：exit 0。
    """
    if not replay_ok:
        if data_unavailable:
            return 0, "warn"
        return (0, "warn") if trial else (1, "enforce")
    if regression:
        return (0, "warn") if trial else (1, "enforce")
    return 0, "ok"


def main(argv: list[str]) -> int:
    trial = _in_trial()
    mode = "trial" if trial else "enforced"
    rf = _load_rf()

    # 1) 首次运行播种基线（自校准，防误报）
    if not os.path.exists(BASELINE_PATH):
        print("[replay_gate] 无基线，先播种 replay_baseline.json", file=sys.stderr)
        try:
            rf.save_baseline(rf.build_document(rf.execute_replay()))
        except Exception as e:  # noqa: BLE001
            print(f"[replay_gate] 基线播种失败：{e}", file=sys.stderr)

    # 2) 跑重放（P1-1：区分「数据不可达」与「代码/回归错误」）
    data_unavailable = not os.path.exists(os.path.join(ROOT, "data.json"))
    replay_ok = True
    try:
        rf.save_result(rf.build_document(rf.execute_replay()))
    except Exception as e:  # noqa: BLE001
        replay_ok = False
        print(f"[replay_gate] 重放执行失败：{e}", file=sys.stderr)

    # 3) 比对
    current = rf.load_document(RESULT_PATH) if os.path.exists(RESULT_PATH) else None
    baseline = rf.load_baseline() if os.path.exists(BASELINE_PATH) else None
    cmp = rf.compare(current, baseline) if (current and baseline) else {
        "regression": None, "error": "missing_document",
    }
    regression = bool(cmp.get("regression"))

    # 4) 判定
    exit_code, gating = decide(trial, regression, replay_ok, data_unavailable)
    report = {
        "version": "1.1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "gating": gating,
        "replay_ok": replay_ok,
        "data_unavailable": data_unavailable,
        "regression": regression,
        "enforce_from": REPLAY_GATE_ENFORCE_FROM,
        "compare": cmp,
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    if not replay_ok:
        if data_unavailable:
            print("[replay_gate][WARN] 重放失败（数据不可达 data.json 缺失），豁免不阻断发布",
                  file=sys.stderr)
        elif trial:
            print("[replay_gate][WARN] 重放执行失败（观察期内不阻断，需人工排查重放管线）",
                  file=sys.stderr)
        else:
            print("[replay_gate][FAIL] 重放执行失败（观察期后 fail-closed：无法证明无回归）",
                  file=sys.stderr)
    elif regression:
        if trial:
            print(f"[replay_gate][WARN] 检测到 replay 回归（观察期内，不阻断发布）；"
                  f"enforce_from={REPLAY_GATE_ENFORCE_FROM}", file=sys.stderr)
        else:
            print("[replay_gate][FAIL] 检测到 replay 回归，发布门已生效（fail-closed）",
                  file=sys.stderr)
    else:
        print("[replay_gate] 无 replay 回归", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
