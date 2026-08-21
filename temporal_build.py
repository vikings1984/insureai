#!/usr/bin/env python3
import json
import os
from temporal import build_temporal_intelligence

HERE = os.path.dirname(os.path.abspath(__file__))
INTEL = os.path.join(HERE, 'intelligence.json')

def main():
    with open(INTEL, encoding='utf-8') as f:
        data = json.load(f)
    data['temporal'] = build_temporal_intelligence(data.get('events', []))
    data['version'] = 6
    tmp = INTEL + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.replace(tmp, INTEL)
    print('Temporal intelligence:', len(data['temporal']['topic_signals']), 'topics;', len(data['temporal']['entity_momentum']), 'entities')

if __name__ == '__main__':
    main()
