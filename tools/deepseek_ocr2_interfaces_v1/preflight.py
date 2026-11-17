"""Read-only four-page input check. Never imports or loads an OCR model."""
import json
from pathlib import Path
from interfaces import prepare_page, sha, write_json

manifest=Path('/plan/pages.jsonl')
assert sha(manifest)=='356d3876e428956b923eaa6406213d3b31955c741dabd4269842ade0f07a8279'
rows=[json.loads(line) for line in manifest.read_text().splitlines()]
assert [r['smoke_order'] for r in rows]==list(range(4))
assert len({r['page_id'] for r in rows})==4
results=[]
for row in rows:
    try:
        page=prepare_page(row,'/source')
        results.append(dict(page_id=row['page_id'],input_status='passed',inference_status='not_attempted',page=page))
    except Exception as exc:
        results.append(dict(page_id=row['page_id'],input_status='failed',inference_status='not_attempted',error=str(exc)))
write_json('/receipt/input_preflight.json',dict(status='passed' if all(r['input_status']=='passed' for r in results) else 'failed',
           pages=results,manifest_sha256=sha(manifest),model_loaded=False,inference=False))
print(json.dumps(results,ensure_ascii=False,indent=2))
assert all(r['input_status']=='passed' for r in results)
