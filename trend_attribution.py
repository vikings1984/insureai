#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Classify module-health changes by persistence, recovery, and recurrence."""
from __future__ import annotations
import json
from pathlib import Path
from contract import ARTIFACT_VERSIONS
ROOT=Path(__file__).resolve().parent

def _load(path: Path)->dict:
    if not path.exists(): return {}
    try:
        value=json.loads(path.read_text(encoding='utf-8')); return value if isinstance(value,dict) else {}
    except (OSError,json.JSONDecodeError): return {}

def _rows(history:dict,module:str)->list[dict]:
    out=[]
    for snap in history.get('snapshots',[]) or []:
        if isinstance(snap,dict):
            row=(snap.get('modules') or {}).get(module)
            if isinstance(row,dict): out.append(row)
    return out

def classify_module(direction:str, rows:list[dict])->tuple[str,str]:
    if not rows: return 'baseline','no historical baseline'
    recent=rows[-4:]
    if direction=='worsening':
        if len(recent)>=3 and all(recent[i].get('error_rate',0)>=recent[i-1].get('error_rate',0) for i in range(1,len(recent))):
            return 'persistent_worsening','error rate increased across consecutive observations'
        return 'single_spike','latest observation worsened materially without sufficient persistence'
    if direction=='improving':
        if len(recent)>=2 and recent[-1].get('error_rate',0)<recent[-2].get('error_rate',0):
            return 'recovering','error rate is moving back toward baseline'
        return 'improving','latest observation improved materially'
    if direction=='stable':
        vals=[r.get('error_rate',0) for r in recent]
        if len(vals)>=3 and max(vals)-min(vals)>=0.05: return 'recovered','recent volatility subsided after a material deviation'
        return 'stable','no material recent change'
    return 'baseline','insufficient evidence for temporal attribution'

def build_attribution(trend:dict|None=None,history:dict|None=None)->dict:
    trend=_load(ROOT/'module_health_trend.json') if trend is None else trend
    history=_load(ROOT/'module_health_history.json') if history is None else history
    modules={}
    for module,row in (trend.get('modules',{}) or {}).items():
        if not isinstance(row,dict): continue
        hist=_rows(history,str(module)); classification,reason=classify_module(str(row.get('direction','baseline')),hist)
        regressions=0; resolved=False
        for item in hist:
            rate=float(item.get('error_rate') or 0)
            if rate<=0.10: resolved=True
            elif resolved and rate>=0.15: regressions+=1
        modules[str(module)]={'classification':classification,'reason':reason,'observation_count':len(hist),'regression_count':regressions,'evidence':'historical_health_snapshots'}
    return {'version':ARTIFACT_VERSIONS['trend_attribution.json'],'principle':'趋势归因用于降低复核噪声，不直接改变评分、决策或紧迫度','modules':modules}

def main()->None:
    result=build_attribution(); (ROOT/'trend_attribution.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(f"Trend attribution: {len(result['modules'])} modules")
if __name__=='__main__': main()
