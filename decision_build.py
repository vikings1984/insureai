#!/usr/bin/env python3
import json
from pathlib import Path
from contract import EXPECTED_VERSION
from decision import ROLE_ACTIONS, build_decisions, context_coverage

ROOT = Path(__file__).resolve().parent
INTEL = ROOT / 'intelligence.json'
PER_ROLE_LIMIT = 12

def main():
    data = json.loads(INTEL.read_text(encoding='utf-8'))
    events = data.get('events', [])
    temporal = data.get('temporal', {})
    # P1-2 DEC-2：按 ROLE_ACTIONS 全部 8 角色分发决策；decisions 保留高管视角扁平列表供下游消费。
    by_role = {role: build_decisions(events, temporal, role)[:PER_ROLE_LIMIT] for role in ROLE_ACTIONS}
    data['decisions'] = by_role['executive']
    data['decisions_by_role'] = by_role
    cards = [card for rows in by_role.values() for card in rows]
    data['decision_stats'] = {
        'high_urgency': sum(1 for x in data['decisions'] if x['urgency'] == 'now'),
        'medium_urgency': sum(1 for x in data['decisions'] if x['urgency'] == 'soon'),
        'watch': sum(1 for x in data['decisions'] if x['urgency'] == 'watch'),
        'roles': list(ROLE_ACTIONS),
        'role_card_counts': {role: len(rows) for role, rows in by_role.items()},
        'decision_context_coverage': context_coverage(cards),
    }
    data['version'] = EXPECTED_VERSION
    INTEL.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Decision intelligence:', data['decision_stats'])

if __name__ == '__main__':
    main()
