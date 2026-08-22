#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rank existing risk signals for daily human attention; never mutate decisions."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from deployment_risk import build_deployment_risk
ROOT = Path(__file__).resolve().parent

def _load(name: str, default):
    path = ROOT / name
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return default

def _urgency_score(value: str | None) -> int:
    return {"now":40,"soon":25,"watch":10}.get(value,0)

def build_radar(credibility=None, intelligence=None, impacts=None, backlog=None, review=None, trend_attribution=None, deployment=None) -> dict:
    credibility=_load('decision_credibility.json',{}) if credibility is None else credibility
    intelligence=_load('intelligence.json',{}) if intelligence is None else intelligence
    impacts=_load('change_impact.json',{}) if impacts is None else impacts
    backlog=_load('optimization_backlog.json',{}) if backlog is None else backlog
    review=_load('review_queue.json',{}) if review is None else review
    trend_attribution=_load('trend_attribution.json',{}) if trend_attribution is None else trend_attribution
    deployment={} if deployment is None else deployment
    credibility_status=credibility.get('status','unknown')
    credibility_penalty={'ready':0,'review':15,'caution':20,'blocked':35}.get(credibility_status,25)
    impact_events={str(x.get('event_id')) for x in impacts.get('impacted_events',[]) if isinstance(x,dict)}
    candidates=[]
    for decision in intelligence.get('decisions',[]) or []:
        event_id=str(decision.get('event_id') or '')
        if not event_id: continue
        basis=decision.get('basis') or {}; score=_urgency_score(decision.get('urgency'))
        if event_id in impact_events: score+=15
        score-=credibility_penalty; reasons=[]
        if decision.get('urgency')=='now': reasons.append('urgent')
        if event_id in impact_events: reasons.append('change_impact')
        if credibility_status in {'review','caution','blocked'}: reasons.append(f'credibility_{credibility_status}')
        candidates.append({'event_id':event_id,'title':decision.get('title') or event_id,'urgency':decision.get('urgency'),'trust_level':basis.get('trust_level'),'attention_score':max(0,min(100,score)),'reasons':reasons,'source':'intelligence.json'})
    for item in review.get('items',[]) or []:
        if not isinstance(item,dict): continue
        event_id=str(item.get('event_id') or item.get('id') or '')
        if not event_id: continue
        attr=item.get('trend_attribution') or {}
        bump={'persistent_worsening':15,'regressed':15,'single_spike':-10,'recovering':-5,'recovered':-10,'stable':-5}.get(attr.get('classification'),0)
        candidates.append({'event_id':event_id,'title':item.get('title') or event_id,'urgency':item.get('urgency'),'trust_level':item.get('trust_level'),'attention_score':max(0,min(100,int(item.get('priority') or 0)+20+bump)),'reasons':['human_review'] + ([f"trend_{attr.get('classification')}"] if attr.get('classification') else []),'source':'review_queue.json','trend_attribution':attr or None})
    for item in backlog.get('items',[]) or []:
        if not isinstance(item,dict) or item.get('status') not in {'open','regressed'}: continue
        module=str(item.get('module','unknown')); attr=(trend_attribution.get('modules') or {}).get(module,{})
        bump={'persistent_worsening':15,'regressed':15,'single_spike':-10,'recovering':-5,'recovered':-10,'stable':-5}.get(attr.get('classification'),0)
        candidates.append({'event_id':f'module:{module}','title':f'模块质量：{module}','urgency':None,'trust_level':None,'attention_score':max(0,min(100,int(item.get('priority') or 0)+(15 if item.get('status')=='regressed' else 0)+bump)),'reasons':['optimization_backlog',item.get('status')] + ([f"trend_{attr.get('classification')}"] if attr.get('classification') else []),'source':'optimization_backlog.json','trend_attribution':attr or None})
    deployment_risk=build_deployment_risk(deployment) if deployment else {'attention':False,'classification':'deployment_unverified','priority':0,'error':None}
    if deployment_risk['attention']:
        candidates.append({'event_id':'deployment:github_pages','title':'生产部署状态：'+deployment_risk['classification'],'urgency':'soon' if deployment_risk['classification']=='deployment_unverified' else 'now','trust_level':None,'attention_score':deployment_risk['priority'],'reasons':[deployment_risk['classification']] + ([deployment_risk['error']] if deployment_risk['error'] else []),'source':'deployment_verification.json','deployment_risk':deployment_risk})
    candidates.sort(key=lambda x:(x['attention_score'],x['event_id']),reverse=True)
    return {'version':3,'generated_at':datetime.now(timezone.utc).isoformat(),'status':credibility_status,'principle':'雷达只排序已有风险信号；部署风险只影响人工注意力与发布可信度，不重新评分、不修改原始决策、不自动执行行动。','items':candidates[:30],'summary':{'items':len(candidates),'top_attention_score':candidates[0]['attention_score'] if candidates else 0,'credibility_status':credibility_status,'impacted_event_count':len(impact_events),'deployment_attention':deployment_risk['attention'],'deployment_classification':deployment_risk['classification']}}

def main():
    result=build_radar(deployment=_load('deployment_verification.json',{})); (ROOT/'daily_risk_radar.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(f"Daily risk radar: {len(result['items'])} items")
if __name__=='__main__': main()
