#!/usr/bin/env python3
import json
from pathlib import Path
from decision import build_decisions

ROOT = Path(__file__).resolve().parent
INTEL = ROOT / 'intelligence.json'

def main():
    data = json.loads(INTEL.read_text(encoding='utf-8'))
    data['decisions'] = build_decisions(data.get('events', []), data.get('temporal', {}), 'executive')[:12]
    data['decision_stats'] = {
        'high_urgency': sum(1 for x in data['decisions'] if x['urgency'] == 'now'),
        'medium_urgency': sum(1 for x in data['decisions'] if x['urgency'] == 'soon'),
        'watch': sum(1 for x in data['decisions'] if x['urgency'] == 'watch'),
    }
    data['version'] = 7
    INTEL.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Decision intelligence:', data['decision_stats'])

if __name__ == '__main__':
    main()
