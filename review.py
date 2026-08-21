#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Human-in-the-loop review queue for InsureAI intelligence."""
from __future__ import annotations
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
INTEL = ROOT / 'intelligence.json'
QUEUE = ROOT / 'review_queue.json'
COUNTERFACTUAL = ROOT / 'counterfactual.json'
CHANGE_IMPACT = ROOT / 'change_impact.json'

def _priority(event, decision, counterfactual=None, impact=None):
    score = int(event.get('scores', {}).get('intelligence_score') or 0); trust = (event.get('trust') or {}).get('level', 'low'); priority = 20
    if score >= 85: priority += 20
    if trust == 'low': priority += 25
    elif trust == 'medium': priority += 10
    if (event.get('trust') or {}).get('conflict'): priority += 30
    if float((event.get('claims') or {}).get('coverage') or 0) < 80: priority += 20
    if decision and decision.get('urgency') == 'now' and trust != 'high': priority += 30
    if counterfactual and counterfactual.get('changed'): priority += 15
    if impact and impact.get('impact') in {'judgement_changed','event_set_changed'}:
        priority += {'low': 0, 'medium': 10, 'high': 30}.get(impact.get('risk'), 0)
    return min(priority, 100)

def _candidate_reasons(event, decision, temporal, counterfactual, impact=None):
    reasons=[]; trust=event.get('trust') or {}; claims=event.get('claims') or {}; scores=event.get('scores') or {}
    if trust.get('conflict'): reasons.append({'type':'conflict','reason':'trust layer detected source conflict'})
    if float(claims.get('coverage') or 0) < 80: reasons.append({'type':'evidence','reason':f"claim evidence coverage={claims.get('coverage', 0)}"})
    if trust.get('level') == 'low' and int(scores.get('intelligence_score') or 0) >= 80: reasons.append({'type':'evidence','reason':'high-value event has low trust'})
    if decision and decision.get('urgency') == 'now' and trust.get('level') != 'high': reasons.append({'type':'decision','reason':'now recommendation without high trust'})
    signal=next((x for x in (temporal or {}).get('topic_signals', []) if x.get('topic') == event.get('topic')), None)
    if signal and signal.get('phase') in {'accelerating','forming'} and int(signal.get('current_period_count') or 0) < 3: reasons.append({'type':'trend','reason':'trend phase has fewer than 3 current-period events'})
    if int(event.get('article_count') or 0) == 1 and int(scores.get('intelligence_score') or 0) >= 80: reasons.append({'type':'event_cluster','reason':'high-impact single-article event; review cluster boundary'})
    if counterfactual and counterfactual.get('changed'): reasons.append({'type':'counterfactual','reason':f"decision changes when {counterfactual.get('scenario')} is removed"})
    if impact and impact.get('impact') in {'judgement_changed','event_set_changed'}: reasons.append({'type':'change_impact','reason':f"downstream judgement changed; risk={impact.get('risk','unknown')}"})
    return reasons

def build_review_queue(data, counterfactual_cases=None, impact_cases=None):
    decisions={str(x.get('event_id')):x for x in data.get('decisions',[]) if x.get('event_id')}; temporal=data.get('temporal') or {}; cf_by_event={}
    for row in counterfactual_cases or []:
        if row.get('changed'): cf_by_event.setdefault(str(row.get('event_id')), row)
    impact_by_event={str(row.get('event_id')):row for row in impact_cases or [] if row.get('event_id')}
    candidates=[]; events=data.get('events',[]) if isinstance(data.get('events'),list) else []
    for event in events:
        event_id=str(event.get('event_id')); decision=decisions.get(event_id); cf=cf_by_event.get(event_id); impact=impact_by_event.get(event_id); reasons=_candidate_reasons(event,decision,temporal,cf,impact)
        if not reasons: continue
        candidates.append({'event_id':event.get('event_id'),'title':event.get('title'),'event_type':event.get('event_type') or 'industry_update','topic':event.get('topic'),'priority':_priority(event,decision,cf,impact),'status':'pending','reasons':reasons[:6],'article_ids':event.get('article_ids',[]),'source_count':event.get('source_count',0),'trust_level':(event.get('trust') or {}).get('level','low'),'intelligence_score':(event.get('scores') or {}).get('intelligence_score',0),'decision':{'urgency':decision.get('urgency'),'action':decision.get('action')} if decision else None,'change_impact':impact if impact else None})
    candidates.sort(key=lambda x:(x['priority'],x.get('intelligence_score',0)),reverse=True)
    return {'version':1,'principle':'人工复核优先处理不确定性高、潜在影响大且判断发生变化的样本','generated_count':len(candidates),'items':candidates[:100]}

def write_queue(data):
    cases=[]; impacts=[]
    if COUNTERFACTUAL.exists():
        try: cases=json.loads(COUNTERFACTUAL.read_text(encoding='utf-8')).get('cases',[])
        except (json.JSONDecodeError,OSError): cases=[]
    if CHANGE_IMPACT.exists():
        try: impacts=json.loads(CHANGE_IMPACT.read_text(encoding='utf-8')).get('impacted_events',[])
        except (json.JSONDecodeError,OSError): impacts=[]
    queue=build_review_queue(data,cases,impacts); QUEUE.write_text(json.dumps(queue,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); return queue

def main():
    data=json.loads(INTEL.read_text(encoding='utf-8')); queue=write_queue(data); print(f"Review queue generated: {len(queue['items'])} pending candidates")
if __name__=='__main__': main()
