import unittest
from daily_risk_radar import build_radar

class DailyRiskRadarTests(unittest.TestCase):
    def test_ranks_urgent_impact(self):
        r=build_radar({'status':'ready'},{'decisions':[{'event_id':'e1','title':'urgent','urgency':'now','basis':{'trust_level':'high'}}]},{'impacted_events':[{'event_id':'e1'}]},{'items':[]},{'items':[]})
        self.assertEqual(r['items'][0]['event_id'],'e1'); self.assertEqual(r['items'][0]['urgency'],'now')
    def test_does_not_mutate_decision(self):
        r=build_radar({'status':'blocked'},{'decisions':[{'event_id':'e1','urgency':'now','basis':{'trust_level':'high'}}]},{'impacted_events':[]},{'items':[]},{'items':[]})
        self.assertEqual(r['items'][0]['urgency'],'now'); self.assertEqual(r['items'][0]['trust_level'],'high')
    def test_regressed_backlog_is_prioritized(self):
        r=build_radar({'status':'ready'},{'decisions':[]},{'impacted_events':[]},{'items':[{'module':'trust','status':'regressed','priority':50}]},{'items':[]})
        self.assertEqual(r['items'][0]['event_id'],'module:trust'); self.assertGreaterEqual(r['items'][0]['attention_score'],65)
    def test_persistent_worsening_beats_single_spike(self):
        backlog={'items':[{'module':'trust','status':'open','priority':50},{'module':'event','status':'open','priority':50}]}
        trend={'modules':{'trust':{'classification':'persistent_worsening'},'event':{'classification':'single_spike'}}}
        r=build_radar({'status':'ready'},{'decisions':[]},{'impacted_events':[]},backlog,{'items':[]},trend)
        self.assertEqual(r['items'][0]['event_id'],'module:trust'); self.assertGreater(r['items'][0]['attention_score'],r['items'][1]['attention_score'])
    def test_failed_deployment_is_top_attention_signal(self):
        deployment={'status':'failed','verified':False,'error':'request_failed'}
        r=build_radar({'status':'ready'},{'decisions':[]},{'impacted_events':[]},{'items':[]},{'items':[]},deployment=deployment, deployment_history=[{'verified':False},{'verified':False}])
        self.assertEqual(r['items'][0]['event_id'],'deployment:github_pages')
        self.assertEqual(r['items'][0]['deployment_risk']['classification'],'deployment_persistent_failure')
        self.assertEqual(r['items'][0]['attention_score'],95)
    def test_verified_deployment_does_not_enter_radar(self):
        deployment={'status':'verified','verified':True}
        r=build_radar({'status':'ready'},{'decisions':[]},{'impacted_events':[]},{'items':[]},{'items':[]},deployment=deployment)
        self.assertFalse(any(x['event_id']=='deployment:github_pages' for x in r['items']))

if __name__=='__main__': unittest.main()
