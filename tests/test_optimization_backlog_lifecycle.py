import unittest
from optimization_backlog import build_backlog

class OptimizationBacklogLifecycleTests(unittest.TestCase):
    def test_new_issue_is_open(self):
        trend={"baseline_available":True,"modules":{"trust":{"direction":"worsening","health":"critical","error_rate":0.6,"error_rate_delta":0.1,"priority":60,"confidence":0.9}}}
        out=build_backlog(trend,{})
        self.assertEqual(out['items'][0]['status'],'open')

    def test_existing_active_issue_stays_open(self):
        trend={"baseline_available":True,"modules":{"trust":{"direction":"worsening","health":"critical","error_rate":0.6,"error_rate_delta":0.1,"priority":60,"confidence":0.9}}}
        previous={"items":[{"dedupe_key":"trust:worsening","status":"open","priority":90}]}
        out=build_backlog(trend,previous)
        self.assertEqual(out['items'][0]['status'],'open')

    def test_resolved_issue_is_retained_as_resolved(self):
        trend={"baseline_available":True,"modules":{"trust":{"direction":"stable","health":"healthy","error_rate":0.1,"error_rate_delta":-0.1,"priority":5,"confidence":0.9}}}
        previous={"items":[{"dedupe_key":"trust:worsening","status":"open","priority":90}]}
        out=build_backlog(trend,previous)
        self.assertEqual(out['items'][0]['status'],'resolved')

    def test_resolved_issue_reopens_as_regressed(self):
        trend={"baseline_available":True,"modules":{"trust":{"direction":"worsening","health":"watch","error_rate":0.3,"error_rate_delta":0.1,"priority":30,"confidence":0.9}}}
        previous={"items":[{"dedupe_key":"trust:worsening","status":"resolved","priority":10}]}
        out=build_backlog(trend,previous)
        self.assertEqual(out['items'][0]['status'],'regressed')

    def test_lifecycle_does_not_change_decision_payload(self):
        trend={"baseline_available":True,"modules":{"decision":{"direction":"stable","health":"healthy","error_rate":0.1,"priority":5}}}
        out=build_backlog(trend,{})
        self.assertIn('items',out)
        self.assertNotIn('urgency',out)

if __name__=='__main__': unittest.main()
