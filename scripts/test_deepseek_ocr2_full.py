"""CPU contract tests for full-study joins and historical result verification."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import run_deepseek_ocr2_full_scoring as full
import pandas as pd

spec=importlib.util.spec_from_file_location('prior_tests',full.s.ROOT/'tests/datasets/test_parser_candidate_scoring.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
ScoringContracts=prior.ScoringContracts

class FullComparison(unittest.TestCase):
    def test_full_pages_and_units_are_exact_and_complete(self):
        cfg=full.s.read_json(full.PLAN/'config.json')
        pages=full.s.read_jsonl(full.PLAN/'full_pages.jsonl');units=full.s.read_jsonl(full.PLAN/'full_units.jsonl')
        self.assertEqual((len(pages),len(units),len({u['query_id'] for u in units})),(837,1941,1623))
        self.assertEqual({u['page_id'] for u in units},{p['page_id'] for p in pages})
        self.assertEqual(sum(len(u['gold_boxes']) for u in units),2497)
        parser=full.s.read_jsonl(full.PLAN/'parser_pages.jsonl')
        for page in parser:
            self.assertEqual(set(page),{'smoke_order','page_id','purpose','effect_evaluation_enabled','question_answer_gold_provided','parser_input','evaluation_reference'})
            self.assertFalse(page['question_answer_gold_provided'])
        self.assertEqual(len(cfg['reuse_pages']),40)
    def test_historical_difference_is_not_hidden(self):
        row=dict(method='A',unit_id='q:p',condition=full.CONDITIONS[0],ranked_layout_ids=[0,1],ranked_scores=[3.0,None],
            **{m:1.0 for m in full.s.METRICS})
        historical=pd.DataFrame([{**row,'ranked_scores':[3.0,float('nan')]}])
        with patch.object(pd,'read_parquet',return_value=historical):
            result=full.baseline_check([row])
            self.assertEqual(result['mismatches'],[])
            self.assertFalse(result['exact']) # incomplete denominator cannot pass
            changed={**row,'hit1@0.5':0.0}
            self.assertEqual(len(full.baseline_check([changed])['mismatches']),1)
    def test_empty_candidates_preserve_multigold_denominator(self):
        unit=dict(query_id='q',doc_id='d',page_id='p',unit_id='q:p',page_size=[100,100],gold_boxes=[[0,0,50,50],[50,50,100,100]])
        pred=full.s.prediction(unit,[],[],full.s.torch.zeros(0,1024),full.CONDITIONS[1],'D-no-text_seed_2')
        self.assertEqual(pred['empty'],1.0)
        self.assertEqual(pred['gold_recall@5@0.5'],0.0)
        self.assertEqual(pred['oracle@0.5'],0.0)

if __name__=='__main__':
    full.s.torch.set_num_threads(2)
    unittest.main(verbosity=2)
