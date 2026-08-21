#!/usr/bin/env python3
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from temporal import build_temporal_intelligence

class TestTemporal(unittest.TestCase):
    def test_accelerating_topic(self):
        events=[]
        for i, day in enumerate(['2026-08-03','2026-08-04','2026-08-05','2026-08-06','2026-08-07','2026-08-08']):
            events.append({'event_id':str(i),'topic':'ai_intelligent','published_at':day+'T00:00:00+00:00','source_count':2,'trust':{'level':'high'},'entities':['acme'],'event_type':'product'})
        result=build_temporal_intelligence(events)
        signal=result['topic_signals'][0]
        self.assertIn(signal['phase'], {'accelerating','forming'})
        self.assertGreater(signal['signal_strength'], 0)

    def test_entity_momentum_bounded(self):
        events=[{'event_id':str(i),'topic':'ai_intelligent','published_at':f'2026-08-{i+1:02d}T00:00:00+00:00','source_count':3,'entities':['acme'],'event_type':'product'} for i in range(8)]
        result=build_temporal_intelligence(events)
        entity=result['entity_momentum'][0]
        self.assertEqual(entity['entity'],'acme')
        self.assertLessEqual(entity['momentum'],100)

    def test_no_dates_do_not_create_false_signal(self):
        result=build_temporal_intelligence([{'event_id':'x','topic':'ai_intelligent','published_at':'bad','entities':['acme']}])
        self.assertEqual(result['topic_signals'],[])

if __name__=='__main__': unittest.main()
