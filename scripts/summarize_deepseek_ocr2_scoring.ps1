# Archive and describe saved frozen scores; never execute a model.
$ErrorActionPreference='Stop'
$studyRoot=Split-Path -Parent $PSScriptRoot
$studyRun=Join-Path $studyRoot 'runs/parser_candidate_comparison/v1/frozen_scoring/deepseek_score_02'
$studyPlan=Join-Path $studyRoot 'experiments/parser_candidate_study/deepseek_ocr2_scoring_v1'
$studyDoc=Join-Path $studyPlan 'results'
if(Test-Path $studyDoc){throw 'Preserve existing report'}
function Read-Json([string]$p){Get-Content -LiteralPath $p -Raw | ConvertFrom-Json -Depth 100}
function Hash([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
function P($v){([double]$v*100).ToString('F2',[cultureinfo]::InvariantCulture)}
function Check([bool]$value,[string]$message){if(-not $value){throw $message}}
$m=Read-Json "$studyRun/metrics.json"
$v=Read-Json "$studyRun/verification.json"
$identity=Read-Json "$studyRun/identity.json"
$resources=Read-Json "$studyRun/resources.json"
$complete=Read-Json "$studyRun/completed.json"
Check ($v.status -eq 'passed' -and $v.fresh_forward_P_prime_exact -eq 240 -and $v.historical_baseline_rows_exact -eq 630) 'Verification incomplete'
foreach($entry in $complete.files_sha256.PSObject.Properties){Check ((Hash "$studyRun/$($entry.Name)") -eq $entry.Value) 'Completed run changed'}
foreach($entry in $identity.code_sha256.PSObject.Properties){Check ((Hash "$studyRoot/$($entry.Name)") -eq $entry.Value) 'Execution code changed'}
$derived=@(Get-Content "$studyRun/derived_manifest.jsonl" | ForEach-Object {$_ | ConvertFrom-Json})
foreach($entry in $derived){Check ((Hash $entry.path) -eq $entry.sha256) 'Derived tensor changed'}
$oldArchive=Read-Json "$studyRoot/experiments/parser_candidate_study/v1/archive_v1/archive_manifest.json"
foreach($entry in $oldArchive.included_files){Check ((Hash "$studyRoot/$($entry.path)") -eq $entry.sha256) 'Historical archive changed'}
$candidateArchive=Read-Json "$studyRoot/experiments/parser_candidate_study/deepseek_ocr2_candidates_v1/results/artifact_manifest.json"
foreach($entry in $candidateArchive.files){Check ((Hash "$studyRoot/$($entry.path)") -eq $entry.sha256) 'Candidate evidence changed'}
$branch=git -C $studyRoot branch --show-current
$head=git -C $studyRoot rev-parse HEAD
$tag=git -C $studyRoot rev-parse 'paper-v1.0^{commit}'
Check ($branch -eq 'experiment/parser-candidate-study' -and $head -eq '02693ee908aec8a12ef53b3492892f84cf588499' -and $tag -eq $head) 'Git baseline changed'
git -C $studyRoot diff --exit-code HEAD -- src scripts/run_route_v2_external.py pyproject.toml uv.lock
Check ($LASTEXITCODE -eq 0) 'Tracked scoring code or dependencies changed'
$original='C:/Users/WenJing/Documents/WorkTransfer/layoutpatch'
git -C $original diff --exit-code HEAD -- pyproject.toml uv.lock
Check ($LASTEXITCODE -eq 0) 'Original dependency manifests changed'
Check ((Get-Content "$studyPlan/tests.log" -Raw) -match 'Ran 10 tests' -and (Get-Content "$studyPlan/tests.log" -Raw) -match '\bOK\b') 'Tests not passed'
New-Item -ItemType Directory -Path $studyDoc | Out-Null
foreach($name in @('metrics.json','identity.json','completed.json','verification.json','resources.json','question_scores.jsonl','paired_question_changes.jsonl','paired_unit_changes.jsonl')){Copy-Item -LiteralPath "$studyRun/$name" -Destination "$studyDoc/$name"}
$old='mineru_top_v1'; $new='deepseek_ocr2_grounding_v2'
$metrics=@('hit1@0.5','cov@5','gold_recall@5@0.5')
$methods=@('A','B','D-no-text')
$lines=[Collections.Generic.List[string]]::new()
$lines.Add('# 固定40页 DeepSeek候选冻结评分结果')
$lines.Add('')
$lines.Add('## Material Passport')
$lines.Add('')
$lines.Add('- Origin Skill: academic-research-suite / experiment-agent；Mode: run + validate。')
$lines.Add('- Origin Date: 2026-11-16；Version Label: deepseek_ocr2_scoring_v1；有效run: deepseek_score_02。')
$lines.Add('- Verification Status: VERIFIED（全部几何、分数、排名、指标和240份P′精确重算；旧条件630条预测与历史逐值一致）。不代表统计上确认解析器优劣。')
$lines.Add('')
$lines.Add('**结论：可达性的小幅提高没有转化为一致的排序收益。** DeepSeek使B的Top-1提高，A和D-no-text下降；三者Cov@5提高，但Gold Recall@5分别为小幅增加、不变和下降。不能称DeepSeek全面更优，也不能把候选条件变化归因于粒度或D网络收益。')
$lines.Add('')
$lines.Add('## 范围与执行')
$lines.Add('')
$lines.Add('同一40页/35文档/125题/126题页单元/159 gold；两条件各500候选。沿用固定P/Q和原checkpoint，seed0/1/2对应source_val epoch1/1/5；无训练、OCR、BGE-M3编码、阈值搜索或外部最优seed选择。43个多页问题的部分题页在样本中，不能解释为完整问答评价。SciEGQA为探索性补充评价。')
$lines.Add('')
$lines.Add('旧/新两条件合计新建80份布局/IoU文件及240份P′。文本输入为零，类型、空间坐标与关系保留；原P′和候选分数没有作为新评分输入。A为面积排序，B为冻结patch相关性与IoU区域聚合，不是完整Snappy复现。D-no-text为原布局模型文本消融。')
$lines.Add("有效评分耗时 $([math]::Round($resources.total_seconds,2)) 秒（评分引擎与落盘；不含入口前置材料校验、独立复核及前期OCR）；torch $($identity.torch)，$($identity.device)，float32、deterministic、TF32关闭。CUDA分配峰值 $([math]::Round($resources.peak_cuda_allocated_bytes/1MB,2)) MiB，保留峰值 $([math]::Round($resources.peak_cuda_reserved_bytes/1MB,2)) MiB，均非系统总显存。")
$lines.Add('')
$lines.Add('## 主结果')
$lines.Add('')
$lines.Add('单位%，差值为百分点。每题先平均所选题页，再125题宏平均。D-no-text列为三seed均值，不是融合三个模型预测。')
$lines.Add('')
$lines.Add('| 方法 | Top-1 旧→新（Δ） | Cov@5 旧→新（Δ） | Gold Recall@5 旧→新（Δ） |')
$lines.Add('|---|---:|---:|---:|')
foreach($method in $methods){
 $cells=@()
 foreach($metric in $metrics){
  $a=$m.summary.$old.$method.$metric; $b=$m.summary.$new.$method.$metric
  if($method -eq 'D-no-text'){$a=$a.mean;$b=$b.mean}
  $cells+="$(P $a)→$(P $b)（$(P ($b-$a))）"
 }
 $lines.Add("| $method | $($cells -join ' | ') |")
}
$lines.Add('')
$lines.Add('Top-1要求第一候选与任一gold IoU≥0.5；Cov@5为top5候选并集对gold并集的面积覆盖；Gold Recall@5沿用IoU降序一对一贪心匹配，不是独立gold命中、最大二分匹配或全候选召回。Cov提高而Gold Recall下降并不矛盾：覆盖面积增加不保证各完整gold达到IoU阈值。')
$lines.Add('')
$lines.Add('## 三个seed全部结果')
$lines.Add('')
$lines.Add('| seed | epoch | Top-1 旧→新 | Cov@5 旧→新 | Gold Recall@5 旧→新 |')
$lines.Add('|---|---:|---:|---:|---:|')
foreach($seed in 0..2){
 $label="D-no-text_seed_$seed";$cells=@()
 foreach($metric in $metrics){$cells+="$(P $m.summary.$old.$label.$metric)→$(P $m.summary.$new.$label.$metric)"}
 $lines.Add("| $seed | $(@(1,1,5)[$seed]) | $($cells -join ' | ') |")
}
$lines.Add('')
foreach($metric in $metrics){$a=$m.summary.$old.'D-no-text'.$metric;$b=$m.summary.$new.'D-no-text'.$metric;$lines.Add("- $metric 三seed均值±样本标准差：$(P $a.mean)±$(P $a.std_ddof1) → $(P $b.mean)±$(P $b.std_ddof1)。")}
$lines.Add('')
$lines.Add('D-no-text三个seed的Top-1均下降，seed间标准差增加；这描述当前固定checkpoint对候选替换的响应，不能证明某种具体机制，也不能从三seed推出跨数据集稳定性。')
$lines.Add('')
$lines.Add('## 配对变化与区间')
$lines.Add('')
$lines.Add('35文档成簇bootstrap，2000次、seed0。D先在同题内平均三seed，再计算配对变化，不把seed当额外独立样本。全部9个比较保留；95%区间为描述性，未对九个指标组合统一校正。')
$lines.Add('')
$lines.Add('| 方法 | 指标 | Δ | 95%描述区间 | 改善/退步/不变题数 | Top-1三方法Bonferroni区间 |')
$lines.Add('|---|---|---:|---|---|---|')
foreach($method in $methods){foreach($metric in $metrics){
 $p=$m.paired.$method.$metric;$adjusted='不适用'
 if($metric -eq 'hit1@0.5'){$adjusted="[$(P $p.bonferroni_ci_low), $(P $p.bonferroni_ci_high)]"}
 $lines.Add("| $method | $metric | $(P $p.mean_diff) | [$(P $p.ci95_low), $(P $p.ci95_high)] | $($p.improved)/$($p.worsened)/$($p.unchanged) | $adjusted |")
}}
$lines.Add('')
$lines.Add('三方法Top-1的普通及调整区间均跨零：不能确认总体改善或退步，更不能宣称等效。B的Cov@5普通区间为正，但它是多个探索性次要指标之一，不作确认性显著结论。改善题数与退步题数不直接决定均值方向，覆盖指标的变化幅度也起作用。')
$lines.Add('')
$lines.Add('## 全部分层（每层5页）')
$lines.Add('')
$lines.Add('D列为该层三个seed指标均值。层名沿用原抽样定义，two_column_proxy为代理版式；不重新分层。')
$lines.Add('')
$lines.Add('| 分层 | 方法 | Top-1旧→新 | Cov@5旧→新 | Gold Recall@5旧→新 |')
$lines.Add('|---|---|---:|---:|---:|')
foreach($entry in $m.strata.PSObject.Properties){foreach($method in $methods){
 $cells=@()
 foreach($metric in $metrics){
  if($method -eq 'D-no-text'){
   $a=(@(0..2 | ForEach-Object {$entry.Value.$old."D-no-text_seed_$_".$metric}) | Measure-Object -Average).Average
   $b=(@(0..2 | ForEach-Object {$entry.Value.$new."D-no-text_seed_$_".$metric}) | Measure-Object -Average).Average
  }else{$a=$entry.Value.$old.$method.$metric;$b=$entry.Value.$new.$method.$metric}
  $cells+="$(P $a)→$(P $b)"
 }
 $lines.Add("| $($entry.Name) | $method | $($cells -join ' | ') |")
}}
$lines.Add('')
$lines.Add('## 与候选可达性的关系')
$lines.Add('')
$lines.Add('上一轮Oracle77.60%→78.40%、全候选贪心召回74.00%→75.60%。本轮每种方法的Oracle均与上一轮审计完全一致。它们是候选几何可达性；本轮Top-1和top5衡量实际排序。D-no-text的Top-1下降4.80个百分点、Gold Recall@5下降1.07个百分点，因此本轮没有支持“可达性提升能够自动转化为D-no-text收益”。B的Top-1增加4.00个百分点也不能归因于D。')
$lines.Add('')
$lines.Add('可能机制包括节点集合/类型/空间关系变化、patch与框权重变化以及旧训练分布与新候选分布不匹配，但目前只是假设。两条件候选总数相同并不意味着逐页框相同；也不能仅靠指标判定哪种机制主导。原始文本虽变化，D-no-text的实际文本输入始终为零。')
$lines.Add('')
$lines.Add('## 工程记录及验收')
$lines.Add('')
$lines.Add('最初两个sandbox内Python启动检查未进入脚本，已结束；采用此前验证过的沙箱外原环境执行，不安装依赖。run deepseek_score_01在旧40页计算后，因启动脚本白名单哈希前缀13位/实际12位不一致拒绝第一份新候选几何输出；没有新候选评分或汇总结果。修复为从封存完整哈希派生12位前缀，失败run及源码保留。有效run_02完整重算两条件，科学配置无变化，不按效果选择run。')
$lines.Add('')
$lines.Add('10项契约测试通过；1260预测、320派生文件齐全；全几何/分数/排名/指标精确重算，240份P′独立前向完全相等，旧条件630条预测与历史完全一致；无失败页、无零IoU候选哨兵。原归档165文件和候选审计360文件哈希未变。分支experiment/parser-candidate-study及paper-v1.0未改变，未提交、推送或合并。')
$lines.Add('')
$lines.Add('## 解释核查与后续')
$lines.Add('')
$lines.Add('统计解释11/11核查：1分层完整保留，不以总体替代分层；2不从宏平均外推个体或全部SciEGQA；3固定探索性分层样本不代表随机总体；4不按解析成功或结果筛选；5明确分母和旧基线；6非只抽旧失败页；7无静默删页题；8全部方法/指标/seed保留；9协议评分前固定，工程失败留痕；10不能归因于单独粒度或D；11非因果机制研究，不作方向性因果推断。多重比较仅Top-1三方法有额外调整，次要指标保持探索性。')
$lines.Add('')
$lines.Add('建议下一轮唯一主要任务为本补充实验结果归档与论文解释整理：将旧MinerU复用与本DeepSeek替换作为不同条件准确区分，完整呈现正负结果和证据边界。当前结果不足以支持直接扩大解析范围，也不建议为追求正收益临时调映射、阈值、seed或训练模型。')
$lines.Add('')
$lines.Add('执行命令：scripts/run_deepseek_ocr2_frozen_scoring.ps1 -Stage score -RunId deepseek_score_02；独立验证将Stage改为verify（已完成，重复写verification回执会被拒绝，勿覆盖）。原始预测/派生清单位于runs/parser_candidate_comparison/v1/frozen_scoring/deepseek_score_02/。本目录复制小型结果和身份文件，不复制模型、P/Q或派生tensor。')
[IO.File]::WriteAllText("$studyDoc/RESULTS.md",($lines -join "`n")+"`n",[Text.UTF8Encoding]::new($false))
$files=@()
foreach($file in Get-ChildItem -LiteralPath $studyRun -Recurse -File){$files+=@{path=[IO.Path]::GetRelativePath($studyRoot,$file.FullName).Replace('\','/');sha256=(Hash $file.FullName);bytes=$file.Length}}
foreach($entry in $derived){$file=Get-Item -LiteralPath $entry.path;$files+=@{path=[IO.Path]::GetRelativePath($studyRoot,$file.FullName).Replace('\','/');sha256=$entry.sha256;bytes=$file.Length}}
foreach($file in Get-ChildItem -LiteralPath $studyDoc -File){$files+=@{path=[IO.Path]::GetRelativePath($studyRoot,$file.FullName).Replace('\','/');sha256=(Hash $file.FullName);bytes=$file.Length}}
$receipt=[ordered]@{status='passed';created_at=(Get-Date -Format o);valid_run='deepseek_score_02';invalid_attempt='deepseek_score_01';branch=$branch;head=$head;paper_tag_commit=$tag;tests_passed=10;old_archive_files_verified=$oldArchive.included_files.Count;candidate_archive_files_verified=$candidateArchive.files.Count;derived_files_verified=$derived.Count;forward_and_metric_verification=$v;scoring_config_sha256=(Hash "$studyRoot/configs/experiments/deepseek_ocr2_frozen_scoring_v1.yaml");summary_script_sha256=(Hash $PSCommandPath);training=$false;parser_inference=$false;files=$files}
$receipt | ConvertTo-Json -Depth 12 | Set-Content "$studyDoc/archive_manifest.json" -Encoding utf8
Write-Output "$studyDoc/RESULTS.md"
