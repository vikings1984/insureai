#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a deduplicated optimization backlog with an explicit lifecycle."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
TREND = ROOT / "module_health_trend.json"
OUTPUT = ROOT / "optimization_backlog.json"
HISTORY = ROOT / "optimization_backlog_history.json"
ACTIONS = {"event":"review clustering and entity-resolution rules","trust":"review source independence, conflict detection, and evidence weighting","claims":"review claim extraction and evidence matching coverage","temporal":"review date normalization, trend windows, and momentum thresholds","decision":"review urgency guardrails and role-specific action mapping","counterfactual":"review sensitivity checks and dependency attribution","scenario":"review assumption boundaries and scenario evidence grounding","unknown":"triage unclassified review feedback and improve attribution vocabulary"}

def _load(path: Path) -> dict:
    if not path.exists(): return {}
    try:
        v=json.loads(path.read_text(encoding="utf-8")); return v if isinstance(v,dict) else {}
    except (OSError,json.JSONDecodeError): return {}

def _priority(row: dict) -> tuple[int,str]:
    direction=row.get("direction"); health=row.get("health"); error_rate=float(row.get("error_rate") or 0.0); confidence=float(row.get("confidence") or 0.0); score=int(row.get("priority") or 0)
    if direction=="worsening": score+=25
    if health=="critical": score+=15
    if error_rate>=.5: score+=10
    if confidence<.6: score-=5
    return max(0,min(100,score)),direction or "baseline"

def _triggered(row: dict) -> bool:
    return row.get("direction") in {"worsening","baseline"} or row.get("health") in {"critical","watch"}

def build_backlog(trend:dict|None=None, previous:dict|None=None)->dict:
    trend=_load(TREND) if trend is None else trend
    previous=previous or {}
    previous_by_module={}
    for x in previous.get("items",[]) if isinstance(previous.get("items",[]),list) else []:
        if not isinstance(x,dict): continue
        module=x.get("module")
        if module: previous_by_module[str(module)]=x
        else:
            key=str(x.get("dedupe_key",""))
            if key: previous_by_module[key.split(":",1)[0]]=x
    active=[]
    for module,row in (trend.get("modules",{}) or {}).items():
        if not isinstance(row,dict): continue
        module=str(module); direction=row.get("direction"); triggered=_triggered(row); key=f"quality:{module}"; old=previous_by_module.get(module)
        if not triggered:
            if old:
                status="resolved" if old.get("status") in {"open","recovering","regressed"} else old.get("status","resolved")
                active.append({**old,"module":module,"dedupe_key":key,"status":status,"resolved_at_next_snapshot":True,"error_rate":row.get("error_rate",0.0),"error_rate_delta":row.get("error_rate_delta")})
            continue
        priority,direction=_priority(row)
        if old and old.get("status")=="resolved": status="regressed"
        elif old and old.get("status") in {"open","regressed"}: status="open"
        elif old: status="recovering"
        else: status="open"
        fingerprint=hashlib.sha256(f"{module}|{direction}|{round(float(row.get('error_rate') or 0.0),4)}".encode()).hexdigest()[:16]
        active.append({"backlog_id":f"quality-{module}","module":module,"priority":priority,"direction":direction,"health":row.get("health","no_signal"),"error_rate":row.get("error_rate",0.0),"error_rate_delta":row.get("error_rate_delta"),"optimization_action":ACTIONS.get(module,ACTIONS["unknown"]),"source":"module_health_trend","automation":"advisory_only","dedupe_key":key,"status":status,"fingerprint":fingerprint})
    active.sort(key=lambda x:(x.get("status") in {"open","regressed"},x.get("priority",0),x.get("module","")),reverse=True)
    return {"version":2,"principle":"质量趋势只生成内部优化建议；生命周期可收敛、可回归，不直接改变线上判断或创建外部任务","baseline_available":bool(trend.get("baseline_available")),"items":active[:50]}

def append_history(backlog:dict, history:dict|None=None)->dict:
    history=history or _load(HISTORY); snaps=history.get("snapshots",[]) if isinstance(history,dict) else []
    if not isinstance(snaps,list): snaps=[]
    snapshot_items=[]
    for x in backlog.get("items",[]):
        if isinstance(x,dict): snapshot_items.append({"dedupe_key":x.get("dedupe_key"),"status":x.get("status"),"priority":x.get("priority",0)})
    snaps.append({"items":snapshot_items})
    return {"version":1,"snapshots":snaps[-90:]}

def main()->None:
    trend=_load(TREND); previous=_load(OUTPUT); history=_load(HISTORY); result=build_backlog(trend,previous)
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); HISTORY.write_text(json.dumps(append_history(result,history),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Optimization backlog: {len(result['items'])} items")
if __name__=="__main__": main()
