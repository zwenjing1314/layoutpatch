"""Archive verified full experiment summaries only; never write manuscripts."""
import hashlib
import json
import base64
from pathlib import Path
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'experiments/parser_candidate_study/deepseek_ocr2_full_v1'
OCR = ROOT / 'runs/parser_candidate_comparison/deepseek_ocr2_full_v1/full_20261117_01'
SCORE = ROOT / 'runs/parser_candidate_comparison/v1/full_frozen_scoring/full_score_20261117_01'
OUT = PLAN / 'results/full_20261117_01'
OLD, NEW = 'mineru_top_v1', 'deepseek_ocr2_grounding_v2'
METRICS = ['hit1@0.5', 'cov@5', 'gold_recall@5@0.5']


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def pct(value):
    return f'{value * 100:.2f}'


def interval(row, corrected=False):
    keys = ('bonferroni_ci_low', 'bonferroni_ci_high') if corrected else ('ci95_low', 'ci95_high')
    return f'[{pct(row[keys[0]])}, {pct(row[keys[1]])}]'


def main():
    verification = read(SCORE / 'verification.json')
    assert verification['status'] == 'passed'
    assert verification['prediction_rows_exact'] == 19410
    assert verification['derived_files_exact'] == 6696
    assert verification['historical_baseline']['exact']
    assert read(OCR / 'pipeline_state.json')['phase'] == 'completed'
    assert git('branch', '--show-current') == 'experiment/parser-candidate-study'
    head = git('rev-parse', 'HEAD')
    assert head == git('rev-parse', 'paper-v1.0^{}') == '02693ee908aec8a12ef53b3492892f84cf588499'
    assert not git('diff', '--name-only') and not git('diff', '--cached', '--name-only')
    subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
    for name, digest in read(SCORE / 'completed.json')['files_sha256'].items():
        assert sha(SCORE / name) == digest
    paper_validation = read(ROOT / 'papers/parser-candidate-revision-v1/validation.json')
    for row in paper_validation['files']:
        assert sha(ROOT / row['path']) == row['sha256'], row['path']
    receipt = read(ROOT / 'papers/parser-candidate-revision-v1/integration_receipt.json')
    assert sha(Path(receipt['selected_source'])) == receipt['source_sha256']
    candidate = read(OCR / 'metrics.json')
    scores = read(SCORE / 'metrics.json')
    generation = read(OCR / 'generation_audit.json')
    resources = read(SCORE / 'resources.json')
    supervisor = read(OCR / 'supervisor.json')
    assert candidate['denominators'] == scores['denominators'] == dict(pages=837, documents=80, questions=1623, units=1941, gold_boxes=2497)
    assert generation['eos_pages'] == 837 and generation['truncated_pages'] == 0
    units = [json.loads(line) for line in (PLAN / 'full_units.jsonl').open(encoding='utf-8-sig') if line.strip()]
    failed = {r['page_id'] for r in candidate['failed_pages']}
    affected = [u for u in units if u['page_id'] in failed]
    sources = {
        'candidate_metrics.json': OCR / 'metrics.json',
        'candidate_acceptance.json': OCR / 'candidate_acceptance.json',
        'visual_review.json': OCR / 'visual_review.json',
        'generation_audit.json': OCR / 'generation_audit.json',
        'ocr_supervisor.json': OCR / 'supervisor.json',
        'scoring_metrics.json': SCORE / 'metrics.json',
        'scoring_verification.json': SCORE / 'verification.json',
        'baseline_check.json': SCORE / 'baseline_check.json',
        'scoring_resources.json': SCORE / 'resources.json',
        'scoring_identity.json': SCORE / 'identity.json',
    }
    assert not OUT.exists(), 'Archive already exists; do not overwrite'
    artifacts = {name: source.read_bytes() for name, source in sources.items()}
    rows = [
        '# DeepSeek-OCR-2 全量补充实验记录', '',
        '本文件是实验结果记录，不是论文修订。所有结果在固定规则下产生；未训练、未挑选外部最优 seed、未改类型映射或修框。', '',
        '## 范围与验收', '',
        '- 固定 837 页、80 篇文档、1623 题、1941 个题—页单元、2497 个 gold 实例。',
        '- 原 40 页输出经身份核验后复用，797 页新推理；833 页成功导出，4 页失败（0.478%）。失败页保留为空候选，没有旧框 fallback。',
        f'- 失败页涉及 {len(affected)} 个题页单元、{len({u["query_id"] for u in affected})} 道题；所有单元均保留。',
        '- 837 页均正常生成 EOS，0 页达到 token 上限，最大生成 3583 tokens，上限 8192。四个失败是定位输出格式/坐标错误，不是截断。',
        '- 机器检查覆盖全部页面；无 gold 视觉检查覆盖 63 个成功叠图和 4 个失败页原图/原始文本。未发现系统性坐标变换错误；局部漏框、拆分、裁切照实保留。',
        '- 19410 条预测完整复算一致；6696 份几何/P′派生文件完整复算一致，其中新计算 P′ 5022 份。原条件 9705 条记录的排名、分数与指标和历史全量结果完全一致。',
        '- 当前分支 experiment/parser-candidate-study；HEAD 与 paper-v1.0 均为 ' + head + '。未切换、推送、合并或修改标签。', '',
        '## 候选可达性', '',
        '百分数均先对同题所有证据页取平均，再对 1623 题宏平均；变化单位为百分点。', '',
        '| 指标 | MinerU | DeepSeek-OCR-2 | 新−旧 | 95% 配对区间 |',
        '|---|---:|---:|---:|---|',
    ]
    names = {'oracle@0.5': 'Oracle@0.5', 'independent_gold_reach@0.5': '逐 gold 独立可达率',
             'all_gold_reachable_independent@0.5': '全部 gold 独立可达率',
             'greedy_all_candidates_gold_recall@0.5': '全候选一对一贪心召回'}
    for key, name in names.items():
        pair = candidate['paired_new_minus_old'][key]
        rows.append(f'| {name} | {pct(candidate["metrics"][OLD][key])} | {pct(candidate["metrics"][NEW][key])} | {pct(pair["mean_diff"])} | {interval(pair)} |')
    rows += ['', 'Oracle 表示任一候选能否与任一 gold 达到 IoU≥0.5。独立可达指标允许同一候选对应多个 gold；贪心召回不允许。本次二者数值相同不代表定义相同。', '',
             '候选总数 9746→9222，页候选中位数 11→10，候选面积占页面比例中位数 2.17%→2.39%。因此本次输出不能概括为“候选普遍变细”。未知类型 formula_number 共 110 框、涉及 29 页，按预先固定规则保留 UNK/type_id=0。', '',
             '## 冻结排序结果', '',
             '| 方法 | 旧 Top-1 | 新 Top-1 | 旧 Cov@5 | 新 Cov@5 | 旧 Gold Recall@5 | 新 Gold Recall@5 |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for method in ['A', 'B', 'D-no-text_seed_0', 'D-no-text_seed_1', 'D-no-text_seed_2', 'D-no-text']:
        values = []
        for metric in METRICS:
            for condition in [OLD, NEW]:
                value = scores['summary'][condition][method][metric]
                values.append(pct(value['mean']) + ' ± ' + pct(value['std_ddof1']) if isinstance(value, dict) else pct(value))
        rows.append('| ' + method + ' | ' + ' | '.join(values) + ' |')
    rows += ['', 'D-no-text 汇总为三个 seed 的均值 ± 样本标准差。checkpoint 均按原 source_val 选定：seed 0/1/2 对应 epoch 1/1/5。', '',
             '| 方法 | Top-1 新−旧 | 95% 区间 | Bonferroni 98.3333% 区间 | 改善/变差/不变的题数 |',
             '|---|---:|---|---|---|']
    for method in ['A', 'B', 'D-no-text']:
        pair = scores['paired'][method]['hit1@0.5']
        rows.append(f'| {method} | {pct(pair["mean_diff"])} | {interval(pair)} | {interval(pair, True)} | {pair["improved"]}/{pair["worsened"]}/{pair["unchanged"]} |')
    rows += ['', '按 80 篇文档进行 2000 次配对 bootstrap，随机种子为 0。D-no-text 先在每题内平均三个 seed，再比较新旧。校正仅覆盖本轮 A/B/D-no-text 三项 Top-1 比较；不覆盖此前试验探索。', '',
             '| 方法 | Cov@5 新−旧（95% 区间） | Gold Recall@5 新−旧（95% 区间） |',
             '|---|---|---|']
    for method in ['A', 'B', 'D-no-text']:
        values = [f'{pct(scores["paired"][method][m]["mean_diff"])} {interval(scores["paired"][method][m])}' for m in METRICS[1:]]
        rows.append('| ' + method + ' | ' + ' | '.join(values) + ' |')
    rows += ['', 'Top-1 为首位候选与任一 gold 的 IoU≥0.5；Cov@5 为前五个候选并集覆盖的 gold 并集面积比例（不是命中率）；Gold Recall@5 为前五个候选与 gold 按 IoU 降序进行一对一贪心匹配的召回率。未改为最大匹配。', '',
             '## 解释边界', '',
             '结论是有限、混合的正向结果：D-no-text 三 seed 平均 Top-1 增加 2.75 个百分点，预定 Bonferroni 98.3333% 区间为 [0.42, 5.72] 个百分点，支持该冻结方法在新候选下改善；其新 Top-1 为 33.55%，数值上仍低于新候选面积基线 A 的 34.29%。这不是 D-no-text 对 A 的优势检验。', '',
             'A 的 Top-1 增加 0.49 个百分点但区间跨零；B 增加 2.65 个百分点，普通 95% 区间为正，但校正区间 [-0.22, 5.50] 跨零。三方法 Cov@5 均增加；Gold Recall@5 只有 D-no-text 的普通 95% 区间排除零，次指标仍按探索性解释。', '',
             'D-no-text 三个 seed 的 Top-1 均上升，但幅度不同（约 +4.22、+2.68、+1.36 个百分点），seed 间样本标准差从 0.95 增至 2.22 个百分点。不能用最佳 seed 0 的 36.08% 代替三 seed 汇总。Oracle 仅轻微变化而排序改善，说明净可达性增量不足以直接解释全部排序收益；具体机制未在本实验中独立识别。', '',
             '- 全量 Oracle 的增量很小，95% 区间包含零；不能声称 DeepSeek-OCR-2 明确解决了候选不可达问题，也不能认定 MinerU 顶层粒度是主要瓶颈。',
             '- 候选变更同时改变位置、大小、数量、类型及文本，不能严格归因于粒度。A/B/D-no-text 均不使用新 OCR 文本语义向量；本轮没有运行 BGE-M3 或完整 D。',
             '- 排序收益必须逐方法解释。若某方法提升，只能说明该冻结方法与新候选组合在本集合上更好；不能把候选替换收益全部归因于布局适配器。',
             '- 区间跨零表示当前数据不能排除无改善，不是证明两者完全等效。局部页面可改善也可恶化，所有配对记录均保存。',
             '- SciEGQA 已用于旧结果分析和 40 页先导试验，本次仍为扩大范围的探索性补充评价，不能称为未见确认测试。任务是正确页面给定后的候选排序，不涉及完整检索或答案生成。', '',
             '## 资源与运行方式', '',
             f'- OCR 监控墙钟 {supervisor["elapsed_seconds"] / 3600:.3f} 小时；797 页逐页处理时间之和 {generation["new_page_seconds_sum"] / 3600:.3f} 小时。40 页复用不计入新推理耗时。',
             f'- OCR 进程采样峰值 RSS {supervisor["worker_peak_sampled_rss_bytes"] / 2**30:.2f} GiB；PyTorch 峰值 allocated {generation["max_torch_allocated_bytes"] / 2**30:.2f} GiB、reserved {generation["max_torch_reserved_bytes"] / 2**30:.2f} GiB；系统采样 GPU 总占用峰值 {supervisor["gpu_peak_sampled_total_used_MiB"]} MiB，包含其他进程。',
             f'- 冻结评分阶段记录耗时 {resources["total_seconds"]:.1f} 秒（含派生写盘与结果分析，不含前置输入核查及独立复算）；峰值 RSS {resources["peak_rss_bytes"] / 2**30:.2f} GiB、CUDA allocated {resources["peak_cuda_allocated_bytes"] / 2**30:.2f} GiB。',
             '- OCR 在已固定的 Linux CUDA Docker 镜像中离线运行；本次冻结评分复用原 Windows Python/PyTorch 环境，读取原 ColPali P/Q 与三个 checkpoint。没有重新安装环境或下载模型。', '',
             '## 文件索引与下一步', '',
             '- 本目录保存候选/评分指标、验收、视觉检查、运行身份、资源与历史基线核对的原样副本。archive_manifest.json 记录来源与哈希，不复制大模型或原始数据。',
             '- 原始 OCR：artifacts/parser_candidate_comparison/deepseek_ocr2_full_v1/raw/full_20261117_01/。',
             '- 候选、失败原因及逐 gold 可达性：runs/parser_candidate_comparison/deepseek_ocr2_full_v1/full_20261117_01/。',
             '- 全部预测与逐题/逐单元配对变化：runs/parser_candidate_comparison/v1/full_frozen_scoring/full_score_20261117_01/。',
             '- 派生几何与 P′：artifacts/parser_candidate_comparison/v1/full_derived/full_score_20261117_01/。',
             '- 执行入口：scripts/complete_deepseek_ocr2_full.ps1；候选审计 audit_deepseek_ocr2_full.ps1；评分与复算 run_deepseek_ocr2_full_scoring.ps1/.py。',
             '- 下一步只需审核本次全量结果及解释边界；不自动追加解析器、调参、训练或修改论文。', '']
    artifacts['RESULTS.md'] = '\n'.join(rows).encode('utf-8')
    tracked = list(sources.values()) + [OCR / name for name in ['export_manifest.json', 'page_status.json', 'page_receipts.json', 'candidates.jsonl', 'unit_metrics.json', 'gold_reachability.json', 'pipeline_code_identity.json', 'pipeline_state.json']]
    tracked += [SCORE / name for name in ['completed.json', 'predictions.jsonl', 'derived_manifest.jsonl', 'question_scores.jsonl', 'paired_question_changes.jsonl', 'paired_unit_changes.jsonl']]
    manifest = dict(status='passed', created_at=datetime.now(timezone.utc).isoformat(), branch=git('branch', '--show-current'), head=head,
                    paper_tag_unchanged=True, paper_files_checked=len(paper_validation['files']), manuscript_source_unchanged=True,
                    tracked_code_unchanged=True, training=False, fixed_denominator=True,
                    sources={p.relative_to(ROOT).as_posix(): sha(p) for p in tracked},
                    archive_files={name: hashlib.sha256(data).hexdigest() for name, data in artifacts.items()})
    artifacts['archive_manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    print(json.dumps(dict(status='passed', output=str(OUT), files={name: base64.b64encode(data).decode('ascii') for name, data in artifacts.items()})))


if __name__ == '__main__':
    main()
