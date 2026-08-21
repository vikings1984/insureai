import unittest
from daily_risk_radar import build_radar

class DailyRiskRadarTests(unittest.TestCase):
    def test_ranks_urgent_impact(self):
        r=build_radar({'status':'ready'},{'decisions':[{'event_id':'e1','title':'urgent','urgency':'now','basis':{'trust_level':'high'}}]},{'impacted_events':[{'event_id':'e1'}]},{'items':[]},{'items':[]})
        self.assertEqual(r['items'][0]['event_id'],'e1')
        self.assertEqual(r['items'][0]['urgency'],'now')
    def test_does_not_mutate_decision(self):
        r=build_radar({'status':'blocked'},{'decisions':[{'event_id':'e1','urgency':'now','basis':{'trust_level':'high'}}]},{'impacted_events':[]},{'items':[]},{'items':[]})
        self.assertEqual(r['items'][0]['urgency'],'now'); self.assertEqual(r['items'][0]['trust_level'],'high')
    def test_regressed_backlog_is_prioritized(self):
        r=build_radar({'status':'ready'},{'decisions':[]},{'impacted_events':[]},{'items':[{'module':'trust','status':'regressed','priority':50}]},{'items':[]})
        self.assertEqual(r['items'][0]['event_id'],'module:trust')
        self.assertGreaterEqual(r['items'][0]['attention_score'],65)

if __name__=='__main__': unittest.main()
