"""Post-run offline replay of saved raw strings, never OCR inference."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,'/interfaces')
from interfaces import export_grounding, sha, write_json

statuses=json.loads(Path('/run/page_status.json').read_text())
records=[]
for status in statuses:
    page=Path('/raw')/status['page_id']
    receipt=json.loads((page/'receipt.json').read_text())
    raw=(page/'raw.txt').read_text(encoding='utf-8')
    saved=json.loads((page/'candidates.json').read_text())
    started=time.perf_counter()
    replay=export_grounding(raw,status['page_id'],receipt['page']['page_size'])
    elapsed=time.perf_counter()-started
    assert replay==saved, 'saved export differs from frozen exporter'
    assert sha(page/'raw.txt')==receipt['raw_sha256']==replay['raw_sha256']
    records.append(dict(page_id=status['page_id'],exact_json_equivalence=True,
                        exporter_replay_seconds=elapsed,candidates=len(replay['candidates'])))
write_json('/run/export_replay.json',dict(status='passed',pages=records,inference=False,
    timing_note='post-run export-only replay; not original measured export latency'))
print(json.dumps(records,indent=2))
