import json
from pathlib import Path
from interfaces import prepare_page, sha, write_json, LABELS

cfg=json.loads(Path('/plan/config.json').read_text(encoding='utf-8-sig'))
assert sha('/plan/pages.jsonl')==cfg['manifest_sha256']
rows=[json.loads(s) for s in Path('/plan/pages.jsonl').read_text().splitlines()]
assert len(rows)==40 and [r['smoke_order'] for r in rows]==list(range(40))
records=[]
for row in rows:
    try:
        page=prepare_page(row,'/source')
        records.append(dict(page_id=row['page_id'],status='passed',page=page))
    except Exception as exc:
        records.append(dict(page_id=row['page_id'],status='input_failed',error=str(exc)))
write_json('/run/preflight_before_gpu.json',dict(pages=records,type_mapping=LABELS,gold_read=False,model_loaded=False))
print(json.dumps(dict(pages=len(records),passed=sum(r['status']=='passed' for r in records),
    failures=[r for r in records if r['status']!='passed'])))
# Input failures remain in the run denominator; do not discard or replace pages.
