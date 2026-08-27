#!/usr/bin/env python3
import unittest
from review import build_review_queue

class TestReviewQueue(unittest.TestCase):
    def test_conflict_and_weak_evidence_get_review_priority(self):
        data={"events":[{"event_id":"evt1","title":"Test event","scores":{"intelligence_score":90},"trust":{"level":"medium","conflict":True},"claims":{"coverage":50},"article_count":1,"article_ids":["a1"],"source_count":2}],"decisions":[{"event_id":"evt1","urgency":"now","action":"test"}],"temporal":{"topic_signals":[]}}
        result=build_review_queue(data); self.assertEqual(result['generated_count'],1); item=result['items'][0]
        self.assertGreaterEqual(item['priority'],90); self.assertEqual(item['decision']['urgency'],'now')
        reason_types={x['type'] for x in item['reasons']}; self.assertIn('conflict',reason_types); self.assertIn('evidence',reason_types); self.assertIn('decision',reason_types)

    def test_low_input_availability_adds_review_reason_without_changing_decision(self):
        data={"events":[{"event_id":"evt3","title":"Evidence-limited event","scores":{"intelligence_score":60},"trust":{"level":"high","conflict":False},"claims":{"coverage":100},"article_count":3,"article_ids":["a1","a2","a3"],"source_count":3}],"decisions":[{"event_id":"evt3","urgency":"watch","action":"watch"}],"temporal":{"topic_signals":[]}}
        result=build_review_queue(data,evidence_availability={'level':'low','reason':'input is stale'}); item=result['items'][0]
        self.assertEqual(item['decision']['action'],'watch'); self.assertIn('input_quality',{x['type'] for x in item['reasons']})

    def test_clean_low_impact_event_is_not_queued(self):
        data={"events":[{"event_id":"evt2","title":"Routine update","scores":{"intelligence_score":60},"trust":{"level":"high","conflict":False},"claims":{"coverage":100},"article_count":3,"article_ids":["a1","a2","a3"],"source_count":3}],"decisions":[{"event_id":"evt2","urgency":"watch","action":"watch"}],"temporal":{"topic_signals":[]}}
        self.assertEqual(build_review_queue(data)['generated_count'],0)

    def test_persistent_worsening_gets_priority_bump_and_reason(self):
        data={"events":[{"event_id":"evt4","event_type":"trust","title":"Trust issue","scores":{"intelligence_score":60},"trust":{"level":"medium","conflict":True},"claims":{"coverage":80},"article_count":2,"article_ids":["a1","a2"],"source_count":2}],"decisions":[{"event_id":"evt4","urgency":"soon","action":"review"}],"temporal":{"topic_signals":[]}}
        attr={"modules":{"trust":{"classification":"persistent_worsening","reason":"three consecutive worsening observations"}}}
        result=build_review_queue(data,trend_attribution=attr); item=result['items'][0]
        self.assertGreaterEqual(item['priority'],80); self.assertIn('trend_persistence',{x['type'] for x in item['reasons']})

    def test_single_spike_is_deemphasized(self):
        data={"events":[{"event_id":"evt5","event_type":"trust","title":"Transient trust spike","scores":{"intelligence_score":60},"trust":{"level":"medium","conflict":True},"claims":{"coverage":80},"article_count":2,"article_ids":["a1","a2"],"source_count":2}],"decisions":[{"event_id":"evt5","urgency":"soon","action":"review"}],"temporal":{"topic_signals":[]}}
        attr={"modules":{"trust":{"classification":"single_spike","reason":"latest observation worsened"}}}
        result=build_review_queue(data,trend_attribution=attr); item=result['items'][0]
        self.assertIn('trend_noise_guard',{x['type'] for x in item['reasons']})

    def test_conflicted_claims_enter_review_queue(self):
        data={"events":[{"event_id":"evt6","title":"Amount dispute event","scores":{"intelligence_score":70},"trust":{"level":"high","conflict":False},"claims":{"coverage":100,"claims":[{"claim_id":"evt6/c1","claim_type":"transaction_amount","claim_text":"交易金额为 $575 million","verification_status":"conflicted","supporting_evidence":[{"evidence_id":"a1"}],"contradicting_evidence":[{"evidence_id":"a2"}]}]},"article_count":2,"article_ids":["a1","a2"],"source_count":2}],"decisions":[{"event_id":"evt6","urgency":"watch","action":"watch"}],"temporal":{"topic_signals":[]}}
        result=build_review_queue(data); self.assertEqual(result['generated_count'],1); item=result['items'][0]
        self.assertIn('claim_conflict',{x['type'] for x in item['reasons']})
        self.assertGreaterEqual(item['priority'],60)

    def test_event_without_claim_conflict_has_no_claim_conflict_reason(self):
        data={"events":[{"event_id":"evt7","title":"Clean event","scores":{"intelligence_score":70},"trust":{"level":"high","conflict":False},"claims":{"coverage":50,"claims":[{"claim_id":"evt7/c1","claim_type":"event_summary","claim_text":"干净事件","verification_status":"single_source"}]},"article_count":2,"article_ids":["a1","a2"],"source_count":2}],"decisions":[{"event_id":"evt7","urgency":"watch","action":"watch"}],"temporal":{"topic_signals":[]}}
        result=build_review_queue(data)
        for item in result['items']:
            self.assertNotIn('claim_conflict',{x['type'] for x in item['reasons']})

# CI retrigger only; no runtime behavior change.
if __name__=='__main__': unittest.main()
