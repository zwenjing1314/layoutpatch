"""Seal full OCR, then gold-blind visual acceptance, then geometry-only metrics."""
from collections import Counter,defaultdict
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0,'/workspace/scripts');sys.path.insert(0,'/interfaces')
from audit_parser_candidates import candidate_metrics,quantiles,METRICS,question_macro,doc_bootstrap_diff
from layoutpatch.datasets.parser_candidates import validate_candidates
from interfaces import export_grounding,sha,write_json

RUN=Path('/run');RAW=Path('/raw');PLAN=Path('/plan')
OLD='mineru_top_v1';NEW='deepseek_ocr2_grounding_v2'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def lines(p):
    with Path(p).open(encoding='utf-8-sig') as f:return [json.loads(s) for s in f if s.strip()]
def dump_lines(p,rows):
    with Path(p).open('x',encoding='utf-8') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
def inputs():
    cfg=read(PLAN/'config.json')
    for name,digest in cfg['manifests'].items():assert sha(PLAN/name)==digest
    pages=lines(PLAN/'full_pages.jsonl');assert len(pages)==837
    return cfg,pages
def seal():
    cfg,pages=inputs();statuses=read(RUN/'page_status.json')
    assert len(statuses)==837 and [s['page_id'] for s in statuses]==[p['page_id'] for p in pages]
    assert not any(s['status'] in ('running','not_attempted') for s in statuses), 'Full run incomplete'
    assert read(RUN/'supervisor.json')['status']=='completed', 'Supervisor did not complete'
    flat=[];receipts=[];files={};required=set(cfg['visual_review_required']);unknown=[];token_max=0
    for page,status in zip(pages,statuses,strict=True):
        pid=page['page_id'];folder=RAW/pid;rows=[];aliases=0
        if status['status']=='exported':
            r=read(folder/'receipt.json');result=read(folder/'candidates.json');gen=read(folder/'generation.json')
            assert r['status']=='exported' and sha(folder/'raw.txt')==r['raw_sha256']
            assert sha(folder/'candidates.json')==r['candidates_sha256']
            assert len(gen)==1 and gen[0]['status']=='eos' and not gen[0]['reached_limit']
            token_max=max(token_max,gen[0]['new_tokens'])
            fresh=export_grounding((folder/'raw.txt').read_text(encoding='utf-8'),pid,page['evaluation_page_size'])
            assert result==fresh, 'Saved export is not reproduced from raw'
            rows=result['candidates'];validate_candidates(rows,pid,page['evaluation_page_size'])
            for row in rows:
                row['condition_id']=NEW
                if row['unknown_label']:unknown.append(dict(page_id=pid,label=row['source']['raw_label']));required.add(pid)
                aliases+=len(row['aliases'])
            assert (folder/'overlay.png').exists()
        else:required.add(pid)
        receipts.append(dict(page_id=pid,status=status['status'],candidate_count=len(rows),duplicate_aliases=aliases,
            raw_reused=status.get('raw_reused',False),error=status.get('error'),error_type=status.get('error_type')))
        flat.extend(rows)
        if folder.exists():
            for file in sorted(folder.rglob('*')):
                if file.is_file():files[file.relative_to(RAW).as_posix()]=sha(file)
    dump_lines(RUN/'candidates.jsonl',flat);write_json(RUN/'page_receipts.json',receipts)
    from PIL import Image,ImageDraw
    sheets=[]
    for offset in range(0,len(pages),12):
        canvas=Image.new('RGB',(1600,1800),'white');draw=ImageDraw.Draw(canvas)
        for j,p in enumerate(pages[offset:offset+12]):
            x=j%4*400;y=j//4*600;pid=p['page_id'];f=RAW/pid/'overlay.png'
            draw.text((x+4,y+4),f'{offset+j} {pid} {receipts[offset+j]["status"]}',fill='black')
            if f.exists():
                with Image.open(f) as image:
                    image=image.convert('RGB');image.thumbnail((395,570));canvas.paste(image,(x,y+24))
        name=f'contact_{offset//12:03d}.png';canvas.save(RUN/name);sheets.append(dict(path=name,sha256=sha(RUN/name)))
    write_json(RUN/'export_manifest.json',dict(status='sealed_awaiting_visual_review',pages=837,condition=NEW,
        candidate_count=len(flat),candidates_sha256=sha(RUN/'candidates.jsonl'),receipts_sha256=sha(RUN/'page_receipts.json'),
        raw_files_sha256=files,sheets=sheets,full_resolution_required=sorted(required),unknown_labels=unknown,
        max_new_tokens_accepted=token_max,failed_pages=[r for r in receipts if r['status']!='exported'],
        protocol_sha256=cfg['protocol_sha256'],config_sha256=sha(PLAN/'config.json'),gold_read=False))
    print(json.dumps(dict(status='sealed_awaiting_visual_review',pages=837,candidates=len(flat),
        full_resolution_pages=len(required),unknown_labels=unknown,failures=[r for r in receipts if r['status']!='exported'])),flush=True)
def compute():
    cfg,pages=inputs();manifest=read(RUN/'export_manifest.json');review=read(RUN/'visual_review.json')
    assert review['status']=='passed' and review['gold_used'] is False
    assert review['export_manifest_sha256']==sha(RUN/'export_manifest.json')
    assert set(review['full_resolution_pages'])==set(manifest['full_resolution_required'])
    assert sha(RUN/'candidates.jsonl')==manifest['candidates_sha256']
    assert sha(RUN/'page_receipts.json')==manifest['receipts_sha256']
    for path,digest in manifest['raw_files_sha256'].items():assert sha(RAW/path)==digest
    units=lines(PLAN/'full_units.jsonl');assert len(units)==1941 and len({u['query_id'] for u in units})==1623
    results={};distribution={};allunits=[];goldrows=[];bycondition={};docof={u['query_id']:u['doc_id'] for u in units}
    for cond,path in [(OLD,PLAN/'old_candidates.jsonl'),(NEW,RUN/'candidates.jsonl')]:
        flat=lines(path);groups={p['page_id']:[] for p in pages}
        for row in flat:groups[row['page_id']].append(row)
        for page in pages:
            rows=groups[page['page_id']];rows.sort(key=lambda r:r['layout_id'])
            validate_candidates(rows,page['page_id'],page['evaluation_page_size'])
        rows=[]
        for unit in units:
            values,best=candidate_metrics(groups[unit['page_id']],unit['gold_boxes'])
            rows.append({**{k:unit[k] for k in ('query_id','page_id','unit_id','doc_id')},'condition':cond,**values})
            for index,value in enumerate(best):goldrows.append(dict(condition=cond,unit_id=unit['unit_id'],page_id=unit['page_id'],
                gold_index=index,gold_type=unit['gold_types'][index],best_iou=value,reachable=value>=.5))
        results[cond]={m:statistics.mean(question_macro(rows,m).values()) for m in METRICS}
        allunits+=rows;bycondition[cond]=rows
        distribution[cond]=dict(candidate_count=len(flat),counts_per_page=quantiles([len(v) for v in groups.values()]),
            area_fraction=quantiles([(r['bbox'][2]-r['bbox'][0])*(r['bbox'][3]-r['bbox'][1])/(r['page_size'][0]*r['page_size'][1]) for r in flat]) if flat else None,
            types=dict(Counter(r['type'] for r in flat)))
    paired={}
    for m in METRICS:
        old=question_macro(bycondition[OLD],m);new=question_macro(bycondition[NEW],m)
        paired[m]={**doc_bootstrap_diff(new,old,docof,iterations=2000,seed=0),
            'improved':sum(new[q]>old[q] for q in old),'worsened':sum(new[q]<old[q] for q in old),
            'unchanged':sum(new[q]==old[q] for q in old)}
    strata={}
    for s in sorted({p['stratum'] for p in pages}):
        ids={p['page_id'] for p in pages if p['stratum']==s}
        strata[s]={c:{m:statistics.mean(question_macro([r for r in bycondition[c] if r['page_id'] in ids],m).values()) for m in METRICS} for c in (OLD,NEW)}
    result=dict(denominators={k:cfg[k] for k in ['pages','documents','questions','units','gold_boxes']},metrics=results,
        paired_new_minus_old=paired,distributions=distribution,strata=strata,failed_pages=manifest['failed_pages'],
        failure_rate=len(manifest['failed_pages'])/837,matching='IoU_desc_one_to_one_greedy',
        aggregation='all_units_within_question_then_question_macro',exploratory=True,score_models_run=False)
    return result,allunits,goldrows
if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='seal':seal()
    else:
        values=compute()
        for name,value in zip(('metrics.json','unit_metrics.json','gold_reachability.json'),values,strict=True):
            if mode=='verify':assert value==read(RUN/name)
            else:write_json(RUN/name,value)
        if mode!='verify':
            write_json(RUN/'candidate_acceptance.json',dict(status='passed',pages=837,config_sha256=sha(PLAN/'config.json'),
                export_sha256=sha(RUN/'export_manifest.json'),metrics_sha256=sha(RUN/'metrics.json'),
                review_sha256=sha(RUN/'visual_review.json'),failure_policy='fixed_denominator_empty_candidates'))
        assert 'torch' not in sys.modules
        print(json.dumps(dict(stage=mode,status='passed',metrics=values[0]['metrics'])),flush=True)
