"""Read-only full-input preparation, no model imports; run in the existing container."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path, PureWindowsPath
import sys

sys.path.insert(0, '/workspace/scripts')
from prepare_parser_candidate_study import BINDINGS, PREP, ENC, stratum
from layoutpatch.datasets.parser_candidates import validate_candidates

SOURCE=Path('/source'); OUT=Path('/plan')
WINDOWS=PureWindowsPath('C:/Users/WenJing/Documents/WorkTransfer/layoutpatch')
REV='aaa02f3811945a91062062994c5c4a3f4c0af2b0'

def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def lines(p):
    with Path(p).open(encoding='utf-8-sig') as f:return [json.loads(s) for s in f if s.strip()]
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def put(name,value):
    with (OUT/name).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def putlines(name,rows):
    with (OUT/name).open('x',encoding='utf-8',newline='\n') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
def win(relative):return str(WINDOWS / relative)
def rel(value):
    p=PureWindowsPath(value)
    return (p.relative_to(WINDOWS) if p.is_absolute() else p).as_posix()
def checked(relative,digest):
    path=SOURCE/rel(relative)
    assert path.resolve().is_relative_to(SOURCE)
    assert sha(path)==digest, str(path)
    return path

def main():
    for path,digest in BINDINGS.items():checked(path,digest)
    enc=read(SOURCE/ENC/'manifest.json')
    flat=lines(SOURCE/PREP/'candidates.jsonl');groups=defaultdict(list)
    for row in flat:groups[row['page_id']].append(row)
    assert len(flat)==9746 and len(groups)==837
    records={r['page_id']:r for r in enc['pages']}
    assert set(records)==set(groups)
    pages=[]; parser=[]; source_checks=[]
    for i,pid in enumerate(sorted(groups)):
        rec=records[pid];rp=f'{PREP}/{pid}_receipt.json';r=read(SOURCE/rp)
        assert r['status']=='passed' and r['page_id']==pid
        assert rel(r['image']['path'])==rel(rec['image_path']) and r['image']['sha256']==rec['image_sha256']
        for path,digest in [(rec['image_path'],rec['image_sha256']),
                            (f"{ENC}/{rec['file']}",rec['sha256']),
                            (r['render']['render_path'],r['render']['render_sha256'])]:
            checked(path,digest);source_checks.append(dict(path=path,sha256=digest))
        source_checks.append(dict(path=rp,sha256=sha(SOURCE/rp)))
        rows=sorted(groups[pid],key=lambda c:c['layout_id']);size=r['render']['page_size']
        validate_candidates(rows,pid,size)
        pages.append(dict(sample_order=i,page_id=pid,doc_id=r['doc_id'],stratum=stratum(rows),
            page_number=r['page_number'],pdf_page_index=r['pdf_page_index'],old_candidate_count=len(rows),
            evaluation_page_size=size,parser_image_path=win(rec['image_path']),
            parser_image_sha256=rec['image_sha256'],parser_image_size=r['image']['mapping']['source_image_size'],
            render_path=win(r['render']['render_path']),receipt_path=win(rp),
            page_cache_path=win(f"{ENC}/{rec['file']}"),page_cache_sha256=rec['sha256']))
        parser.append(dict(smoke_order=i,page_id=pid,purpose='full_candidate_generation_page_only',
            effect_evaluation_enabled=False,question_answer_gold_provided=False,
            parser_input=dict(image_path=win(rec['image_path']),sha256=rec['image_sha256'],
                size=r['image']['mapping']['source_image_size'],exif_orientation=r['image']['mapping']['source_exif_orientation']),
            evaluation_reference=dict(render_path=win(r['render']['render_path']),sha256=r['render']['render_sha256'],
                page_size=size,pdf_rotation=r['render']['rotation'],mapping_status=r['image']['mapping']['status'],
                receipt_path=win(rp),receipt_sha256=sha(SOURCE/rp),P_sha256=rec['sha256'])))
    qrel=next(p for p in BINDINGS if p.endswith('SciEGQA_Bench.jsonl'))
    annotations=lines(SOURCE/qrel);units=[]
    for idx,row in enumerate(annotations):
        qid=f'sciegqa_{idx:05d}';doc=row['doc_name'].removesuffix('.pdf')
        assert len(row['evidence_page'])==len(row['rel_bbox'])==len(row['subimg_type'])
        for number,boxes,kinds in zip(row['evidence_page'],row['rel_bbox'],row['subimg_type'],strict=True):
            pid=f'{doc}_p{number-1}';w,h=groups[pid][0]['page_size']
            assert len(boxes)==len(kinds) and boxes
            gold=[[b[0]*w/1000,b[1]*h/1000,b[2]*w/1000,b[3]*h/1000] for b in boxes]
            units.append(dict(query_id=qid,doc_id=doc,page_id=pid,unit_id=f'{qid}:{pid}',
                page_size=[w,h],gold_boxes=gold,gold_types=kinds,role='exploratory_full_supplement'))
    assert len(annotations)==1623 and len(units)==1941 and len({u['unit_id'] for u in units})==1941
    assert {u['page_id'] for u in units}==set(groups)
    qr=enc['queries'];checked(f"{ENC}/{qr['file']}",qr['sha256'])
    wm=read(SOURCE/'artifacts/route_v2_external/preparation_v1/20261007_152240/weights.json')['D-no-text']
    assert [x['seed'] for x in wm['weights']]==[0,1,2] and [x['selected_epoch'] for x in wm['weights']]==[1,1,5]
    for weight in wm['weights']:checked(weight['checkpoint'],weight['sha256'])
    checked(wm['config'],wm['config_sha256']);checked(wm['run']+'/checkpoint_selection.json',wm['selection_sha256'])
    reuse=read('/pilot/export_manifest.json')
    for path,digest in reuse['files_sha256'].items():assert sha(Path('/reuse')/path)==digest
    pilot=lines('/pilot/candidates.jsonl');pilot_ids=sorted({r['page_id'] for r in pilot})
    assert len(pilot_ids)==40 and set(pilot_ids)<=set(groups)
    old=[]
    for pid in sorted(groups):
        for row in sorted(groups[pid],key=lambda r:r['layout_id']):
            c=dict(row);c.update(condition_id='mineru_top_v1',source_candidate_id=c['candidate_id'])
            c['candidate_id']='mineru_top_v1:'+c['candidate_id'];old.append(c)
    required=set()
    for s in sorted({p['stratum'] for p in pages}):
        group=[p['page_id'] for p in pages if p['stratum']==s]
        group.sort(key=lambda p:hashlib.sha256(('full-ocr2-visual-v1'+p).encode()).hexdigest())
        required.update(group[:4])
    required.update(r['page_id'] for r in parser if r['evaluation_reference']['pdf_rotation']!=0)
    for name,data in [('full_pages.jsonl',pages),('parser_pages.jsonl',parser),('full_units.jsonl',units),('old_candidates.jsonl',old)]:putlines(name,data)
    put('source_checks.json',source_checks)
    cfg=dict(schema='deepseek-ocr2-full-v1',status='frozen',model_id='deepseek-ai/DeepSeek-OCR-2',revision=REV,
        image_id='sha256:a59f549647c823db086de838a3837056901428f8bea69a1d124f12f78de91b9f',
        pages=837,questions=1623,units=1941,documents=len({p['doc_id'] for p in pages}),
        gold_boxes=sum(len(u['gold_boxes']) for u in units),old_candidates=9746,
        manifests={n:sha(OUT/n) for n in ['full_pages.jsonl','parser_pages.jsonl','full_units.jsonl','old_candidates.jsonl','source_checks.json']},
        source_bindings=BINDINGS,weights=wm,queries_sha256=qr['sha256'],reuse_pages=pilot_ids,
        reuse_source_run='candidate_20261116_02',reuse_export_sha256=sha('/pilot/export_manifest.json'),
        manifest_sha256=sha(OUT/'parser_pages.jsonl'),export_policy='deepseek-ocr2-grounding-v2',
        interfaces_sha256=sha('/legacy/interfaces.py'),visual_review_required=sorted(required),
        methods=['A','B','D-no-text'],seeds=[0,1,2],checkpoint_epochs=[1,1,5],
        fallback='none',max_attempts_per_page=1,training=False,paper_editing=False,
        phase_limits_seconds=dict(preflight=1800,load=600,page=300,overlay=60),overall_timeout_seconds=86400,
        protocol_sha256=sha(OUT/'PROTOCOL.md'))
    put('config.json',cfg)
    print(json.dumps({k:cfg[k] for k in ['pages','questions','units','documents','gold_boxes','old_candidates']}),flush=True)
    print(json.dumps(dict(status='prepared',new_inference_pages=837-len(pilot_ids),reuse_pages=len(pilot_ids),
        visual_review_pages=len(required),strata=dict(Counter(p['stratum'] for p in pages)),torch_imported='torch' in sys.modules)),flush=True)

if __name__=='__main__':main()
