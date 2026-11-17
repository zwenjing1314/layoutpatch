# Saved-results reporting only. No OCR, model loading or ranking.
$ErrorActionPreference='Stop'
$studyRoot=Split-Path -Parent $PSScriptRoot
$studyRun=Join-Path $studyRoot 'runs/parser_candidate_comparison/deepseek_ocr2_candidates_v1/candidate_20261116_02'
$studyRaw=Join-Path $studyRoot 'artifacts/parser_candidate_comparison/deepseek_ocr2_candidates_v1/raw/candidate_20261116_02'
$studyDoc=Join-Path $studyRoot 'experiments/parser_candidate_study/deepseek_ocr2_candidates_v1/results'
if(Test-Path $studyDoc){throw 'Result report already exists; preserve it'}
function Read-Json([string]$p){Get-Content -LiteralPath $p -Raw | ConvertFrom-Json -Depth 100}
function Hash([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
function Percent($v){([double]$v*100).ToString('F2',[cultureinfo]::InvariantCulture)}
$m=Read-Json "$studyRun/metrics.json"
$supervisor=Read-Json "$studyRun/supervisor.json"
$status=Read-Json "$studyRun/page_status.json"
$seal=Read-Json "$studyRun/export_manifest.json"
if((Hash "$studyRun/candidates.jsonl") -ne $seal.candidates_sha256){throw 'Candidates changed'}
$runtime=@(); $rawLabels=@{}; $unknown=@(); $generation=@()
foreach($item in $status){
 $folder=Join-Path $studyRaw $item.page_id
 if(Test-Path "$folder/runtime.json"){$runtime+=Read-Json "$folder/runtime.json"}
 if(Test-Path "$folder/candidate_audit.json"){
  $audit=Read-Json "$folder/candidate_audit.json"
  foreach($entry in $audit.raw_labels.PSObject.Properties){$rawLabels[$entry.Name]+=$entry.Value}
  $unknown+=@($audit.unknown_labels)
 }
 if(Test-Path "$folder/generation.json"){$generation+=@(Read-Json "$folder/generation.json")}
}
$newRuntime=@($runtime | Where-Object { -not $_.raw_reused })
$load=Read-Json "$studyRun/model_load.json"
$cost=@{new_ocr_pages_with_runtime=$newRuntime.Count;reused_raw_pages=@($runtime | Where-Object raw_reused).Count;new_page_wall_seconds=($newRuntime | Measure-Object page_wall_seconds -Sum).Sum;new_page_min_seconds=($newRuntime | Measure-Object page_wall_seconds -Minimum).Minimum;new_page_max_seconds=($newRuntime | Measure-Object page_wall_seconds -Maximum).Maximum;model_load_seconds=$load.elapsed_seconds;supervisor=$supervisor;peak_allocated_bytes=($runtime.resources | Measure-Object peak_allocated_bytes -Maximum).Maximum;peak_reserved_bytes=($runtime.resources | Measure-Object peak_reserved_bytes -Maximum).Maximum;raw_labels=$rawLabels;unknown_labels=@($unknown | Sort-Object -Unique);total_recorded_new_tokens=($generation | Measure-Object new_tokens -Sum).Sum;max_new_tokens_observed=($generation | Measure-Object new_tokens -Maximum).Maximum}
New-Item -ItemType Directory -Path $studyDoc -ErrorAction Stop | Out-Null
$cost | ConvertTo-Json -Depth 12 | Set-Content "$studyDoc/resources_and_labels.json" -Encoding utf8
$lines=[Collections.Generic.List[string]]::new()
$lines.Add('# 固定40页 DeepSeek 候选可达性审计')
$lines.Add('')
$lines.Add('## Material Passport')
$lines.Add('')
$lines.Add('- Origin Skill: academic-research-suite / experiment-agent；inline run + validate。')
$lines.Add('- Origin Date: 2026-11-16；Version Label: deepseek_ocr2_candidates_v1。')
$lines.Add('- Verification Status: VERIFIED 仅指保存候选的几何指标精确重算；OCR仅执行一次，未验证跨运行GPU逐token复现。')
$lines.Add('')
$lines.Add('独立条件 deepseek_ocr2_grounding_v2 vs 原 MinerU 顶层候选。解析前固定 figure_title→text，其余映射沿用；未知类型保留UNK。没有按gold调框、拼接、筛选或选映射。模型固定revision aaa02f3811945a91062062994c5c4a3f4c0af2b0，BF16，原1024/768/crop及8192上限/ngram35。')
$lines.Add('')
$lines.Add('40页、35文档、125问题、126题页单元、159 gold；原8层各5页。两张额外旋转诊断页未纳入。前2页复用四页试跑中身份完全匹配的原始OCR并重新导出，38页新推理；原始输出及原v1候选不改写。原43个多页问题的样本题页并不覆盖其全部页面。')
$lines.Add('')
$lines.Add("成功导出 $($m.successful_pages)/40 页；固定分母失败率 $(Percent $m.failed_page_rate)%。所有失败或未尝试页在主结果中视为空候选，没有旧候选fallback。")
$lines.Add('')
$lines.Add('## 可达性结果')
$lines.Add('')
$lines.Add('单元先在同题内平均，再125题宏平均。数值为百分数；差值和CI为百分点。95%区间按文档成簇配对bootstrap，2000次、seed0，仅探索性描述且未作多指标校正。')
$lines.Add('')
$lines.Add('| 指标 | MinerU顶层 | DeepSeek v2 | Δ | Δ 95% CI | 改善/退步/不变题数 |')
$lines.Add('|---|---:|---:|---:|---|---|')
foreach($key in @('oracle@0.5','independent_gold_reach@0.5','all_gold_reachable_independent@0.5','greedy_all_candidates_gold_recall@0.5')){
 $p=$m.paired_new_minus_old.$key
 $lines.Add("| $key | $(Percent $m.metrics.mineru_top_v1.$key) | $(Percent $m.metrics.deepseek_ocr2_grounding_v2.$key) | $(Percent $p.mean_diff) | [$(Percent $p.ci95_low), $(Percent $p.ci95_high)] | $($p.questions_improved)/$($p.questions_worsened)/$($p.questions_unchanged) |")
}
$lines.Add('')
$lines.Add('Oracle为至少一个gold有候选IoU≥0.5。independent指标允许一个候选命中多个gold；greedy指标沿用已有IoU降序、索引打破平局的一对一贪心，不是最大匹配，不是Gold Recall@5。未运行候选排序，不能把这些值称为Top-1收益。')
$lines.Add("159个gold的独立可达微平均：MinerU $(Percent $m.gold_micro_reach.mineru_top_v1)%；DeepSeek $(Percent $m.gold_micro_reach.deepseek_ocr2_grounding_v2)%。它与题宏平均口径不同。")
$lines.Add('')
$lines.Add('## 候选和资源')
$lines.Add('')
$lines.Add('| 条件 | 总候选 | 每页最小/中位/最大 | 面积比例中位/p95 |')
$lines.Add('|---|---:|---|---|')
foreach($c in @('mineru_top_v1','deepseek_ocr2_grounding_v2')){
 $d=$m.distributions.$c
 $lines.Add("| $c | $($d.candidate_count) | $($d.counts_per_page.min)/$($d.counts_per_page.p50)/$($d.counts_per_page.max) | $(Percent $d.area_fraction.p50)% / $(Percent $d.area_fraction.p95)% |")
}
$lines.Add('')
$lines.Add("新推理累计页面处理秒：$($cost.new_page_wall_seconds)；单页范围 $($cost.new_page_min_seconds)–$($cost.new_page_max_seconds)；模型加载 $($cost.model_load_seconds) 秒。复用两页不纳入新OCR速度。完整资源和原始标签计数见 resources_and_labels.json。GPU总使用含其他程序，不能当作模型独占；采样不是瞬时精确峰值。")
$lines.Add('')
$lines.Add('所有40页无gold叠图总览，并对8层首个样本检查完整图。审核记录绑定封存清单hash；数值指标在审核后才读取gold。原始schema错误、越界、空框、重复框、未知类型记录保留，未作自动修复。输入8页存在<0.18评价像素的DPI取整差异，要求历史内容对齐检查全部通过，且差异≤1评价像素。')
$lines.Add('')
$lines.Add('## 完整分层结果')
$lines.Add('')
$lines.Add('所有8层结果保留于 metrics.json.strata；各层5页，仅描述。若报告共同成功子集，其结果在 conditional_success_subset 中，条件性分母另列；不得替代固定40页主结果。')
$lines.Add('')
$lines.Add('## 解释与限制')
$lines.Add('')
$lines.Add('本轮只回答候选可达性，没有重新编码ColPali、重建模型P′、运行A/B/D-no-text评分或训练。框、类型、数量和文本同时变化，不能把差异归于单一“更细粒度”。所有四指标都报告，不选择最优阈值、parser或seed。SciEGQA为已有分析后的探索性补充评价，不能称为未见确认测试。')
$lines.Add('')
$lines.Add('首次candidate_20261116_01因Windows命令行过长停止在启动前；26项测试已通过且没有模型加载/推理。candidate_20261116_02使用等价Compose文件挂载120个只读页面文件，不改变实验条件，不重试已解析页面。')
$lines.Add('')
$lines.Add('### 统计解释核查（11/11项已检查，非全部有适用统计检验）')
$lines.Add('')
$lines.Add('1. Simpson：8层完整保留，分层方向不外推为统一机制；详细方向见结果补充解释。2. 生态谬误：只报告所选题页/问题聚合，不推断个体或全部SciEGQA。3. 选择偏差：固定分层探索性样本，不代表随机总体。4. Collider：主结果不以解析成功筛选；成功子集仅条件性。5. 基率：保留40/125/126/159分母及旧基线。6. 回归均值：未按旧失败挑样本。7. 幸存者偏差：失败/未尝试保留为0。8. 多重寻找：4指标全报，区间无确认性显著宣称。9. 分析分叉：映射和阈值推理前固定，唯一基础设施修复留痕。10. 因果：整套候选条件改变，不能归因于D或粒度。11. 反向因果：非因果分析，不建立方向性社会/行为机制。')
$lines.Add('')
$lines.Add('## 文件')
$lines.Add('')
$lines.Add('主运行 runs/parser_candidate_comparison/deepseek_ocr2_candidates_v1/candidate_20261116_02/；raw及叠图 artifacts/parser_candidate_comparison/deepseek_ocr2_candidates_v1/raw/candidate_20261116_02/。候选聚合文件在主运行 candidates.jsonl，其hash由 export_manifest.json 固定。完整原始文件未搬走；本目录仅复制审阅用JSON/日志，不复制模型或原图。')
$lines.Add('')
$lines.Add('生成入口 scripts/run_deepseek_ocr2_candidates.ps1；审计入口 scripts/audit_deepseek_ocr2_candidates.ps1（seal→人工无gold核查→metrics→verify）。不推送、不合并、不改变paper-v1.0。下一步是否值得冻结评分，应依据本轮完整结果另行决定，不自动执行。')
[IO.File]::WriteAllText((Join-Path $studyDoc 'RESULTS.md'),($lines -join "`n")+"`n",[Text.UTF8Encoding]::new($false))
foreach($name in @('metrics.json','unit_metrics.json','gold_reachability.json','identity.json','config.json','page_receipts.json','export_manifest.json','visual_review.json','supervisor.json','model_load.json','loading_info.json','interface_tests.log','metric_tests.log','watchdog_tests.log','preflight_before_gpu.json')){Copy-Item -LiteralPath "$studyRun/$name" -Destination "$studyDoc/$name"}
$manifest=@()
foreach($folder in @($studyRun,$studyRaw)){
 foreach($file in Get-ChildItem -LiteralPath $folder -Recurse -File){$manifest+=@{path=[IO.Path]::GetRelativePath($studyRoot,$file.FullName).Replace('\','/');bytes=$file.Length;sha256=(Hash $file.FullName)}}
}
@{files=$manifest;created_at=(Get-Date -Format o);scores_run=$false;training=$false} | ConvertTo-Json -Depth 8 | Set-Content "$studyDoc/artifact_manifest.json" -Encoding utf8
Write-Output "$studyDoc/RESULTS.md"
