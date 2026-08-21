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
def _priority(event, decision, counterfactual=None):
    score = int(event.get('scores', {}).get('intelligence_score') or 0); trust = (event.get('trust') or {}).get('level', 'low'); priority = 20
    if score >= 85: priority += 20
    if trust == 'low': priority += 25
    elif trust == 'medium': priority += 10
    if (event.get('trust') or {}).get('conflict'): priority += 30
    if float((event.get('claims') or {}).get('coverage') or 0) < 80: priority += 20
    if decision and decision.get('urgency') == 'now' and trust != 'high': priority += 30
    if counterfactual and counterfactual.get('changed'): priority += 15
    return min(priority, 100)
def _candidate_reasons(event, decision, temporal, counterfactual):
    reasons=[]; trust=event.get('trust') or {}; claims=event.get('claims') or {}; scores=event.get('scores') or {}
    if trust.get('conflict'): reasons.append({'type':'conflict','reason':'trust layer detected source conflict'})
    if float(claims.get('coverage') or 0) < 80: reasons.append({'type':'evidence','reason':f"claim evidence coverage={claims.get('coverage', 0)}"})
    if trust.get('level') == 'low' and int(scores.get('intelligence_score') or 0) >= 80: reasons.append({'type':'evidence','reason':'high-value event has low trust'})
    if decision and decision.get('urgency') == 'now' and trust.get('level') != 'high': reasons.append({'type':'decision','reason':'now recommendation without high trust'})
    signal=next((x for x in (temporal or {}).get('topic_signals', []) if x.get('topic') == event.get('topic')), None)
    if signal and signal.get('phase') in {'accelerating','forming'} and int(signal.get('current_period_count') or 0) < 3: reasons.append({'type':'trend','reason':'trend phase has fewer than 3 current-period events'})
    if int(event.get('article_count') or 0) == 1 and int(scores.get('intelligence_score') or 0) >= 80: reasons.append({'type':'event_cluster','reason':'high-impact single-article event; review cluster boundary'})
    if counterfactual and counterfactual.get('changed'): reasons.append({'type':'counterfactual','reason':f"decision changes when {counterfactual.get('scenario')} is removed"})
    return reasons
def build_review_queue(data, counterfactual_cases=None):
    decisions={str(x.get('event_id')):x for x in data.get('decisions',[]) if x.get('event_id')}; temporal=data.get('temporal') or {}; cf_by_event={}
    for row in counterfactual_cases or []:
        if row.get('changed'): cf_by_event.setdefault(str(row.get('event_id')), row)
    candidates=[]; events=data.get('events',[]) if isinstance(data.get('events'),list) else []
    for event in events:
        decision=decisions.get(str(event.get('event_id'))); cf=cf_by_event.get(str(event.get('event_id'))); reasons=_candidate_reasons(event,decision,temporal,cf)
        if not reasons: continue
        candidates.append({'event_id':event.get('event_id'),'title':event.get('title'),'event_type':event.get('event_type') or 'industry_update','topic':event.get('topic'),'priority':_priority(event,decision,cf),'status':'pending','reasons':reasons[:5],'article_ids':event.get('article_ids',[]),'source_count':event.get('source_count',0),'trust_level':(event.get('trust') or {}).get('level','low'),'intelligence_score':(event.get('scores') or {}).get('intelligence_score',0),'decision':{'urgency':decision.get('urgency'),'action':decision.get('action')} if decision else None})
    candidates.sort(key=lambda x:(x['priority'],x.get('intelligence_score',0)),reverse=True)
    return {'version':1,'principle':'人工复核优先处理不确定性高且潜在影响大的样本','generated_count':len(candidates),'items':candidates[:100]}
def write_queue(data):
    cases=[]
    if COUNTERFACTUAL.exists():
        try: cases=json.loads(COUNTERFACTUAL.read_text(encoding='utf-8')).get('cases',[])
        except (json.JSONDecodeError,OSError): cases=[]
    queue=build_review_queue(data,cases); QUEUE.write_text(json.dumps(queue,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); return queue
def main():
    data=json.loads(INTEL.read_text(encoding='utf-8')); queue=write_queue(data); print(f"Review queue generated: {len(queue['items'])} pending candidates")
if __name__=='__main__': main()
