#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 Source Health 人工确认台账（Event OS 第五阶段；只记录，不执行）。

为 `observability.section_source_degrade` 的降权**建议**补一个可审计的人工确认环节，
把「建议」流转为可追踪的状态：suggested → confirm/downweight/suspend → recover（或 reject）。

严格边界（本阶段只补确认接口，**不自动执行**）：
- 本脚本**只写台账** ``source_degrade_ledger.json``，**绝不**修改 data.json 的信源权重、
  **绝不**自动 suspend/降权任何信源；真正的权重/停源动作需另行人工在采集侧执行。
- 台账仅供审计与呈现（observability 读取后标注每条建议的 status）。

用法::

    python3 scripts/source_degrade_confirm.py list
    python3 scripts/source_degrade_confirm.py confirm 众安保险 --note "人工确认长期不可用"
    python3 scripts/source_degrade_confirm.py downweight 众安保险
    python3 scripts/source_degrade_confirm.py recover 众安保险
    python3 scripts/source_degrade_confirm.py reject 众安保险 --note "复核后恢复健康"
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER_PATH = os.path.join(ROOT, "source_degrade_ledger.json")

ACTIONS = {"confirm", "downweight", "suspend", "recover", "reject"}


def _load() -> dict:
    if not os.path.exists(LEDGER_PATH):
        return {"version": "1.0", "actions": []}
    try:
        with open(LEDGER_PATH, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"version": "1.0", "actions": []}
    doc.setdefault("actions", [])
    return doc


def _save(doc: dict) -> None:
    with open(LEDGER_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _note(argv: list[str]) -> str:
    return argv[argv.index("--note") + 1] if "--note" in argv else ""


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "list":
        doc = _load()
        latest: dict[str, dict] = {}
        for a in doc["actions"]:
            if a.get("source"):
                latest[a["source"]] = a
        if not latest:
            print("[source_degrade_confirm] 台账为空（尚无人工确认记录）")
            return 0
        for src, a in sorted(latest.items()):
            print(f"  {src}: {a.get('action')} @ {a.get('at')}"
                  f"{'  note=' + a['note'] if a.get('note') else ''}")
        return 0

    action, source = argv[0], argv[1]
    if action not in ACTIONS:
        print(f"用法：source_degrade_confirm.py <{'|'.join(sorted(ACTIONS))}> <source> [--note ...] | list",
              file=sys.stderr)
        return 2
    if not source:
        print("缺少 source 参数", file=sys.stderr)
        return 2

    doc = _load()
    doc["actions"].append({
        "source": source,
        "action": action,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": _note(argv),
    })
    _save(doc)
    print(f"[source_degrade_confirm] 已记录：{source} -> {action}（仅台账，未改权重/未停源）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
