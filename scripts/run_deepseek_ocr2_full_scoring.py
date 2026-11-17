"""Independent full-data binding; unchanged network, scoring and metric functions."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import time

import run_parser_candidate_study as s

PLAN=s.ROOT/'experiments/parser_candidate_study/deepseek_ocr2_full_v1'
SOURCE=Path('C:/Users/WenJing/Documents/WorkTransfer/layoutpatch')
CONDITIONS=('mineru_top_v1','deepseek_ocr2_grounding_v2')
HISTORY=SOURCE/'runs/retrieval/route_v2_external_eval_v1/20261009_163938'
ENC='artifacts/route_v2_external/encoding_v1/runs/20261009_141912'

def inputs(candidate_run):
    cfg=s.read_json(PLAN/'config.json')
    s.require((cfg['pages'],cfg['questions'],cfg['units'])==(837,1623,1941),'full denominator config changed')
    s.require(cfg['methods']==['A','B','D-no-text'] and cfg['seeds']==[0,1,2] and cfg['checkpoint_epochs']==[1,1,5], 'scope changed')
    s.require(not cfg['training'] and not cfg['paper_editing'] and cfg['fallback']=='none','forbidden execution')
    s.checked(PLAN,'PROTOCOL.md',cfg['protocol_sha256'])
    for file,digest in cfg['manifests'].items():s.checked(PLAN,file,digest)
    for file,digest in cfg['source_bindings'].items():s.checked(SOURCE,file,digest)
    pages=s.read_jsonl(PLAN/'full_pages.jsonl');units=s.read_jsonl(PLAN/'full_units.jsonl')
    s.require(len(pages)==len({p['page_id'] for p in pages})==837 and len(units)==len({u['unit_id'] for u in units})==1941,'duplicate IDs')
    s.require(len({u['query_id'] for u in units})==1623 and sum(len(u['gold_boxes']) for u in units)==cfg['gold_boxes'],'full unit coverage')
    acceptance=s.read_json(candidate_run/'candidate_acceptance.json')
    s.require(acceptance['status']=='passed' and acceptance['pages']==837 and acceptance['config_sha256']==s.sha256(PLAN/'config.json'),'candidate gate missing')
    seal=s.read_json(s.checked(candidate_run,'export_manifest.json',acceptance['export_sha256']))
    s.checked(candidate_run,'metrics.json',acceptance['metrics_sha256'])
    review=s.read_json(s.checked(candidate_run,'visual_review.json',acceptance['review_sha256']))
    s.require(review['status']=='passed' and review['gold_used'] is False,'review gate missing')
    receipts=s.read_json(s.checked(candidate_run,'page_receipts.json',seal['receipts_sha256']))
    s.require([r['page_id'] for r in receipts]==[p['page_id'] for p in pages],'page status coverage changed')
    candidates={};outputs={}
    for condition,path,digest in [(CONDITIONS[0],PLAN/'old_candidates.jsonl',cfg['manifests']['old_candidates.jsonl']),
                                  (CONDITIONS[1],candidate_run/'candidates.jsonl',seal['candidates_sha256'])]:
        flat=s.read_jsonl(s.checked(path.parent,path.name,digest));group={p['page_id']:[] for p in pages}
        for row in flat:
            s.require(row['condition_id']==condition,'condition mismatch');group[row['page_id']].append(row)
        for page in pages:
            group[page['page_id']].sort(key=lambda r:r['layout_id'])
            s.validate_candidates(group[page['page_id']],page['page_id'],page['evaluation_page_size'])
        candidates[condition]=group;outputs[condition]=dict(path=str(path),sha256=digest,count=len(flat))
    for row in receipts:
        s.require(len(candidates[CONDITIONS[1]][row['page_id']])==row['candidate_count'],'receipt candidate mismatch')
        if row['status']!='exported':s.require(row['candidate_count']==0,'failed page acquired candidates')
    manifest=s.read_json(SOURCE/ENC/'manifest.json')
    encoding_cfg=s.yaml.safe_load((SOURCE/'configs/tools/route_v2_external_encoding_v1.yaml').read_text('utf-8-sig'))
    s.require(manifest['config']==encoding_cfg and manifest['schema']=='route-v2-external-encoding-v1','P/Q processing changed')
    info=s.read_json(SOURCE/manifest['run_info'])
    s.require(info['status']=='ready' and info['manifest_sha256']==s.sha256(SOURCE/ENC/'manifest.json') and info['model_identities']==manifest['model_identities'],'encoding identity changed')
    annotations=s.read_jsonl(SOURCE/next(p for p in cfg['source_bindings'] if p.endswith('SciEGQA_Bench.jsonl')))
    for unit in units:
        ann=annotations[int(unit['query_id'].split('_')[-1])]
        s.require(ann['doc_name'].removesuffix('.pdf')==unit['doc_id'],'question/doc mismatch')
        indices=[i for i,p in enumerate(ann['evidence_page']) if f"{unit['doc_id']}_p{p-1}"==unit['page_id']]
        s.require(len(indices)==1 and s.gold_boxes_from_relative(ann['rel_bbox'][indices[0]],unit['page_size'])==unit['gold_boxes'],'gold changed')
    records={r['page_id']:r for r in manifest['pages']};patches={}
    for page in pages:
        rec=records[page['page_id']]
        s.require(rec['sha256']==page['page_cache_sha256'] and rec['image_sha256']==page['parser_image_sha256'],'P/image identity mismatch')
        path=s.checked(SOURCE/ENC,rec['file'],rec['sha256'])
        s.require(path==Path(page['page_cache_path']).resolve(),'P path mismatch')
        s.checked(SOURCE,rec['image_path'],rec['image_sha256'])
        patches[page['page_id']]=s.validate_page(s.torch.load(path,weights_only=True,map_location='cpu'),page['page_id'])
    qr=manifest['queries'];query=s.torch.load(s.checked(SOURCE/ENC,qr['file'],qr['sha256']),weights_only=True,map_location='cpu')
    selected={u['query_id'] for u in units}
    s.validate_queries(query,qr,selected,manifest['model_identities']['colpali']['resolved']['pad_token_id'])
    wm=cfg['weights'];s.validate_seeds(wm['weights']);s.checked(SOURCE,wm['config'],wm['config_sha256'])
    selection=s.read_json(s.checked(SOURCE,wm['run']+'/checkpoint_selection.json',wm['selection_sha256']))['D-no-text']
    models={}
    for weight in wm['weights']:
        path=s.checked(SOURCE,weight['checkpoint'],weight['sha256']);payload=s.torch.load(path,weights_only=True,map_location='cpu')
        chosen=selection[str(weight['seed'])]
        s.require(set(payload)=={'seed','epoch','val_score','state_dict'},'unexpected checkpoint')
        s.require(payload['seed']==weight['seed']==chosen['seed'] and payload['epoch']==weight['selected_epoch']==chosen['best_epoch'],'checkpoint epoch changed')
        s.require(payload['val_score']==chosen['best_val'] and math.isfinite(payload['val_score']) and chosen['checkpoint_sha256']==weight['sha256'] and path.name==chosen['checkpoint'],'source_val choice changed')
        model=s.InputAblatedD('text');model.load_state_dict(payload['state_dict'],strict=True);model.eval().requires_grad_(False)
        for parameter in model.parameters():s.finite(parameter,'checkpoint')
        models[weight['seed']]=model
    bindings=dict(config_sha256=s.sha256(PLAN/'config.json'),candidate_outputs=outputs,weights=wm,
        source_bindings=cfg['source_bindings'],queries_sha256=qr['sha256'],model_identities=manifest['model_identities'],
        candidate_acceptance_sha256=s.sha256(candidate_run/'candidate_acceptance.json'),
        historical_predictions_sha256=s.sha256(HISTORY/'predictions.parquet'),historical_metrics_sha256=s.sha256(HISTORY/'metrics.json'))
    return cfg,pages,units,candidates,patches,{q:query['embeddings'][q].float() for q in selected},models,bindings

def baseline_check(predictions):
    import pandas as pd
    historical=pd.read_parquet(HISTORY/'predictions.parquet')
    old={(r['method'],r['unit_id']):r for r in historical.to_dict('records') if r['method'] in s.LABELS}
    rows=[r for r in predictions if r['condition']==CONDITIONS[0]];mismatches=[];max_delta=0.0
    for row in rows:
        prev=old[row['method'],row['unit_id']]
        rank=list(prev['ranked_layout_ids'])
        scores=[None if x is None or math.isnan(float(x)) else float(x) for x in prev['ranked_scores']]
        equal=rank==row['ranked_layout_ids'] and scores==row['ranked_scores']
        for m in s.METRICS:
            max_delta=max(max_delta,abs(float(prev[m])-row[m]));equal=equal and float(prev[m])==row[m]
        if not equal:mismatches.append(dict(method=row['method'],unit_id=row['unit_id'],rank_equal=rank==row['ranked_layout_ids']))
    return dict(rows=len(rows),expected=1941*5,exact=not mismatches and len(rows)==1941*5,max_metric_delta=max_delta,mismatches=mismatches)

def execute(args):
    cfg,pages,units,candidates,patches,queries,models,bindings=inputs(s.ROOT/args.candidate_run)
    if args.stage=='preflight':
        print(json.dumps(dict(status='passed',pages=len(pages),units=len(units),seeds=list(models),cuda=s.torch.cuda.is_available())),flush=True);return
    out=s.ROOT/'runs/parser_candidate_comparison/v1/full_frozen_scoring'/args.run_id
    verify=args.stage=='verify';s.require(out.exists() if verify else not out.exists(),'output run state mismatch')
    s.CONDITIONS=CONDITIONS;s.CONFIG=PLAN/'config.json'
    files=s.code_files();files['experiments/parser_candidate_study/deepseek_ocr2_full_v1/PROTOCOL.md']=cfg['protocol_sha256']
    files['scripts/run_deepseek_ocr2_full_scoring.ps1']=s.sha256(s.ROOT/'scripts/run_deepseek_ocr2_full_scoring.ps1')
    code_sha=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
    s.require(s.torch.cuda.is_available(),'CUDA required; no silent CPU fallback')
    s.torch.manual_seed(0);s.torch.set_num_threads(4);s.torch.use_deterministic_algorithms(True)
    s.torch.backends.cuda.matmul.allow_tf32=False;s.torch.backends.cudnn.allow_tf32=False
    identity=dict(config=cfg,bindings=bindings,code_sha256=files,combined_code_sha256=code_sha,
        torch=s.torch.__version__,device=s.torch.cuda.get_device_name(0),training=False,parser_inference=False,tf32=False,deterministic=True)
    if verify:
        s.require(s.read_json(out/'identity.json')==identity,'verification identity changed')
        for path,digest in s.read_json(out/'completed.json')['files_sha256'].items():s.checked(out,path,digest)
        saved={(r['condition'],r['method'],r['unit_id']):r for r in s.read_jsonl(out/'predictions.jsonl')}
        derived_saved={r['path']:r for r in s.read_jsonl(out/'derived_manifest.jsonl')}
        s.require(len(saved)==19410 and len(derived_saved)==6696,'incomplete saved output')
    else:
        s.write_json(out/'identity.json',identity)
        for path in files:s.write_bytes(out/'code'/path,(s.ROOT/path).read_bytes())
    bypage=defaultdict(list)
    for unit in units:bypage[unit['page_id']].append(unit)
    predictions=[];derived=[];timings=[];started=time.perf_counter();s.torch.cuda.reset_peak_memory_stats()
    def tensor(path,payload,expected):
        if verify:
            rec=derived_saved[str(path)];stored=s.torch.load(s.checked(s.ROOT,rec['path'],rec['sha256']),weights_only=True,map_location='cpu')
            s.check_cache(stored,expected)
            if 'P_prime' in payload:s.require(s.torch.equal(stored['P_prime'],payload['P_prime']),'fresh P-prime differs')
            else:
                s.require(s.torch.equal(stored['iou'],payload['iou']) and stored['layout_ids']==payload['layout_ids'],'geometry differs')
                for key,value in payload['layout'].items():s.require(s.torch.equal(stored['layout'][key],value),'layout differs')
            derived.append(rec)
        else:derived.append(dict(path=str(path),sha256=s.save_tensor(path,payload),identity=expected))
    with s.torch.inference_mode():
        for condition in CONDITIONS:
            for index,page in enumerate(pages):
                begin=time.perf_counter();pid=page['page_id'];rows=candidates[condition][pid]
                layout=s.page_layout(rows,s.torch.zeros(len(rows),1024,dtype=s.torch.float32))
                s.require(not bool(layout['text'].any()) and bool(layout['mask'].all()),'text/mask violation')
                iou=s.patch_iou_matrix([r['bbox'] for r in rows],page['evaluation_page_size'])
                for value in layout.values():s.finite(value,'layout')
                s.finite(iou,'IoU')
                cand_sha=bindings['candidate_outputs'][condition]['sha256']
                expected=s.cache_identity(condition,cand_sha,page,'geometry',code_sha)
                base=s.ROOT/'artifacts/parser_candidate_comparison/v1/full_derived'/args.run_id/condition/pid
                tensor(base/'layout.pt',dict(identity=expected,layout=layout,iou=iou,layout_ids=[r['layout_id'] for r in rows]),expected)
                transforms={'B':patches[pid].to('cuda:0')};gpu_layout={k:v.to('cuda:0') for k,v in layout.items()}
                for seed,model in models.items():
                    model.to('cuda:0');prime=model(transforms['B'],gpu_layout) if rows else transforms['B'].clone()
                    s.finite(prime,'P prime');transforms[f'D-no-text_seed_{seed}']=prime
                    expected=s.cache_identity(condition,cand_sha,page,bindings['weights']['weights'][seed]['sha256'],code_sha)
                    tensor(base/f'P_prime_seed_{seed}.pt',dict(identity=expected,P_prime=prime.cpu()),expected)
                for unit in bypage[pid]:
                    for label in s.LABELS:
                        if label=='A':values=s.torch.tensor(s.area_scores([r['bbox'] for r in rows]),dtype=s.torch.float32).tolist()
                        else:values=s.region_scores(s.patch_scores(queries[unit['query_id']].to('cuda:0'),transforms[label]),iou.to('cuda:0')).cpu().tolist()
                        row=s.prediction(unit,rows,values,iou,condition,label)
                        if verify:s.require(row==saved[condition,label,unit['unit_id']],'fresh prediction differs')
                        predictions.append(row)
                s.torch.cuda.synchronize();timings.append(dict(condition=condition,page_id=pid,seconds=time.perf_counter()-begin))
                if (index+1)%25==0 or index+1==len(pages):print(json.dumps(dict(event='progress',stage=args.stage,condition=condition,pages_done=index+1,total=len(pages))),flush=True)
    result,questions,transitions=s.analyze(predictions,units,pages)
    result['denominators']={k:cfg[k] for k in ('pages','documents','questions','units','gold_boxes')}
    result['failed_pages']=s.read_json(s.ROOT/args.candidate_run/'export_manifest.json')['failed_pages']
    paired=s.paired_units(predictions,units);baseline=baseline_check(predictions)
    oracle=s.read_json(s.ROOT/args.candidate_run/'metrics.json')['metrics']
    for c in CONDITIONS:
        for label in s.LABELS:
            value=s.statistics.mean(s.question_macro([r for r in predictions if r['condition']==c and r['method']==label],'oracle@0.5').values())
            s.require(value==oracle[c]['oracle@0.5'],'oracle audit differs')
    if verify:
        s.require(result==s.read_json(out/'metrics.json') and questions==s.read_jsonl(out/'question_scores.jsonl') and transitions==s.read_jsonl(out/'paired_question_changes.jsonl') and paired==s.read_jsonl(out/'paired_unit_changes.jsonl'),'analytical replay differs')
        s.require(baseline['exact'],'historical full baseline differs; investigate')
        s.write_json(out/'verification.json',dict(status='passed',prediction_rows_exact=len(predictions),derived_files_exact=len(derived),
            fresh_P_prime_exact=837*2*3,historical_baseline=baseline,oracle_audit_matches=True,training=False))
    else:
        for name,rows in [('predictions.jsonl',predictions),('derived_manifest.jsonl',derived),('question_scores.jsonl',questions),('paired_question_changes.jsonl',transitions),('paired_unit_changes.jsonl',paired)]:s.write_jsonl(out/name,rows)
        s.write_json(out/'metrics.json',result);s.write_json(out/'baseline_check.json',baseline)
        s.write_json(out/'resources.json',dict(total_seconds=time.perf_counter()-started,page_timings=timings,peak_rss_bytes=s.peak_rss(),peak_cuda_allocated_bytes=s.torch.cuda.max_memory_allocated(),peak_cuda_reserved_bytes=s.torch.cuda.max_memory_reserved()))
        output=['identity.json','predictions.jsonl','derived_manifest.jsonl','metrics.json','question_scores.jsonl','paired_question_changes.jsonl','paired_unit_changes.jsonl','resources.json','baseline_check.json']
        s.write_json(out/'completed.json',dict(status='completed_pending_verification',files_sha256={f:s.sha256(out/f) for f in output}))
    print(json.dumps(dict(stage=args.stage,status='passed',baseline_exact=baseline['exact'],predictions=len(predictions),derived=len(derived),summary=result['summary'])),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['preflight','score','verify'],required=True)
    parser.add_argument('--candidate-run',required=True);parser.add_argument('--run-id',required=True);parser.add_argument('--write-broker',action='store_true')
    args=parser.parse_args();s.require(args.run_id.startswith('full_score_') and args.run_id.replace('_','').isalnum(),'full isolated run ID required')
    s.require(args.candidate_run.startswith('runs/parser_candidate_comparison/deepseek_ocr2_full_v1/') and '..' not in args.candidate_run,'candidate path outside full experiment')
    if args.write_broker:s.enable_write_broker()
    execute(args)
