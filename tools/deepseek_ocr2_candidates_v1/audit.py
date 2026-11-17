"""Audit saved candidates only. No OCR model imports or scoring; gold after seal/review."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0,'/workspace/scripts')
from audit_parser_candidates import candidate_metrics,quantiles,METRICS,question_macro,doc_bootstrap_diff
from interfaces import sha,write_json

RUN=Path('/run'); RAW=Path('/raw')
OLD='mineru_top_v1'; NEW='deepseek_ocr2_grounding_v2'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def lines(path):
    return [json.loads(s) for s in Path(path).read_text(encoding='utf-8-sig').splitlines() if s.strip()]


def fixed_pages():
    assert sha('/eval/sample_pages.jsonl')=='a8930e50677a1a21a992351ecd426d8590cd4a76917f1eaeb5762a9e82de6e40'
    pages=lines('/eval/sample_pages.jsonl')
    assert len(pages)==40 and len({p['doc_id'] for p in pages})==35
    return pages


def seal():
    pages=fixed_pages(); statuses=read(RUN/'page_status.json')
    assert [p['page_id'] for p in pages]==[s['page_id'] for s in statuses]
    flat=[]; receipts=[]; files={}; overlays=[]
    for page,status in zip(pages,statuses):
        pid=page['page_id']; folder=RAW/pid; candidates=[]
        if status['status']=='exported':
            saved=read(folder/'receipt.json'); result=read(folder/'candidates.json')
            assert saved['status']=='exported' and sha(folder/'raw.txt')==saved['raw_sha256']
            assert sha(folder/'candidates.json')==saved['candidates_sha256']
            gen=read(folder/'generation.json')
            assert len(gen)==1 and gen[0]['status']=='eos' and not gen[0]['reached_limit']
            candidates=result['candidates']
            for i,c in enumerate(candidates):
                assert c['page_id']==pid and c['layout_id']==i and c['page_size']==page['evaluation_page_size']
                c['condition_id']=NEW
            overlays.append(dict(page_id=pid,path=f'{pid}/overlay.png',sha256=sha(folder/'overlay.png')))
        # Failed and never-attempted pages explicitly contribute zero candidates.
        receipts.append(dict(page_id=pid,status=status['status'],candidate_count=len(candidates),
            raw_reused=status.get('raw_reused',False),error=status.get('error')))
        flat.extend(candidates)
        if folder.exists():
            for file in folder.rglob('*'):
                if file.is_file():files[file.relative_to(RAW).as_posix()]=sha(file)
    with (RUN/'candidates.jsonl').open('x',encoding='utf-8') as stream:
        for c in flat:stream.write(json.dumps(c,ensure_ascii=False)+'\n')
    write_json(RUN/'page_receipts.json',receipts)
    write_json(RUN/'overlays.json',overlays)
    # Contact sheets are diagnostic only, without questions or gold.
    from PIL import Image,ImageDraw
    overlay_map={o['page_id']:o for o in overlays}
    sheet_files=[]
    for offset in range(0,40,4):
        canvas=Image.new('RGB',(1200,1660),'white'); draw=ImageDraw.Draw(canvas)
        for j,p in enumerate(pages[offset:offset+4]):
            x=(j%2)*600; y=(j//2)*830; pid=p['page_id']
            draw.text((x+5,y+5),f'{offset+j:02d} {pid} | {receipts[offset+j]["status"]}',fill='black')
            if pid in overlay_map:
                with Image.open(RAW/overlay_map[pid]['path']) as im:
                    im=im.convert('RGB'); im.thumbnail((595,800)); canvas.paste(im,(x,y+25))
        name=f'contact_{offset//4:02d}.png'; canvas.save(RUN/name)
        sheet_files.append(dict(path=name,sha256=sha(RUN/name),pages=[p['page_id'] for p in pages[offset:offset+4]]))
    first={}
    for p in pages:first.setdefault(p['stratum'],p['page_id'])
    write_json(RUN/'export_manifest.json',dict(condition=NEW,pages=40,candidate_count=len(flat),
        files_sha256=files,candidates_sha256=sha(RUN/'candidates.jsonl'),
        receipts_sha256=sha(RUN/'page_receipts.json'),overlays_sha256=sha(RUN/'overlays.json'),
        sheets=sheet_files,full_resolution_required=list(first.values()),gold_read=False))


def compute():
    pages=fixed_pages(); pmap={p['page_id']:p for p in pages}
    manifest=read(RUN/'export_manifest.json'); visual=read(RUN/'visual_review.json')
    assert visual['status']=='passed' and visual['gold_used'] is False
    assert visual['export_manifest_sha256']==sha(RUN/'export_manifest.json')
    assert set(visual['reviewed_pages'])==set(pmap)
    assert set(visual['full_resolution_pages'])==set(manifest['full_resolution_required'])
    assert sha(RUN/'candidates.jsonl')==manifest['candidates_sha256']
    assert sha(RUN/'page_receipts.json')==manifest['receipts_sha256']
    for path,digest in manifest['files_sha256'].items():assert sha(RAW/path)==digest
    for sheet in manifest['sheets']:assert sha(RUN/sheet['path'])==sheet['sha256']
    assert sha('/eval/old_candidates.jsonl')=='5fdc3ef44b5ea64abdd030330b4703a27e6fde5ef2f5ed4f50389b196d1ec00f'
    assert sha('/eval/sample_units.jsonl')=='9fff08e97b497001de4c9723a57bf402afed6a4acbf351e1b9f86975274381f2'
    units=lines('/eval/sample_units.jsonl')
    assert len(units)==126 and len({u['query_id'] for u in units})==125 and sum(len(u['gold_boxes']) for u in units)==159
    assert {u['page_id'] for u in units}==set(pmap)
    grouped={}; distributions={}; results={}; unit_rows=[]; gold_rows=[]
    bycondition={}; doc_of={u['query_id']:u['doc_id'] for u in units}
    for condition,path in [(OLD,'/eval/old_candidates.jsonl'),(NEW,RUN/'candidates.jsonl')]:
        flat=lines(path); cand=defaultdict(list)
        for c in flat:cand[c['page_id']].append(c)
        assert not (set(cand)-set(pmap))
        if condition==OLD:assert len(flat)==500
        for p in pages:cand[p['page_id']].sort(key=lambda c:c['layout_id'])
        grouped[condition]=cand; rows=[]
        for u in units:
            values,best=candidate_metrics(cand[u['page_id']],u['gold_boxes'])
            rows.append({**{k:u[k] for k in ('query_id','unit_id','page_id','doc_id')},'condition':condition,**values})
            for index,value in enumerate(best):
                gold_rows.append(dict(condition=condition,unit_id=u['unit_id'],page_id=u['page_id'],
                    gold_index=index,gold_type=u['gold_types'][index],best_iou=value,reachable=value>=.5))
        bycondition[condition]=rows; unit_rows+=rows
        results[condition]={m:statistics.mean(question_macro(rows,m).values()) for m in METRICS}
        distributions[condition]=dict(candidate_count=len(flat),counts_per_page=quantiles([len(cand[p]) for p in pmap]),
            area_fraction=quantiles([(c['bbox'][2]-c['bbox'][0])*(c['bbox'][3]-c['bbox'][1])/(c['page_size'][0]*c['page_size'][1]) for c in flat]),
            types=dict(Counter(c['type'] for c in flat)))
    paired={}
    for m in METRICS:
        old=question_macro(bycondition[OLD],m); new=question_macro(bycondition[NEW],m)
        paired[m]={**doc_bootstrap_diff(new,old,doc_of,iterations=2000,seed=0),
            'questions_improved':sum(new[q]>old[q] for q in old),'questions_worsened':sum(new[q]<old[q] for q in old),
            'questions_unchanged':sum(new[q]==old[q] for q in old)}
    strata={}
    for s in sorted({p['stratum'] for p in pages}):
        ids={p['page_id'] for p in pages if p['stratum']==s}
        strata[s]={c:{m:statistics.mean(question_macro([r for r in bycondition[c] if r['page_id'] in ids],m).values()) for m in METRICS} for c in (OLD,NEW)}
    receipts=read(RUN/'page_receipts.json'); success={r['page_id'] for r in receipts if r['status']=='exported'}
    conditional={}
    if len(success)<40:
        for c in (OLD,NEW):
            subset=[r for r in bycondition[c] if r['page_id'] in success]
            conditional[c]={m:statistics.mean(question_macro(subset,m).values()) if subset else None for m in METRICS}
    result=dict(denominators=dict(pages=40,documents=35,questions=125,units=126,gold=159),metrics=results,
        paired_new_minus_old=paired,distributions=distributions,strata=strata,
        failed_pages=[r for r in receipts if r['status']!='exported'],failed_page_rate=(40-len(success))/40,
        successful_pages=len(success),conditional_success_subset=conditional,
        gold_micro_reach={c:statistics.mean(float(r['reachable']) for r in gold_rows if r['condition']==c) for c in (OLD,NEW)},
        aggregation='question_macro_after_mean_selected_units_per_question',partial_multi_page_questions=43,
        score_models_run=False,training=False,ci_role='descriptive_document_bootstrap_not_multiplicity_adjusted')
    return result,unit_rows,gold_rows


def main():
    mode=sys.argv[1]
    if mode=='seal':seal();return
    values=compute()
    for name,value in zip(('metrics.json','unit_metrics.json','gold_reachability.json'),values):
        if mode=='verify':assert value==read(RUN/name)
        else:write_json(RUN/name,value)
    assert 'torch' not in sys.modules
    print(json.dumps(dict(stage=mode,status='passed',metrics=values[0]['metrics'],failures=values[0]['failed_pages'])))


if __name__=='__main__':main()
