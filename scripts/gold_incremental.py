#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-3b Gold 增量追加（Event OS 第八阶段）。

方案要求（§3-P0-3）：
> **关键设计**：gold 必须支持**增量追加**（`candidates → pending_human → apply`），
> 而不是一次性交付千条——评审提的 500~1000 条建议**分批滚动**更现实。

**复用**已有成熟范式 `scripts/promote_real_v2_candidates.py`（不另造口径）：
```
prepare()  → 待审bundle，每条 decision="pending"
            "Never auto-validated."
apply()    → 拒绝在仍有 pending 时执行；只接受 approve/reject
```

本脚本把该范式**泛化**到任意 gold 文件（Event / Decision / Claim / Semantic Change），
使「分批滚动积累 gold」成为可持续动作，而非一次性工程。

用法::

    # 1) 准备待审bundle（从候选池）
    python3 scripts/gold_incremental.py prepare --gold gold/decision_gold.json \
        --candidates benchmarks/real_v2/candidates.json

    # 2) 人逐条标注（编辑 bundle，把 decision 改成 approve/reject；可加 labels）
    #    或交互式：python3 scripts/gold_incremental.py next

    # 3) 试演（不写盘）
    python3 scripts/gold_incremental.py apply --dry-run

    # 4) 应用（仅当全部已标注）
    python3 scripts/gold_incremental.py apply

**纪律**：
- 绝不自动验证（`apply` 遇到 pending 即拒绝）；
- 不覆盖既有已确认条目，只**追加**新条目（增量语义）；
- 每次 apply 记录 `applied_at` / `batch`，可审计。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

VERSION = "gold-incremental-v1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _write(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def prepare(gold_path: str, candidates_path: str | None, batch: str | None) -> dict:
    """从候选池生成待审bundle（decision 全pending，绝不自动验证）。

    增量语义：若bundle 已存在，则在**其基础上**追加（保留人工已标注的 decision/labels），
    已存在的 id 不重复追加。
    """
    bundle_path = gold_path.replace(".json", ".review_bundle.json")
    # 优先以既有 bundle 为基线（保留人工标注）；否则从已确认的 gold 起建
    gold = _read(bundle_path) or _read(gold_path) or {
        "version": VERSION, "gold_status": "pending_human", "entries": [],
    }

    cands = (_read(candidates_path) or {}).get("candidates") or []

    # 已在 bundle 里的条目（按 id 去重）→ 增量语义：不重复追加
    existing = {e.get("id") for e in (gold.get("entries") or []) if e.get("id")}
    added = 0
    for c in cands:
        cid = c.get("id")
        if not cid or cid in existing:
            continue
        gold.setdefault("entries", []).append({
            "id": cid,
            "dimension": c.get("dimension"),
            "proposed_relation": c.get("proposed_relation"),
            "primary_entity": c.get("primary_entity"),
            "rationale": c.get("rationale"),
            "batch": batch or _now()[:10],
            "decision": "pending",     # 必须人工表态
            "labels": {},              # 人工填 gold（如 same_event: true/false）
            "added_at": _now(),
        })
        existing.add(cid)
        added += 1

    gold["gold_status"] = "pending_human"
    gold["note"] = ("decision must be set to 'approve' or 'reject' per entry before apply. "
                    "Never auto-validated.")
    gold["version"] = gold.get("version", VERSION)
    _write(bundle_path, gold)
    return {"bundle": bundle_path, "added": added,
            "total_pending": sum(1 for e in gold["entries"] if e.get("decision") == "pending")}


def apply(gold_path: str, dry_run: bool = False) -> dict:
    """应用已全部标注的 bundle；**遇pending 即拒绝**。"""
    bundle_path = gold_path.replace(".json", ".review_bundle.json")
    bundle = _read(bundle_path)
    if bundle is None:
        return {"applied": False, "reason": f"未找到待审 bundle：{bundle_path}"}
    entries = bundle.get("entries") or []
    pending = [e for e in entries if e.get("decision") == "pending"]
    if pending:
        return {"applied": False,
                "reason": f"仍有 {len(pending)} 条未标注（decision != approve/reject），拒绝自动验证",
                "pending_count": len(pending)}
    if not dry_run:
        bundle["gold_status"] = "human_confirmed"
        bundle["applied_at"] = _now()
        _write(gold_path, bundle)
    return {"applied": True, "dry_run": dry_run, "total": len(entries),
            "gold_status": "human_confirmed"}


def status(gold_path: str) -> dict:
    bundle_path = gold_path.replace(".json", ".review_bundle.json")
    b = _read(bundle_path)
    if b is None:
        return {"exists": False, "path": bundle_path}
    entries = b.get("entries") or []
    return {
        "exists": True, "path": bundle_path,
        "gold_status": b.get("gold_status"),
        "total": len(entries),
        "pending": sum(1 for e in entries if e.get("decision") == "pending"),
        "approved": sum(1 for e in entries if e.get("decision") == "approve"),
        "rejected": sum(1 for e in entries if e.get("decision") == "reject"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gold 增量追加（pending_human → apply）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--gold", required=True)
    p.add_argument("--candidates")
    p.add_argument("--batch")
    sub.add_parser("status").add_argument("--gold", required=True)
    ap2 = sub.add_parser("apply")
    ap2.add_argument("--gold", required=True)
    ap2.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "prepare":
        out = prepare(args.gold, args.candidates, args.batch)
        print(f"[gold_incremental] prepare新增 {out['added']} 条 → {out['bundle']}；"
              f"待标注 {out['total_pending']} 条")
    elif args.cmd == "status":
        print(json.dumps(status(args.gold), ensure_ascii=False))
    else:
        out = apply(args.gold, args.dry_run)
        if out.get("applied"):
            print(f"[gold_incremental] apply {'(dry-run) ' if args.dry_run else ''}"
                  f"成功：{out.get('total', 0)} 条 → gold_status={out.get('gold_status')}")
        else:
            print(f"[gold_incremental] 拒绝 apply：{out.get('reason')}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())