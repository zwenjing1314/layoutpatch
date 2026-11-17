"""Reuse scientific contract tests and reject candidate identity/type drift."""
import importlib.util
import unittest
import run_deepseek_ocr2_frozen_scoring as new

spec = importlib.util.spec_from_file_location('old_scoring_tests', new.s.ROOT / 'tests/datasets/test_parser_candidate_scoring.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
ScoringContracts = old.ScoringContracts


class DeepSeekBindings(unittest.TestCase):
    def test_type_drift_and_condition_rejected(self):
        pages=[dict(page_id='p',evaluation_page_size=[100,100])]
        row=dict(page_id='p',page_size=[100,100],layout_id=0,candidate_id='p:0',
                 bbox=[0,0,50,50],type='text',type_id=1,text='caption',
                 source={'raw_label':'figure_title'},condition_id=new.CONDITIONS[1],
                 policy='deepseek-ocr2-grounding-v2')
        self.assertEqual(len(new.validate_new_candidates([row],pages)['p']),1)
        for changed in ({'type_id':2},{'condition_id':'mineru_top_v1'},
                        {'type':'title','type_id':2},{'bbox':[0,0,101,50]}):
            with self.assertRaises(ValueError):
                new.validate_new_candidates([{**row,**changed}],pages)

    def test_replacement_geometry_must_rebuild_weights(self):
        torch=new.s.torch
        a=dict(layout_id=0,page_size=[448,448],bbox=[0,0,100,100],type='text')
        b={**a,'bbox':[200,200,400,400]}
        la=new.s.page_layout([a],torch.zeros(1,1024))
        lb=new.s.page_layout([b],torch.zeros(1,1024))
        for key in ('W_raw','W_attn','cover_mass','coords'):
            self.assertFalse(torch.equal(la[key],lb[key]), key)
        self.assertFalse(torch.equal(new.s.patch_iou_matrix([a['bbox']],a['page_size']),
                                     new.s.patch_iou_matrix([b['bbox']],b['page_size'])))


if __name__=='__main__':
    new.s.torch.set_num_threads(2)
    unittest.main()
