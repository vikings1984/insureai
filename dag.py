#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1-7 DAG Workflow：把 daily-collect 的 analyze 长链拆为显式 DAG 编排（零依赖）。

背景：daily-collect.yml 的 release job 原先是一长串**顺序写死**的 ``python3 X.py``
步骤（约 30 个），依赖关系只存在于维护者脑子里：无法单独重跑某个阶段、无法回答
「这次是哪一步慢/哪一步炸了」、也无法表达真正的数据依赖（其实多条支链可以并行）。

本模块把这条长链声明为 DAG：

- 每个节点声明 ``requires``（读入的产物）与 ``produces``（写出的产物）；
  **数据边**由二者的交集自动推导 —— 依赖是数据驱动声明的，不再靠注释记忆。
- 另加**顺序边**（声明顺序相邻节点 prev→cur）作为兜底：即使某个 ``produces``
  文件名写错导致数据边缺失，拓扑序仍严格等于原 CI 顺序，**执行行为零变更**。
  （``produces`` 写错只会让依赖图不够精确，不会让流水线跑错顺序。）
- 提供：拓扑排序 + 无环校验、``--only`` 单节点重跑、``--from`` 子树重跑、
  ``--to`` 跑到指定节点（含其全部上游）、``--dry-run`` 只看计划、
  每次执行写出 ``dag_run.json``（逐节点 status / exit_code / duration_sec）。

用法::

    python3 dag.py plan                      # 打印拓扑序与依赖
    python3 dag.py run                       # 按拓扑序执行全部
    python3 dag.py run --to evaluation       # 跑 evaluation 及其上游
    python3 dag.py run --from module_health  # 跑 module_health 及其下游
    python3 dag.py run --only review         # 只跑 review（校验其 requires 已就绪）
    python3 dag.py run --dry-run             # 只打印计划，不执行
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(HERE, "dag_run.json")


def _node(nid, name, cmd, requires=None, produces=None):
    return {
        "id": nid,
        "name": name,
        "cmd": cmd,
        "requires": list(requires or []),
        "produces": list(produces or []),
    }


# 节点按原 CI 声明顺序排列（该顺序即原执行顺序；顺序边保证拓扑序与之严格一致）
NODES = [
    _node("intelligence", "Build event-based intelligence", "python3 intelligence.py",
          requires=["data.json"], produces=["intelligence.json"]),
    _node("claims_build", "Build claim/evidence intelligence", "python3 claims_build.py",
          requires=["intelligence.json"], produces=["claims.json"]),
    _node("trust_build", "Build evidence trust layer", "python3 trust_build.py",
          requires=["claims.json"], produces=["trust.json"]),
    _node("temporal_build", "Build temporal intelligence", "python3 temporal_build.py",
          requires=["intelligence.json"], produces=["temporal.json"]),
    _node("trend_intelligence", "Build trend intelligence", "python3 trend_intelligence.py",
          requires=["intelligence.json"], produces=["trend_intelligence.json"]),
    _node("calibration", "Build bounded human-feedback calibration", "python3 calibration.py",
          requires=["claims.json"], produces=["calibration.json"]),
    _node("decision_build", "Build decision intelligence", "python3 decision_build.py",
          requires=["intelligence.json", "claims.json"], produces=["decisions.json"]),
    _node("decision_stability", "Analyze decision stability", "python3 decision_stability.py",
          requires=["decisions.json"], produces=["decision_stability.json"]),
    _node("decision_credibility", "Build decision credibility summary", "python3 decision_credibility.py",
          requires=["decisions.json"], produces=["decision_credibility.json"]),
    _node("counterfactual", "Run counterfactual robustness analysis", "python3 counterfactual.py",
          requires=["decisions.json"], produces=["counterfactual.json"]),
    _node("scenario", "Run bounded scenario intelligence", "python3 scenario.py",
          requires=["intelligence.json"], produces=["scenario.json"]),
    _node("scenario_matrix", "Run cross-scenario decision matrix", "python3 scenario_matrix.py",
          requires=["scenario.json"], produces=["scenario_matrix.json"]),
    _node("action_triggers", "Build actionable trigger rules", "python3 action_triggers.py",
          requires=["decisions.json"], produces=["action_triggers.json"]),
    _node("execution_readiness", "Build execution readiness packs", "python3 execution_readiness.py",
          requires=["decisions.json"], produces=["execution_readiness.json"]),
    _node("audit_ledger", "Build auditable lineage ledger", "python3 audit_ledger.py",
          requires=["intelligence.json"], produces=["audit_ledger.json"]),
    _node("change_impact", "Analyze downstream change impact", "python3 change_impact.py",
          requires=["decisions.json"], produces=["change_impact.json"]),
    _node("contract", "Validate and stamp data contract", "python3 contract.py",
          requires=["intelligence.json"]),
    _node("shards_check", "Validate intelligence shards consistency",
          "python3 intelligence_shards.py --check", requires=["intelligence.json"]),
    _node("evaluation", "Evaluate intelligence quality", "python3 evaluation.py",
          requires=["intelligence.json", "claims.json"], produces=["evaluation.json"]),
    _node("quality_metrics_gate", "Quantitative quality metrics gate",
          "python3 scripts/quality_metrics_gate.py", requires=["intelligence.json", "claims.json"]),
    _node("production_replay", "Production replay", "python3 production_replay.py",
          requires=["intelligence.json"]),
    _node("replay_compare", "Replay publish gate (P1-A, trial warn-only)",
          "python3 scripts/replay_compare_gate.py",
          requires=["intelligence.json"], produces=["replay_compare_report.json"]),
    _node("review", "Build human review queue (P1-4 状态机同步)", "python3 review.py",
          requires=["intelligence.json", "change_impact.json", "counterfactual.json"],
          produces=["review_queue.json", "review_state.json"]),
    _node("feedback_attribution", "Attribute review feedback to modules", "python3 feedback_attribution.py",
          requires=["review_queue.json"], produces=["feedback_attribution.json"]),
    _node("decision_ledger", "Build E2 decision ledger", "python3 decision_ledger.py",
          requires=["decisions.json"], produces=["decisions_ledger.json"]),
    _node("knowledge_graph", "Build knowledge graph", "python3 knowledge_graph.py",
          requires=["intelligence.json"], produces=["knowledge_graph.json"]),
    _node("validate_kg", "Validate knowledge graph", "python3 scripts/validate_knowledge_graph.py",
          requires=["knowledge_graph.json"]),
    _node("module_health", "Build module health profile", "python3 module_health.py",
          requires=["intelligence.json"], produces=["module_health.json"]),
    _node("module_health_trend", "Build module health trend", "python3 module_health_trend.py",
          requires=["module_health.json"],
          produces=["module_health_trend.json", "module_health_history.json"]),
    _node("trend_attribution", "Attribute temporal health trend", "python3 trend_attribution.py",
          requires=["module_health_trend.json"], produces=["trend_attribution.json"]),
    _node("optimization_backlog", "Build optimization backlog", "python3 optimization_backlog.py",
          requires=["module_health.json"], produces=["optimization_backlog.json"]),
    _node("daily_risk_radar", "Build daily risk radar", "python3 daily_risk_radar.py",
          requires=["intelligence.json"], produces=["daily_risk_radar.json"]),
    _node("owner_risk_view", "Build owner-facing risk view", "python3 owner_risk_view.py",
          requires=["intelligence.json"], produces=["owner_risk_view.json"]),
    _node("freshness", "Measure input-data freshness", "python3 freshness.py",
          requires=["data.json"], produces=["freshness.json"]),
    _node("evidence_availability", "Translate freshness into evidence availability",
          "python3 evidence_availability.py", requires=["freshness.json"],
          produces=["evidence_availability.json"]),
]

NODE_BY_ID = {n["id"]: n for n in NODES}
_ORDER = {n["id"]: i for i, n in enumerate(NODES)}


def build_edges() -> dict[str, set[str]]:
    """构建有向边：数据边（produces ∩ requires）+ 顺序边（声明顺序 prev→cur）。

    顺序边是**安全兜底**：保证拓扑序严格等于原 CI 顺序，
    因此即便某个 produces 文件名与实际不符，执行顺序也不会被改变。
    """
    producer: dict[str, list[str]] = {}
    for n in NODES:
        for f in n["produces"]:
            producer.setdefault(f, []).append(n["id"])

    edges: dict[str, set[str]] = {n["id"]: set() for n in NODES}
    # 1) 数据边
    for n in NODES:
        for f in n["requires"]:
            for p in producer.get(f, []):
                if p != n["id"]:
                    edges[p].add(n["id"])
    # 2) 顺序边（兜底）
    for i in range(1, len(NODES)):
        edges[NODES[i - 1]["id"]].add(NODES[i]["id"])
    return edges


def topo_order(edges: dict[str, set[str]] | None = None) -> tuple[list[str], bool]:
    """Kahn 拓扑排序，tie-break 按声明顺序。返回 (order, acyclic)。"""
    edges = edges if edges is not None else build_edges()
    indeg = {n["id"]: 0 for n in NODES}
    for src, dsts in edges.items():
        for d in dsts:
            indeg[d] += 1
    ready = sorted([n["id"] for n in NODES if indeg[n["id"]] == 0], key=lambda x: _ORDER[x])
    out: list[str] = []
    while ready:
        cur = ready.pop(0)
        out.append(cur)
        for d in sorted(edges.get(cur, set()), key=lambda x: _ORDER[x]):
            indeg[d] -= 1
            if indeg[d] == 0:
                ready.append(d)
                ready.sort(key=lambda x: _ORDER[x])
    return out, len(out) == len(NODES)


def downstream(edges: dict[str, set[str]], start: str) -> set[str]:
    seen, stack = {start}, [start]
    while stack:
        cur = stack.pop()
        for d in edges.get(cur, set()):
            if d not in seen:
                seen.add(d)
                stack.append(d)
    return seen


def upstream(edges: dict[str, set[str]], target: str) -> set[str]:
    rev: dict[str, set[str]] = {n["id"]: set() for n in NODES}
    for s, dsts in edges.items():
        for d in dsts:
            rev[d].add(s)
    seen, stack = {target}, [target]
    while stack:
        cur = stack.pop()
        for u in rev.get(cur, set()):
            if u not in seen:
                seen.add(u)
                stack.append(u)
    return seen


def select(mode: str | None, target: str | None) -> list[str]:
    """按模式选出待执行节点，返回按拓扑序排列的 id 列表。"""
    order, acyclic = topo_order()
    if not acyclic:
        raise RuntimeError("dag has a cycle")
    if not mode or mode == "all":
        return order
    edges = build_edges()
    if mode == "only":
        if target not in NODE_BY_ID:
            raise KeyError(f"unknown node: {target}")
        return [target]
    if mode == "from":
        if target not in NODE_BY_ID:
            raise KeyError(f"unknown node: {target}")
        keep = downstream(edges, target)
    elif mode == "to":
        if target not in NODE_BY_ID:
            raise KeyError(f"unknown node: {target}")
        keep = upstream(edges, target)
    else:
        raise ValueError(f"unknown mode: {mode}")
    return [nid for nid in order if nid in keep]


def missing_requires(node: dict) -> list[str]:
    """返回该节点声明的 requires 中尚不存在的文件（容错 None / 缺键）。"""
    return [f for f in (node.get("requires") or [])
            if not os.path.exists(os.path.join(HERE, f))]


def run(ids: list[str], keep_going: bool = False, dry_run: bool = False) -> dict:
    report = {
        "version": "1.0",
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "count": len(ids),
        "ok": True,
        "nodes": [],
    }
    for nid in ids:
        node = NODE_BY_ID[nid]
        if dry_run:
            report["nodes"].append({
                "id": nid, "name": node["name"], "status": "planned",
                "exit_code": None, "duration_sec": 0.0,
            })
            continue
        t0 = time.time()
        proc = subprocess.run(node["cmd"], shell=True, cwd=HERE)
        dur = round(time.time() - t0, 3)
        status = "ok" if proc.returncode == 0 else "failed"
        report["nodes"].append({
            "id": nid, "name": node["name"], "status": status,
            "exit_code": proc.returncode, "duration_sec": dur,
        })
        if proc.returncode != 0:
            report["ok"] = False
            print(f"[dag] FAILED {nid} ({node['name']}) exit={proc.returncode}", file=sys.stderr)
            if not keep_going:
                break
        else:
            print(f"[dag] ok   {nid} ({node['name']}) {dur}s", file=sys.stderr)
    report["ok"] = bool(report["ok"]) and all(
        n["status"] != "failed" for n in report["nodes"]
    )
    return report


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"plan", "validate"}:
        order, acyclic = topo_order()
        if argv and argv[0] == "validate":
            print(json.dumps({"acyclic": acyclic, "nodes": len(NODES)}, ensure_ascii=False))
            return 0 if acyclic else 1
        rows = []
        for i, nid in enumerate(order, 1):
            n = NODE_BY_ID[nid]
            rows.append({
                "step": i, "id": nid, "name": n["name"],
                "requires": n["requires"], "produces": n["produces"], "cmd": n["cmd"],
            })
        print(json.dumps({"acyclic": acyclic, "count": len(rows), "plan": rows},
                         ensure_ascii=False, indent=2))
        return 0 if acyclic else 1

    if argv[0] == "run":
        mode, target = None, None
        dry_run = "--dry-run" in argv
        keep_going = "--keep-going" in argv
        for flag in ("--only", "--from", "--to"):
            if flag in argv:
                idx = argv.index(flag)
                if idx + 1 >= len(argv):
                    print(f"usage: dag.py run {flag} <node>", file=sys.stderr)
                    return 2
                mode, target = flag.lstrip("-"), argv[idx + 1]
        try:
            ids = select(mode, target)
        except (KeyError, ValueError, RuntimeError) as e:
            print(f"[dag] {e}", file=sys.stderr)
            return 2
        # 单节点重跑：前置产物缺失时拒绝执行（避免带着脏输入跑出错误结论）
        if mode == "only":
            miss = missing_requires(NODE_BY_ID[target])
            if miss:
                print(f"[dag] REFUSED: {target} 缺少上游产物 {miss}；请先跑其上游", file=sys.stderr)
                return 1
        report = run(ids, keep_going=keep_going, dry_run=dry_run)
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"[dag] report -> dag_run.json (ok={report['ok']}, nodes={len(report['nodes'])})",
              file=sys.stderr)
        return 0 if report["ok"] else 1

    print("usage: dag.py [plan|validate|run] [--only|--from|--to <node>] [--dry-run] [--keep-going]",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
