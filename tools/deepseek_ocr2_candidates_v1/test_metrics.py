import sys
import unittest
sys.path.insert(0,'/workspace/scripts')
from audit_parser_candidates import candidate_metrics,question_macro

class MetricsTests(unittest.TestCase):
    def test_one_to_one_is_distinct_from_independent_reach(self):
        values,_=candidate_metrics([dict(layout_id=0,bbox=[0,0,10,10])],[[0,0,10,10],[0,0,10,10]])
        self.assertEqual(values['oracle@0.5'],1)
        self.assertEqual(values['independent_gold_reach@0.5'],1)
        self.assertEqual(values['greedy_all_candidates_gold_recall@0.5'],.5)
    def test_failed_page_zero_all_metrics(self):
        values,best=candidate_metrics([],[[0,0,10,10]])
        self.assertTrue(all(v==0 for v in values.values()))
        self.assertEqual(best,[0])
    def test_question_macro_retains_zero_unit(self):
        self.assertEqual(question_macro([dict(query_id='q',m=1),dict(query_id='q',m=0)],'m'),{'q':.5})

if __name__=='__main__':unittest.main(verbosity=2)
