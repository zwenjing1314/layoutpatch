"""Full page-only OCR. Evaluation inputs and old candidates are not mounted."""
import json
from pathlib import Path
import resource
import sys
import time
import traceback
from collections import Counter

sys.path.insert(0,'/interfaces')
from interfaces import INFER,prepare_page,process_page,export_grounding,sha,source_path,write_json
from supervisor import atomic_json

RUN=Path('/run');RAW=Path('/raw');MODEL=Path('/snapshot');sequence=0
def stage(phase,page_id=None):
    global sequence
    sequence+=1
    atomic_json(RUN/'state.json',dict(sequence=sequence,phase=phase,page_id=page_id,time=time.time()))
def memory(torch):
    return dict(peak_allocated_bytes=torch.cuda.max_memory_allocated(),peak_reserved_bytes=torch.cuda.max_memory_reserved(),
        worker_lifetime_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def preflight():
    cfg=read('/plan/config.json')
    assert sha('/plan/pages.jsonl')==cfg['manifest_sha256']
    assert sha('/interfaces/interfaces.py')==cfg['interfaces_sha256']
    with Path('/plan/pages.jsonl').open() as f:rows=[json.loads(s) for s in f if s.strip()]
    assert cfg['pages']==837 and len(rows)==837 and [r['smoke_order'] for r in rows]==list(range(837))
    pages=[];statuses=[]
    for row in rows:
        try:
            pages.append(prepare_page(row,'/source'))
            statuses.append(dict(page_id=row['page_id'],status='not_attempted'))
        except Exception as exc:
            pages.append(None);statuses.append(dict(page_id=row['page_id'],status='input_failed',error=str(exc)))
    return cfg,rows,pages,statuses
def reused(page,cfg):
    source=Path('/reuse')/page['page_id'];out=RAW/page['page_id']
    saved=read(source/'receipt.json');gen=read(source/'generation.json')
    assert saved['page']==page and saved['infer_parameters']==INFER and saved['status']=='exported'
    assert sha(source/'raw.txt')==saved['raw_sha256'] and len(gen)==1
    assert gen[0]['status']=='eos' and not gen[0]['reached_limit']
    expected={'temperature':0.0,'max_new_tokens':8192,'no_repeat_ngram_size':35,'use_cache':True}
    assert all(gen[0]['kwargs'][k]==v for k,v in expected.items())
    out.mkdir(exist_ok=False)
    raw=(source/'raw.txt').read_text(encoding='utf-8')
    (out/'raw.txt').write_text(raw,encoding='utf-8',newline='')
    write_json(out/'generation.json',gen)
    result=export_grounding(raw,page['page_id'],page['page_size'])
    write_json(out/'candidates.json',result)
    receipt=dict(status=result['status'],page=page,infer_parameters=INFER,generation=gen,
        candidate_count=len(result['candidates']),raw_sha256=sha(out/'raw.txt'),candidates_sha256=sha(out/'candidates.json'),
        continue_allowed=result['status']=='exported',inference_executed=False,raw_reused=True,
        source_run=cfg['reuse_source_run'],original_receipt_sha256=sha(source/'receipt.json'))
    write_json(out/'receipt.json',receipt)
    return receipt
def main():
    stage('preflight');cfg,rows,pages,statuses=preflight()
    atomic_json(RUN/'page_status.json',statuses)
    write_json(RUN/'input_preflight.json',pages)
    integrity=read('/evidence/file_integrity.json')
    assert sha('/evidence/file_integrity.json')=='5cf25b8ccb03e703616acd995461e37d672d7d28e07ccf3a098a854dcdfdc9ee'
    assert integrity['revision']==cfg['revision']
    for item in integrity['files']:
        file=MODEL/item['path'];assert file.stat().st_size==item['bytes'] and sha(file)==item['sha256']
    write_json(RUN/'preload_verification.json',dict(status='passed',model_revision=cfg['revision'],
        model_files=len(integrity['files']),infer_parameters=INFER,seed=0))
    stage('load');start=time.monotonic()
    import torch
    import transformers
    from transformers import AutoTokenizer,AutoModel
    torch.manual_seed(0);torch.cuda.reset_peak_memory_stats()
    tokenizer=AutoTokenizer.from_pretrained(str(MODEL),trust_remote_code=True,local_files_only=True)
    model,info=AutoModel.from_pretrained(str(MODEL),trust_remote_code=True,local_files_only=True,
        use_safetensors=True,torch_dtype=torch.bfloat16,_attn_implementation='flash_attention_2',output_loading_info=True)
    write_json(RUN/'loading_info.json',info)
    assert not any(info.get(k) for k in ('missing_keys','unexpected_keys','mismatched_keys','error_msgs'))
    model=model.eval().cuda();torch.cuda.synchronize()
    load_seconds=time.monotonic()-start
    write_json(RUN/'model_load.json',dict(status='loaded',torch=torch.__version__,transformers=transformers.__version__,
        dtype=str(next(model.parameters()).dtype),elapsed_seconds=load_seconds,resources=memory(torch)))
    for i,(row,page) in enumerate(zip(rows,pages,strict=True)):
        if page is None:continue
        pid=page['page_id'];stage('page',pid)
        statuses[i]['status']='running';atomic_json(RUN/'page_status.json',statuses)
        torch.cuda.reset_peak_memory_stats();start=time.monotonic()
        is_reuse=pid in cfg['reuse_pages']
        receipt=reused(page,cfg) if is_reuse else process_page(model,tokenizer,page,RAW)
        elapsed=time.monotonic()-start
        write_json(RAW/pid/'runtime.json',dict(page_wall_seconds=elapsed,raw_reused=is_reuse,resources=memory(torch)))
        statuses[i].update(status=receipt['status'],candidate_count=receipt.get('candidate_count',0),
            raw_reused=is_reuse,page_wall_seconds=elapsed,error=receipt.get('error'),error_type=receipt.get('error_type'))
        atomic_json(RUN/'page_status.json',statuses)
        if not receipt['continue_allowed']:
            error=(receipt.get('error','')+' '+receipt.get('error_type','')).lower()
            print(json.dumps(dict(event='page_failed',page_id=pid,completed=i+1,total=len(rows),error=error)),flush=True)
            if any(s in error for s in ('out of memory','outofmemory','cuda','cublas','cudnn')):return 2
            continue
        stage('overlay',pid)
        from PIL import Image,ImageDraw
        candidates=read(RAW/pid/'candidates.json')['candidates']
        with Image.open(source_path(row['evaluation_reference']['render_path'],'/source')) as image:overlay=image.convert('RGB')
        draw=ImageDraw.Draw(overlay)
        for c in candidates:
            box=c['bbox'];draw.rectangle(box,outline='red',width=3)
            draw.text((box[0]+2,box[1]+2),str(c['layout_id']),fill='blue',stroke_width=1,stroke_fill='white')
        overlay.save(RAW/pid/'overlay.png')
        write_json(RAW/pid/'candidate_audit.json',dict(candidate_count=len(candidates),
            raw_box_count=sum(1+len(c['aliases']) for c in candidates),types=dict(Counter(c['type'] for c in candidates)),
            unknown_labels=sorted({c['source']['raw_label'] for c in candidates if c['unknown_label']}),
            overlay_sha256=sha(RAW/pid/'overlay.png')))
        print(json.dumps(dict(event='page_exported',page_id=pid,completed=i+1,total=len(rows),
            raw_reused=is_reuse,candidates=len(candidates),page_seconds=elapsed)),flush=True)
    return 0
if __name__=='__main__':
    try:
        if '--preflight' in sys.argv:
            cfg,rows,pages,statuses=preflight()
            write_json(RUN/'preflight_before_gpu.json',dict(statuses=statuses,model_loaded=False,gold_read=False))
            print(json.dumps(dict(status='preflight_complete',pages=len(pages),valid_inputs=sum(p is not None for p in pages),
                failures=[s for s in statuses if s['status']=='input_failed'])),flush=True)
        else:sys.exit(main())
    except Exception as exc:
        write_json(RUN/'worker_error.json',dict(error_type=type(exc).__name__,error=str(exc)))
        traceback.print_exc();sys.exit(2)
