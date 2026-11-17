"""Read-only independent forward replay of all saved study P-prime tensors."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_parser_candidate_study as s

run = s.ROOT / 'runs/parser_candidate_comparison/v1/frozen_scoring/stage3_20261116_04'
os.environ['TORCHINDUCTOR_CACHE_DIR'] = str(s.ROOT / 'artifacts/parser_candidate_comparison/v1/runtime_cache/torchinductor')
os.environ['CUDA_CACHE_DISABLE'] = '1'
cfg, pages, units, candidates, patches, queries, models, bindings = s.load_inputs()
s.torch.set_num_threads(4)
s.torch.use_deterministic_algorithms(True)
s.torch.backends.cuda.matmul.allow_tf32 = False
s.torch.backends.cudnn.allow_tf32 = False
records = s.read_jsonl(run / 'derived_manifest.jsonl')
count = 0
with s.torch.inference_mode():
    for record in records:
        ident = record['identity']
        if ident['checkpoint_sha256'] == 'geometry':
            continue
        seed = next(w['seed'] for w in bindings['weights']['weights'] if w['sha256'] == ident['checkpoint_sha256'])
        rows = candidates[ident['condition']][ident['page_id']]
        layout = s.page_layout(rows, s.torch.zeros(len(rows), 1024))
        fresh = models[seed].to(cfg['device'])(patches[ident['page_id']].to(cfg['device']), {k:v.to(cfg['device']) for k,v in layout.items()}).cpu()
        saved = s.torch.load(s.checked(s.ROOT, record['path'], record['sha256']), weights_only=True, map_location='cpu')
        s.require(s.torch.equal(fresh, saved['P_prime']), 'forward replay P-prime mismatch')
        count += 1
predictions = s.read_jsonl(run / 'predictions.jsonl')
lookup = {(p['condition'], p['method'], p['unit_id']):p for p in predictions}
unchanged_pages = [p['page_id'] for p in pages if len(candidates[s.CONDITIONS[0]][p['page_id']]) == len(candidates[s.CONDITIONS[1]][p['page_id']])]
for unit in units:
    for label in s.LABELS:
        old, new = (lookup[c,label,unit['unit_id']] for c in s.CONDITIONS)
        oldscores = dict(zip(old['ranked_layout_ids'], old['ranked_scores'], strict=True))
        newscores = dict(zip(new['ranked_layout_ids'], new['ranked_scores'], strict=True))
        if label in ('A','B') or unit['page_id'] in unchanged_pages:
            s.require(all(newscores[i] == score for i,score in oldscores.items()), 'unchanged-input scores changed')
seed_changes = {}
for label in s.LABELS:
    seed_changes[label] = {}
    for metric in s.METRICS:
        ds = [lookup[s.CONDITIONS[1],label,u['unit_id']][metric] - lookup[s.CONDITIONS[0],label,u['unit_id']][metric] for u in units]
        seed_changes[label][metric] = dict(improved=sum(d>0 for d in ds),worsened=sum(d<0 for d in ds),unchanged=sum(d==0 for d in ds))
print(json.dumps(dict(status='passed',forward_replay_exact_P_prime=count,unchanged_pages=len(unchanged_pages),existing_A_B_scores_exact=True,unchanged_page_D_scores_exact=True,unit_changes=seed_changes),indent=2))
