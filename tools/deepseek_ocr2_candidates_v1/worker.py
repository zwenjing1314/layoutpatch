"""Fixed 40-page generation only. Gold and baseline candidates are not mounted."""
import json
from pathlib import Path
import resource
import sys
import time
import traceback
from collections import Counter

sys.path.insert(0,'/trial')
from interfaces import INFER, prepare_page, process_page, export_grounding, sha, source_path, write_json
from supervisor import atomic_json

RUN=Path('/run'); RAW=Path('/raw'); MODEL=Path('/snapshot')
sequence=0


def stage(phase, page_id=None):
    global sequence
    sequence+=1
    atomic_json(RUN/'state.json',dict(sequence=sequence,phase=phase,page_id=page_id,time=time.time()))


def memory(torch):
    return dict(peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                current_allocated_bytes=torch.cuda.memory_allocated(),
                current_reserved_bytes=torch.cuda.memory_reserved(),
                worker_lifetime_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)


def reuse_smoke(page):
    """Reuse raw only with matching successful input and decoding identities."""
    pid=page['page_id']; source=Path('/reuse')/pid; out=RAW/pid
    previous=json.loads((source/'receipt.json').read_text())
    generation=json.loads((source/'generation.json').read_text())
    if (previous['page']!=page or previous['infer_parameters']!=INFER or
        previous['status']!='exported' or generation[0]['status']!='eos' or
        generation[0]['reached_limit'] or sha(source/'raw.txt')!=previous['raw_sha256']):
        raise ValueError('smoke raw cannot be reused')
    out.mkdir(exist_ok=False)
    raw=(source/'raw.txt').read_text(encoding='utf-8')
    (out/'raw.txt').write_text(raw,encoding='utf-8',newline='')
    write_json(out/'generation.json',generation)
    result=export_grounding(raw,pid,page['page_size'])
    write_json(out/'candidates.json',result)
    receipt=dict(status=result['status'],page=page,infer_parameters=INFER,generation=generation,
        candidate_count=len(result['candidates']),raw_sha256=sha(out/'raw.txt'),
        candidates_sha256=sha(out/'candidates.json'),continue_allowed=result['status']=='exported',
        inference_executed=False,raw_reused=True,source_run='smoke_20261116_01',
        original_receipt_sha256=sha(source/'receipt.json'),original_generation_sha256=sha(source/'generation.json'))
    write_json(out/'receipt.json',receipt)
    return receipt


def main():
    stage('preflight')
    rows=[json.loads(s) for s in Path('/plan/pages.jsonl').read_text().splitlines()]
    cfg=json.loads(Path('/plan/config.json').read_text(encoding='utf-8-sig'))
    if sha('/plan/pages.jsonl')!=cfg['manifest_sha256']:
        raise ValueError('fixed page manifest changed')
    if [r['smoke_order'] for r in rows]!=list(range(40)):
        raise ValueError('fixed page order changed')
    statuses=[dict(page_id=r['page_id'],status='not_attempted') for r in rows]
    atomic_json(RUN/'page_status.json',statuses)
    pages=[]
    for i,row in enumerate(rows):
        try:
            pages.append(prepare_page(row,'/source'))
        except Exception as exc:
            pages.append(None)
            statuses[i].update(status='input_failed',error=str(exc))
    atomic_json(RUN/'page_status.json',statuses)
    write_json(RUN/'input_preflight.json',pages)
    integrity=json.loads(Path('/evidence/file_integrity.json').read_text())
    if sha('/evidence/file_integrity.json')!='5cf25b8ccb03e703616acd995461e37d672d7d28e07ccf3a098a854dcdfdc9ee':
        raise ValueError('integrity receipt changed')
    for entry in integrity['files']:
        path=MODEL/entry['path']
        if path.stat().st_size!=entry['bytes'] or sha(path)!=entry['sha256']:
            raise ValueError(f'model file changed: {entry["path"]}')
    write_json(RUN/'preload_verification.json',dict(status='passed',files=16,model_revision=integrity['revision'],
        known_index_total_size_discrepancy=True,infer_parameters=INFER,seed=0))
    stage('load')
    started=time.monotonic()
    import torch
    import transformers
    from transformers import AutoTokenizer, AutoModel
    torch.manual_seed(0)
    torch.cuda.reset_peak_memory_stats()
    load_record=dict(status='started',dtype='bfloat16',attention='flash_attention_2',local_files_only=True)
    try:
        tokenizer=AutoTokenizer.from_pretrained(str(MODEL),trust_remote_code=True,local_files_only=True)
        model,loading_info=AutoModel.from_pretrained(str(MODEL),trust_remote_code=True,
            local_files_only=True,use_safetensors=True,torch_dtype=torch.bfloat16,
            _attn_implementation='flash_attention_2',output_loading_info=True)
        write_json(RUN/'loading_info.json',loading_info)
        if any(loading_info.get(key) for key in ('missing_keys','unexpected_keys','mismatched_keys','error_msgs')):
            raise ValueError('nonempty checkpoint loading diagnostics; stop before inference')
        model=model.eval().cuda()
        torch.cuda.synchronize()
        load_record.update(status='loaded',torch=torch.__version__,transformers=transformers.__version__,
            parameter_dtype=str(next(model.parameters()).dtype),device=str(next(model.parameters()).device),
            generation_config=model.generation_config.to_dict())
    except Exception as exc:
        load_record.update(status='failed',error_type=type(exc).__name__,error=str(exc))
        raise
    finally:
        load_record.update(elapsed_seconds=time.monotonic()-started,resources=memory(torch))
        write_json(RUN/'model_load.json',load_record)
    for index,(row,page) in enumerate(zip(rows,pages)):
        if page is None:
            continue
        page_id=page['page_id']
        statuses[index]['status']='running'
        atomic_json(RUN/'page_status.json',statuses)
        stage('page',page_id)
        torch.cuda.reset_peak_memory_stats()
        started=time.monotonic()
        reused=page_id in cfg['reuse_smoke_pages']
        receipt=reuse_smoke(page) if reused else process_page(model,tokenizer,page,RAW)
        elapsed=time.monotonic()-started
        write_json(RAW/page_id/'runtime.json',dict(page_wall_seconds=elapsed,resources=memory(torch),
                   model_load_seconds=load_record['elapsed_seconds'],raw_reused=reused,
                   exit_code=0 if receipt['continue_allowed'] else 2))
        statuses[index].update(status=receipt['status'],page_wall_seconds=elapsed,
                               candidate_count=receipt.get('candidate_count'),raw_sha256=receipt.get('raw_sha256'))
        atomic_json(RUN/'page_status.json',statuses)
        if not receipt['continue_allowed']:
            error=(receipt.get('error','')+' '+receipt.get('error_type','')).lower()
            if any(s in error for s in ('out of memory','outofmemory','cuda','cublas','cudnn')):
                return 2
            continue
        stage('overlay',page_id)
        from PIL import Image, ImageDraw
        candidates=json.loads((RAW/page_id/'candidates.json').read_text())['candidates']
        render=source_path(row['evaluation_reference']['render_path'],'/source')
        with Image.open(render) as im:
            overlay=im.convert('RGB')
        draw=ImageDraw.Draw(overlay)
        for c in candidates:
            box=c['bbox']; draw.rectangle(box,outline='red',width=3)
            draw.text((box[0]+2,box[1]+2),str(c['layout_id']),fill='blue',stroke_width=1,stroke_fill='white')
        overlay.save(RAW/page_id/'overlay.png')
        areas=[(c['bbox'][2]-c['bbox'][0])*(c['bbox'][3]-c['bbox'][1])/(page['page_size'][0]*page['page_size'][1]) for c in candidates]
        write_json(RAW/page_id/'candidate_audit.json',dict(candidate_count=len(candidates),
            raw_box_count=sum(1+len(c['aliases']) for c in candidates),types=dict(Counter(c['type'] for c in candidates)),
            raw_labels=dict(Counter(c['source']['raw_label'] for c in candidates)),
            unknown_labels=sorted({c['source']['raw_label'] for c in candidates if c['unknown_label']}),
            area_fractions=areas,min_area_fraction=min(areas),max_area_fraction=max(areas),
            overlay_sha256=sha(RAW/page_id/'overlay.png')))
        statuses[index].update(status='exported',raw_reused=reused)
        atomic_json(RUN/'page_status.json',statuses)
        print(json.dumps(dict(event='page_exported',completed=index+1,total=40,page_id=page_id,
            candidates=len(candidates),raw_reused=reused,page_seconds=elapsed)),flush=True)
    return 0


if __name__=='__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        write_json(RUN/'worker_error.json',dict(error_type=type(exc).__name__,error=str(exc)))
        traceback.print_exc()
        sys.exit(2)
