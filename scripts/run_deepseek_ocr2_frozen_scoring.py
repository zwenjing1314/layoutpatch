"""New sealed candidate binding, reusing the unchanged fixed40 scoring engine."""
import argparse
import json
from pathlib import Path

import run_parser_candidate_study as s

CONFIG = s.ROOT / 'configs/experiments/deepseek_ocr2_frozen_scoring_v1.yaml'
CONDITIONS = ('mineru_top_v1', 'deepseek_ocr2_grounding_v2')


def validate_new_candidates(flat, pages):
    grouped = {p['page_id']: [] for p in pages}
    for row in flat:
        s.require(row['condition_id'] == CONDITIONS[1], 'new condition mismatch')
        s.require(row['policy'] == 'deepseek-ocr2-grounding-v2', 'export policy mismatch')
        s.require(row['page_id'] in grouped, 'unexpected candidate page')
        grouped[row['page_id']].append(row)
    from layoutpatch.layout.schema import TYPE_TO_ID
    for page in pages:
        rows = grouped[page['page_id']]
        rows.sort(key=lambda r: r['layout_id'])
        s.validate_candidates(rows, page['page_id'], page['evaluation_page_size'])
        for row in rows:
            s.require(row['type_id'] == TYPE_TO_ID[row['type']], 'node type ID mismatch')
            if row['source']['raw_label'] == 'figure_title':
                s.require(row['type'] == 'text' and row['type_id'] == 1, 'figure_title map mismatch')
    return grouped


def prepare():
    # Call historical loader under its ORIGINAL configuration and condition globals.
    # Every old identity/denominator/checkpoint check remains active.
    cfg = s.yaml.safe_load(CONFIG.read_text('utf-8-sig'))
    s.require(s.sha256(Path(s.__file__)) == cfg['reused_runner_sha256'], 'historical runner changed')
    original = s.load_inputs()
    old_cfg, pages, units, old_candidates, patches, queries, models, bindings = original
    for key in ('status', 'methods', 'seeds', 'checkpoint_epochs', 'device', 'training',
                'new_parser_inference', 'fallback', 'bootstrap_iterations', 'bootstrap_seed', 'family_size'):
        s.require(cfg[key] == old_cfg[key], f'frozen scoring parameter changed: {key}')
    s.require(tuple(cfg['conditions']) == CONDITIONS, 'wrong comparison')
    run = s.ROOT / cfg['candidate_run']
    seal = s.read_json(s.checked(run, 'export_manifest.json', cfg['export_manifest_sha256']))
    validation = s.read_json(s.checked(s.ROOT, cfg['candidate_validation'], cfg['candidate_validation_sha256']))
    s.require(validation['status'] == 'passed' and validation['pages'] == 40 and validation['truncated_pages'] == 0,
              'candidate acceptance missing')
    for entry in validation['report_files']:
        s.checked((s.ROOT / cfg['candidate_validation']).parent, entry['name'], entry['sha256'])
    # The archived manifest includes raw OCR, parser receipts, overlays and sealed metrics.
    archive = s.read_json((s.ROOT / cfg['candidate_validation']).parent / 'artifact_manifest.json')
    for entry in archive['files']:
        s.checked(s.ROOT, entry['path'], entry['sha256'])
    s.require(seal['candidates_sha256'] == cfg['candidate_sha256'], 'candidate seal changed')
    flat = s.read_jsonl(s.checked(run, 'candidates.jsonl', cfg['candidate_sha256']))
    s.require(len(flat) == seal['candidate_count'] == 500, 'candidate count changed')
    receipts = s.read_json(s.checked(run, 'page_receipts.json', seal['receipts_sha256']))
    s.require([r['page_id'] for r in receipts] == [p['page_id'] for p in pages], 'fixed pages changed')
    s.require(all(r['status'] == 'exported' for r in receipts), 'audited page status changed')
    candidates = {CONDITIONS[0]: old_candidates[CONDITIONS[0]],
                  CONDITIONS[1]: validate_new_candidates(flat, pages)}
    new_record = dict(path=(run / 'candidates.jsonl').relative_to(s.ROOT).as_posix(),
                      sha256=cfg['candidate_sha256'], count=500)
    bindings['candidate_outputs'] = {CONDITIONS[0]: bindings['candidate_outputs'][CONDITIONS[0]],
                                     CONDITIONS[1]: new_record}
    bindings['deepseek_candidate_validation_sha256'] = cfg['candidate_validation_sha256']
    bindings['deepseek_export_manifest_sha256'] = cfg['export_manifest_sha256']
    bindings['scoring_protocol_sha256'] = s.sha256(s.ROOT / cfg['protocol'])
    # Score from the sealed geometry, never from old region scores or old P-prime.
    return cfg, pages, units, candidates, patches, queries, models, bindings


def verify_forward_and_baseline(inputs, out):
    cfg, pages, units, candidates, patches, queries, models, bindings = inputs
    count = 0
    with s.torch.inference_mode():
        for record in s.read_jsonl(out / 'derived_manifest.jsonl'):
            identity = record['identity']
            if identity['checkpoint_sha256'] == 'geometry':
                continue
            seed = next(w['seed'] for w in bindings['weights']['weights']
                        if w['sha256'] == identity['checkpoint_sha256'])
            rows = candidates[identity['condition']][identity['page_id']]
            layout = s.page_layout(rows, s.torch.zeros(len(rows), 1024))
            p = patches[identity['page_id']].to(cfg['device'])
            fresh = (models[seed].to(cfg['device'])(p, {k:v.to(cfg['device']) for k,v in layout.items()})
                     if rows else p.clone()).cpu()
            saved = s.torch.load(s.checked(s.ROOT, record['path'], record['sha256']),
                                 weights_only=True, map_location='cpu')
            s.require(s.torch.equal(fresh, saved['P_prime']), 'fresh forward P-prime mismatch')
            count += 1
    s.require(count == 240, 'incomplete forward verification')
    old = s.read_jsonl(s.checked(s.ROOT, cfg['baseline_predictions'], cfg['baseline_predictions_sha256']))
    current = s.read_jsonl(out / 'predictions.jsonl')
    old = [p for p in old if p['condition'] == CONDITIONS[0]]
    current_old = [p for p in current if p['condition'] == CONDITIONS[0]]
    s.require(len(old) == 630 and old == current_old, 'historical baseline predictions changed')
    oracle = s.read_json(s.ROOT / cfg['candidate_run'] / 'metrics.json')['metrics']
    for condition in CONDITIONS:
        for label in s.LABELS:
            rows = [p for p in current if p['condition'] == condition and p['method'] == label]
            value = s.statistics.mean(s.question_macro(rows, 'oracle@0.5').values())
            s.require(value == oracle[condition]['oracle@0.5'], 'scoring candidates differ from oracle audit')
    result = dict(status='passed',fresh_forward_P_prime_exact=count,historical_baseline_rows_exact=630,
                  geometry_score_rank_metric_replay_exact=True,oracle_audit_matches=True,
                  predictions=1260,derived_files=320,training=False,parser_inference=False)
    s.write_json(out / 'verification.json', result)
    print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['score','verify','preflight'], required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--write-broker', action='store_true')
    args = parser.parse_args()
    s.require(args.run_id.startswith('deepseek_score_') and args.run_id.replace('_','').isalnum(), 'isolated run ID required')
    if args.write_broker:
        s.enable_write_broker()
    inputs = prepare()
    if args.stage == 'preflight':
        print(json.dumps(dict(status='passed',stage='preflight',pages=len(inputs[1]),units=len(inputs[2]),
              seeds=list(inputs[6]),cuda=s.torch.cuda.is_available(),torch=s.torch.__version__,
              protocol_sha256=inputs[7]['scoring_protocol_sha256'])),flush=True)
        return
    # Bind the unchanged generic execution and analysis functions AFTER legacy validation.
    s.CONFIG = CONFIG
    s.CONDITIONS = CONDITIONS
    s.load_inputs = lambda: inputs
    original_code_files = s.code_files
    def code_files():
        files = original_code_files()
        for relative in ('scripts/run_deepseek_ocr2_frozen_scoring.ps1',
                         'scripts/test_deepseek_ocr2_scoring.py',inputs[0]['protocol']):
            files[relative] = s.sha256(s.ROOT / relative)
        return files
    s.code_files = code_files
    out = s.ROOT / 'runs/parser_candidate_comparison/v1/frozen_scoring' / args.run_id
    try:
        s.execute(args.run_id, verify=args.stage == 'verify')
        if args.stage == 'verify':
            verify_forward_and_baseline(inputs, out)
    except Exception as exc:
        if args.stage == 'score' and not (out / 'completed.json').exists() and not (out / 'failed.json').exists():
            s.write_json(out / 'failed.json',dict(status='invalid',error_type=type(exc).__name__,message=str(exc)))
        raise


if __name__ == '__main__':
    main()
