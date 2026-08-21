#!/usr/bin/env python3
import unittest
from review import build_review_queue
class TestCounterfactualReview(unittest.TestCase):
    def test_changed_counterfactual_is_reviewed(self):
        data={'events':[{'event_id':'e1','topic':'regulatory_change','event_type':'regulatory','scores':{'intelligence_score':90},'trust':{'level':'high','conflict':False},'claims':{'coverage':100},'article_count':2,'article_ids':['a1','a2'],'source_count':2}],'decisions':[{'event_id':'e1','urgency':'now','action':'test'}],'temporal':{'topic_signals':[]}}
        result=build_review_queue(data,[{'event_id':'e1','scenario':'remove_topic_trend_signal','changed':True}])
        self.assertEqual(result['generated_count'],1)
        self.assertIn('counterfactual',{x['type'] for x in result['items'][0]['reasons']})
if __name__=='__main__': unittest.main()
