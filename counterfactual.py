#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Counterfactual robustness checks for InsureAI intelligence decisions."""
from __future__ import annotations
import json
from pathlib import Path
from decision import build_decisions
ROOT = Path(__file__).resolve().parent
INTEL = ROOT / 'intelligence.json'
OUTPUT = ROOT / 'counterfactual.json'
def _decision_by_event(events, temporal):
    rows = build_decisions(events, temporal, 'executive')
    return {str(x.get('event_id')): x for x in rows}
def _strip_conflicting_signal(event):
    clone = dict(event)
    trust = dict(clone.get('trust') or {})
    trust['conflict'] = False
    clone['trust'] = trust
    return clone
def _strip_trend(temporal, topic):
    out = dict(temporal or {})
    out['topic_signals'] = [x for x in out.get('topic_signals', []) if x.get('topic') != topic]
    return out
def build_counterfactual(data: dict) -> dict:
    events = data.get('events', []) if isinstance(data, dict) else []
    temporal = data.get('temporal') or {}
    baseline = _decision_by_event(events, temporal)
    cases = []
    for event in events:
        eid = str(event.get('event_id'))
        base = baseline.get(eid)
        if not base: continue
        cf = _decision_by_event([_strip_conflicting_signal(event)], temporal).get(eid, base)
        cases.append({'event_id': eid, 'scenario': 'remove_conflict_flag', 'baseline_urgency': base['urgency'], 'counterfactual_urgency': cf['urgency'], 'changed': base['urgency'] != cf['urgency'], 'note': '仅移除冲突标记；用于验证决策是否被单一信号支配。'})
        signal_topic = event.get('topic')
        if signal_topic:
            cf2 = _decision_by_event([event], _strip_trend(temporal, signal_topic)).get(eid, base)
            cases.append({'event_id': eid, 'scenario': 'remove_topic_trend_signal', 'baseline_urgency': base['urgency'], 'counterfactual_urgency': cf2['urgency'], 'changed': base['urgency'] != cf2['urgency'], 'note': '移除该主题趋势信号；用于验证现在/近期判断是否过度依赖时间趋势。'})
    changed = sum(1 for x in cases if x['changed'])
    return {'version': 1, 'principle': '高价值结论必须在去除单一关键输入后保持合理稳健，否则进入人工复核。', 'total_cases': len(cases), 'fragile_cases': changed, 'fragility_rate': round(changed / len(cases), 4) if cases else 0.0, 'cases': cases[:500]}
def main():
    data = json.loads(INTEL.read_text(encoding='utf-8'))
    result = build_counterfactual(data)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('total_cases', 'fragile_cases', 'fragility_rate')}, ensure_ascii=False))
if __name__ == '__main__': main()
