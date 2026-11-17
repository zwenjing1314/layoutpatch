import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from interfaces import export_grounding, observe_generate, process_page, process_sequence, sha, source_path, prepare_page


def grounding(boxes='[[0,0,999,999]]', label='text', text='正文'):
    return f'<|ref|>{label}<|/ref|><|det|>{boxes}<|/det|>{text}'


class Tensor:
    dtype = 'int64'
    device = 'cpu'
    def __init__(self, values):
        self.values = np.array(values)
        self.shape = self.values.shape
    def __getitem__(self, key):
        return self.values[key]


class FakeModel:
    def __init__(self, tokens=None, raw=None, error=None):
        self.tokens = [42, 2] if tokens is None else tokens
        self.raw = grounding() if raw is None else raw
        self.error = error
    def generate(self, *args, **kwargs):
        self.received = (args, kwargs)
        if self.error:
            raise self.error
        self.output = Tensor([args[0][0].tolist() + self.tokens])
        return self.output
    def infer(self, tokenizer, **kwargs):
        self.infer_kwargs = kwargs
        self.generate(Tensor([[1, 9]]), temperature=0.0, eos_token_id=2,
                      max_new_tokens=8192, no_repeat_ngram_size=35, use_cache=True)
        return self.raw


class ExportTests(unittest.TestCase):
    def test_fixed_figure_title_mapping(self):
        row=export_grounding(grounding(label='figure_title'),'p',[100,100])['candidates'][0]
        self.assertEqual((row['type'],row['type_id'],row['unknown_label']),('text',1,False))
        self.assertEqual(row['source']['raw_label'],'figure_title')
    def test_full_page_and_landscape_no_second_rotation(self):
        row = export_grounding(grounding(), 'page', [1584, 1224])['candidates'][0]
        self.assertEqual(row['bbox'], [0, 0, 1584, 1224])
        half = export_grounding(grounding('[[0,0,499.5,999]]'), 'page', [1584,1224])
        self.assertEqual(half['candidates'][0]['bbox'], [0,0,792,1224])
    def test_multiple_shared_text_and_aliases(self):
        raw = grounding('[[0,0,99,99],[100,100,200,200]]') + grounding('[[0,0,99,99]]','table','表格')
        result = export_grounding(raw, 'p', [999,999])
        self.assertEqual(result['raw_box_count'], 3)
        a,b = result['candidates']
        self.assertEqual(a['source']['shared_text_group'], b['source']['shared_text_group'])
        self.assertEqual(a['aliases'][0]['raw_label'], 'table')
        self.assertEqual(a['aliases'][0]['text'], '表格')
        self.assertEqual(a['text'], raw[slice(*a['source']['text_char_span'])])
    def test_unknown_and_nested_overlap_preserved(self):
        rows=export_grounding(grounding('[[0,0,999,999],[10,10,20,20]]','novel'), 'p',[999,999])['candidates']
        self.assertEqual(len(rows),2)
        self.assertTrue(all(r['unknown_label'] and r['type']=='UNK' for r in rows))
    def test_plain_markdown_and_empty(self):
        for raw in ['', '# title\n|a|b|']:
            self.assertEqual(export_grounding(raw,'p',[100,100])['status'],'no_grounding')
    def test_invalid_box_rejects_whole_page(self):
        for bad in ['[]','[[0,0,0,1]]','[[0,0,1000,1]]','[[true,0,2,2]]',
                    '[[0,0,NaN,2]]','[[0,0,Infinity,2]]','[[0,0,2]]','[[2,2,1,1]]',
                    '__import__("os").system("false")']:
            with self.subTest(bad=bad), self.assertRaises((ValueError,TypeError)):
                export_grounding(grounding()+grounding(bad),'p',[100,100])
    def test_malformed_markers(self):
        for raw in ['<|ref|>text', '<|det|>[]<|/det|>', grounding()+'<|ref',
                    grounding().replace('<|/ref|>', ''), grounding()+'<|/det|>']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                export_grounding(raw,'p',[100,100])


class ObserverTests(unittest.TestCase):
    def test_real_cpu_tensor_and_nn_module_method_restoration(self):
        import torch
        class SyntheticModule(torch.nn.Module):
            def generate(self, ids, **kwargs):
                return torch.cat([ids, torch.tensor([[42,2]])],dim=1)
        model=SyntheticModule(); records=[]
        with observe_generate(model,records):
            output=model.generate(torch.tensor([[1,9]]),eos_token_id=2,max_new_tokens=8192)
        self.assertEqual(output.tolist(),[[1,9,42,2]])
        self.assertEqual(records[0]['status'],'eos')
        self.assertNotIn('generate',vars(model))
    def test_identity_passthrough_restore_and_actual_tokens(self):
        model=FakeModel(); records=[]; ids=Tensor([[1,9]])
        kwargs=dict(eos_token_id=2,max_new_tokens=8192,images=[(ids,ids)])
        with observe_generate(model,records):
            output=model.generate(ids,**kwargs)
            self.assertIs(output,model.output)
            self.assertIs(model.received[0][0],ids)
            self.assertIs(model.received[1]['images'],kwargs['images'])
        self.assertNotIn('generate',vars(model))
        self.assertEqual(records[0]['new_token_ids'],[42,2])
        self.assertEqual(records[0]['status'],'eos')
    def test_limits_eos_at_cap_and_unproven(self):
        for tokens,limit,status in [([3,2],2,'limit_reached'),([3],5,'termination_unproven'),
                                    ([],5,'termination_unproven'),([2,3,2],8,'termination_unproven')]:
            model=FakeModel(tokens=tokens); records=[]
            with observe_generate(model,records):
                model.generate(Tensor([[1]]),eos_token_id=[2],max_new_tokens=limit)
            self.assertEqual(records[0]['status'],status)
    def test_exception_restores_and_records(self):
        model=FakeModel(error=RuntimeError('synthetic OOM')); records=[]
        with self.assertRaises(RuntimeError):
            with observe_generate(model,records):
                model.generate(Tensor([[1]]),eos_token_id=2,max_new_tokens=10)
        self.assertNotIn('generate',vars(model))
        self.assertEqual(records[0]['status'],'error')
    def test_existing_instance_override_preserved(self):
        model=FakeModel(); original=model.generate; model.generate=original
        with observe_generate(model,[]):
            pass
        self.assertIs(model.generate,original)


class PageTests(unittest.TestCase):
    def test_sequence_preserves_four_page_denominator_and_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); base=self.page(root)
            pages=[dict(base,page_id=f'p{i}') for i in range(4)]
            statuses=process_sequence(FakeModel(tokens=[42]),None,pages,root)
            self.assertEqual([r['status'] for r in statuses],['failed']+['not_attempted']*3)
            self.assertEqual(json.loads((root/'page_status.json').read_text()),statuses)

    def test_synthetic_page_receipt_geometry_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); folder=root/'artifacts'; folder.mkdir()
            Image.new('RGB',(20,10),'white').save(folder/'input.png')
            Image.new('RGB',(40,20),'white').save(folder/'render.png')
            ih,rh=sha(folder/'input.png'),sha(folder/'render.png')
            receipt=dict(page_id='p',status='passed',image=dict(sha256=ih,mapping=dict(status='passed',
                source_image_size=[20,10],render_image_size=[40,20],source_exif_orientation=1,checks={'alignment':True})),
                render=dict(render_sha256=rh,page_size=[40,20],rotation=90))
            (folder/'receipt.json').write_text(json.dumps(receipt))
            prefix='C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/artifacts/'
            row=dict(smoke_order=0,page_id='p',purpose='test',effect_evaluation_enabled=False,
                question_answer_gold_provided=False,
                parser_input=dict(image_path=prefix+'input.png',sha256=ih,size=[20,10],exif_orientation=1),
                evaluation_reference=dict(render_path=prefix+'render.png',sha256=rh,page_size=[40,20],
                pdf_rotation=90,mapping_status='passed',receipt_path=prefix+'receipt.json',
                receipt_sha256=sha(folder/'receipt.json'),P_sha256='not_read'))
            page=prepare_page(row,root)
            self.assertEqual(page['page_size'],[40,20])
            row['parser_input']['sha256']='wrong'
            with self.assertRaises(ValueError):
                prepare_page(row,root)

    def page(self, root):
        image=root/'input.png'; image.write_bytes(b'synthetic image for fake infer')
        return dict(page_id='p',image_path=str(image),image_sha256=sha(image),source_size=[100,100],
                    page_size=[100,100],exif_orientation=1,mapping_receipt_sha256='test',
                    render_sha256='test',transform='oriented_full_image_999_to_render_pixels_no_extra_rotation',
                    pdf_rotation_diagnostic_only=0)
    def test_raw_before_failed_export_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); page=self.page(root)
            result=process_page(FakeModel(raw=grounding('[[0,0,1000,2]]')),None,page,root)
            self.assertEqual(result['status'],'failed')
            self.assertTrue((root/'p/raw.txt').exists())
            self.assertFalse((root/'p/candidates.json').exists())
            with self.assertRaises(FileExistsError):
                process_page(FakeModel(),None,page,root)
    def test_success_and_fixed_infer_parameters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); page=self.page(root); model=FakeModel()
            result=process_page(model,None,page,root)
            self.assertTrue(result['continue_allowed'])
            self.assertEqual(model.infer_kwargs['image_file'],page['image_path'])
            self.assertEqual(model.infer_kwargs['image_size'],768)
            self.assertTrue(model.infer_kwargs['eval_mode'])
            self.assertNotIn('page_size',model.infer_kwargs)
    def test_unproven_generation_retains_raw_no_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); page=self.page(root)
            result=process_page(FakeModel(tokens=[42]),None,page,root)
            self.assertFalse(result['continue_allowed'])
            self.assertTrue((root/'p/raw.txt').exists())
            self.assertFalse((root/'p/candidates.json').exists())
    def test_no_grounding_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            result=process_page(FakeModel(raw='plain markdown'),None,self.page(root),root)
            self.assertEqual(result['status'],'no_grounding')
            self.assertFalse(result['continue_allowed'])
    def test_changed_input_stops_before_infer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); page=self.page(root); page['image_sha256']='wrong'; model=FakeModel()
            result=process_page(model,None,page,root)
            self.assertFalse(result['inference_executed'])
            self.assertFalse(hasattr(model,'infer_kwargs'))
    def test_path_escape_and_extra_gold_rejected(self):
        with self.assertRaises(ValueError):
            source_path('C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/artifacts/../../secret','/source')
        with self.assertRaises(ValueError):
            prepare_page({'gold':[]},'/source')


if __name__=='__main__':
    unittest.main(verbosity=2)
