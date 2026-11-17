# Local saved-result archiving only. No Python, models, network or new statistics.
$ErrorActionPreference='Stop'
$studyRoot=Split-Path -Parent $PSScriptRoot
$studyDoc=Join-Path $studyRoot 'experiments/parser_candidate_study/supplement_archive_v2'
$studyZip=Join-Path $studyRoot 'artifacts/parser_candidate_comparison/v1/archives/parser_candidate_supplement_v2.zip'
function J([string]$p){Get-Content -LiteralPath $p -Raw | ConvertFrom-Json -Depth 100}
function Get-StudyHash([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
function Check([bool]$value,[string]$message){if(-not $value){throw $message}}
function P($v){([double]$v*100).ToString('F2',[cultureinfo]::InvariantCulture)}
function Rel([string]$p){[IO.Path]::GetRelativePath($studyRoot,$p).Replace('\','/')}
function Same-Json($a,$b){
 if($null -eq $a -or $null -eq $b){return ($null -eq $a -and $null -eq $b)}
 if($a -is [Collections.IDictionary]){
  if($b -isnot [Collections.IDictionary] -or $a.Count -ne $b.Count){return $false}
  foreach($key in $a.Keys){if(-not $b.Contains($key) -or -not (Same-Json $a[$key] $b[$key])){return $false}}
  return $true
 }
 if($a -is [array]){
  if($b -isnot [array] -or $a.Count -ne $b.Count){return $false}
  for($i=0;$i -lt $a.Count;$i++){if(-not (Same-Json $a[$i] $b[$i])){return $false}}
  return $true
 }
 return ($a -ceq $b)
}
function Write-New([string]$p,[string]$text){
 if(Test-Path -LiteralPath $p){
  $saved=[IO.File]::ReadAllText($p)
  if([IO.Path]::GetExtension($p) -eq '.json'){
   Check (Same-Json ($saved | ConvertFrom-Json -AsHashtable -Depth 100) ($text | ConvertFrom-Json -AsHashtable -Depth 100)) "Existing JSON data differ: $p"
  }else{Check ($saved -ceq ($text+"`n")) "Existing archive material differs: $p"}
  return # Preserve exact completed text from an interrupted packaging attempt.
 }
 $stream=[IO.File]::Open($p,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
 try{$bytes=[Text.UTF8Encoding]::new($false).GetBytes($text+"`n");$stream.Write($bytes,0,$bytes.Length)}finally{$stream.Dispose()}
}
function Verify-Entries($entries){foreach($e in $entries){Check ((Get-StudyHash (Join-Path $studyRoot $e.path)) -eq $e.sha256) "Sealed file changed: $($e.path)"}}
Check (-not (Test-Path $studyZip)) 'Archive exists; preserve it'
foreach($name in @('archive_manifest.json','archive_receipt.json')){Check (-not (Test-Path "$studyDoc/$name")) "Archive output already exists: $name"}
$oldDoc=Join-Path $studyRoot 'experiments/parser_candidate_study/v1/archive_v1'
$candDoc=Join-Path $studyRoot 'experiments/parser_candidate_study/deepseek_ocr2_candidates_v1/results'
$scoreDoc=Join-Path $studyRoot 'experiments/parser_candidate_study/deepseek_ocr2_scoring_v1/results'
$candRun=Join-Path $studyRoot 'runs/parser_candidate_comparison/deepseek_ocr2_candidates_v1/candidate_20261116_02'
$scoreRun=Join-Path $studyRoot 'runs/parser_candidate_comparison/v1/frozen_scoring/deepseek_score_02'
$oldManifest=J "$oldDoc/archive_manifest.json"
$oldReceipt=J "$oldDoc/archive_receipt.json"
$candidateManifest=J "$candDoc/artifact_manifest.json"
$scoreManifest=J "$scoreDoc/archive_manifest.json"
Verify-Entries $oldManifest.included_files
Verify-Entries $candidateManifest.files
Verify-Entries $scoreManifest.files
Check ((Get-StudyHash "$oldDoc/archive_manifest.json") -eq $oldReceipt.manifest_sha256) 'Old manifest changed'
Check ((Get-StudyHash "$studyRoot/$($oldReceipt.archive_path)") -eq $oldReceipt.archive_sha256) 'Old review ZIP changed'
$candValidation=J "$candDoc/final_validation.json"
foreach($e in $candValidation.report_files){Check ((Get-StudyHash "$candDoc/$($e.name)") -eq $e.sha256) 'Candidate report changed'}
$verification=J "$scoreRun/verification.json"
Check ($verification.status -eq 'passed' -and $verification.fresh_forward_P_prime_exact -eq 240 -and $verification.historical_baseline_rows_exact -eq 630) 'Missing exact replay evidence'
$identity=J "$scoreRun/identity.json"
foreach($e in $identity.code_sha256.PSObject.Properties){Check ((Get-StudyHash "$studyRoot/$($e.Name)") -eq $e.Value) "Frozen scoring source changed: $($e.Name)"}
$parserIdentity=J "$candRun/identity.json"
foreach($e in $parserIdentity.code_sha256.PSObject.Properties){Check ((Get-StudyHash "$studyRoot/tools/deepseek_ocr2_candidates_v1/$($e.Name)") -eq $e.Value) 'Frozen parser source changed'}
$derived=@(Get-Content "$scoreRun/derived_manifest.jsonl" | ForEach-Object {$_ | ConvertFrom-Json -Depth 30})
Check ($derived.Count -eq 320 -and $oldManifest.derived_tensors_not_copied.Count -eq 320) 'Derived file count mismatch'
foreach($e in @($derived)+@($oldManifest.derived_tensors_not_copied)){Check ((Get-StudyHash $e.path) -eq $e.sha256) 'Derived tensor changed'}
$branch=git -C $studyRoot branch --show-current
$head=git -C $studyRoot rev-parse HEAD
$tag=git -C $studyRoot rev-parse 'paper-v1.0^{commit}'
Check ($branch -eq 'experiment/parser-candidate-study' -and $head -eq '02693ee908aec8a12ef53b3492892f84cf588499' -and $tag -eq $head) 'Git baseline changed'
git -C $studyRoot diff --exit-code HEAD -- src scripts/run_route_v2_external.py pyproject.toml uv.lock
Check ($LASTEXITCODE -eq 0) 'Frozen tracked code changed'
$original='C:/Users/WenJing/Documents/WorkTransfer/layoutpatch'
git -C $original diff --exit-code HEAD -- pyproject.toml uv.lock
Check ($LASTEXITCODE -eq 0) 'Original dependencies changed'

$candidate=J "$candRun/metrics.json"
$score=J "$scoreRun/metrics.json"
$prior=J "$oldDoc/numerical_summary.json"
Check (($score.denominators | ConvertTo-Json -Compress) -eq ($prior.denominators | ConvertTo-Json -Compress)) 'Historical denominator differs'
foreach($method in @('A','B','D-no-text_seed_0','D-no-text_seed_1','D-no-text_seed_2')){
 foreach($metric in @('hit1@0.5','cov@5','gold_recall@5@0.5')){Check ($score.summary.mineru_top_v1.$method.$metric -eq $prior.scoring.mineru_top_v1.$method.$metric) 'Shared baseline differs'}
}
$numbers=[ordered]@{schema='parser-candidate-supplement-v2';scale='fractions_0_to_1_except_counts';denominators=$score.denominators;deepseek_candidate=$candidate;deepseek_scoring=$score;mineru_subannotations_previous=$prior;no_new_statistics=$true;source_sha256=@{candidate_metrics=(Get-StudyHash "$candRun/metrics.json");scoring_metrics=(Get-StudyHash "$scoreRun/metrics.json");prior_summary=(Get-StudyHash "$oldDoc/numerical_summary.json")}}
Write-New "$studyDoc/numerical_summary.json" ($numbers | ConvertTo-Json -Depth 80)
$lines=[Collections.Generic.List[string]]::new()
$lines.Add('# 补充实验完整数值表')
$lines.Add('')
$lines.Add('从冻结JSON直接格式化，不重新计算预测或bootstrap。问题宏平均；百分数，差值/区间单位为百分点；D-no-text均值及ddof=1标准差。原始精度与全部八层结果见numerical_summary.json及同包原RESULTS.md。')
$lines.Add('')
$lines.Add('## 三个条件（共用原基线，非新的三方检验）')
$lines.Add('')
$lines.Add('| 条件 | Oracle | A Top-1 | B Top-1 | D-no-text Top-1 |')
$lines.Add('|---|---:|---:|---:|---:|')
$lines.Add("| MinerU顶层 | $(P $candidate.metrics.mineru_top_v1.'oracle@0.5') | $(P $score.summary.mineru_top_v1.A.'hit1@0.5') | $(P $score.summary.mineru_top_v1.B.'hit1@0.5') | $(P $score.summary.mineru_top_v1.'D-no-text'.'hit1@0.5'.mean) |")
$lines.Add("| MinerU顶层+子注释 | $(P $prior.candidate_reachability.mineru_top_plus_annotations_v1.'oracle@0.5') | $(P $prior.scoring.mineru_top_plus_annotations_v1.A.'hit1@0.5') | $(P $prior.scoring.mineru_top_plus_annotations_v1.B.'hit1@0.5') | $(P $prior.scoring.mineru_top_plus_annotations_v1.'D-no-text'.'hit1@0.5'.mean) |")
$lines.Add("| DeepSeek grounding v2 | $(P $candidate.metrics.deepseek_ocr2_grounding_v2.'oracle@0.5') | $(P $score.summary.deepseek_ocr2_grounding_v2.A.'hit1@0.5') | $(P $score.summary.deepseek_ocr2_grounding_v2.B.'hit1@0.5') | $(P $score.summary.deepseek_ocr2_grounding_v2.'D-no-text'.'hit1@0.5'.mean) |")
$lines.Add('')
$lines.Add('## DeepSeek候选可达性')
$lines.Add('')
$lines.Add('| 指标 | 原顶层 | DeepSeek | Δ | 95%描述区间 | 改善/退步/不变题数 |')
$lines.Add('|---|---:|---:|---:|---|---|')
foreach($e in $candidate.metrics.mineru_top_v1.PSObject.Properties){
 $key=$e.Name;$p=$candidate.paired_new_minus_old.$key
 $lines.Add("| $key | $(P $e.Value) | $(P $candidate.metrics.deepseek_ocr2_grounding_v2.$key) | $(P $p.mean_diff) | [$(P $p.ci95_low), $(P $p.ci95_high)] | $($p.questions_improved)/$($p.questions_worsened)/$($p.questions_unchanged) |")
}
$lines.Add('')
$lines.Add('## DeepSeek排序：全部方法及seed')
$lines.Add('')
$lines.Add('| 方法 | 指标 | 原顶层 | DeepSeek | Δ | 原/新seed标准差 |')
$lines.Add('|---|---|---:|---:|---:|---|')
foreach($method in @('A','B','D-no-text_seed_0','D-no-text_seed_1','D-no-text_seed_2','D-no-text')){
 foreach($metric in @('hit1@0.5','cov@5','gold_recall@5@0.5')){
  $a=$score.summary.mineru_top_v1.$method.$metric;$b=$score.summary.deepseek_ocr2_grounding_v2.$method.$metric;$sd='不适用'
  if($method -eq 'D-no-text'){$sd="$(P $a.std_ddof1)/$(P $b.std_ddof1)";$a=$a.mean;$b=$b.mean}
  $lines.Add("| $method | $metric | $(P $a) | $(P $b) | $(P ($b-$a)) | $sd |")
 }
}
$lines.Add('')
$lines.Add('## DeepSeek全部九个配对比较')
$lines.Add('')
$lines.Add('35文档cluster bootstrap、2000次、seed0；D先同题内平均三seed。Top-1调整只针对本轮三方法，不覆盖两轮全部比较或次要指标。')
$lines.Add('')
$lines.Add('| 方法 | 指标 | Δ | 95%描述区间 | Top-1调整98.3333%区间 | 改善/退步/不变 |')
$lines.Add('|---|---|---:|---|---|---|')
foreach($method in @('A','B','D-no-text')){foreach($metric in @('hit1@0.5','cov@5','gold_recall@5@0.5')){
 $p=$score.paired.$method.$metric;$adjust='不适用'
 if($metric -eq 'hit1@0.5'){$adjust="[$(P $p.bonferroni_ci_low), $(P $p.bonferroni_ci_high)]"}
 $lines.Add("| $method | $metric | $(P $p.mean_diff) | [$(P $p.ci95_low), $(P $p.ci95_high)] | $adjust | $($p.improved)/$($p.worsened)/$($p.unchanged) |")
}}
$lines.Add('')
$lines.Add('原MinerU子注释的完整逐seed和区间表未改写，见同包prior RESULTS_TABLES.md。所有八层结果完整保留于JSON；DeepSeek评分RESULTS.md含八层×三方法可读表。本文不新增跨解析器直接检验。')
Write-New "$studyDoc/RESULTS_TABLES.md" ($lines -join "`n")

$files=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$excluded=[Collections.Generic.List[object]]::new()
function Include-File([string]$path){
 $file=Get-Item -LiteralPath $path
 $relative=Rel $file.FullName
 Check (-not $relative.StartsWith('..')) 'Outside workspace inclusion rejected'
 if($file.Extension -in @('.png','.jpg','.jpeg','.pdf','.pt','.safetensors')){
  $excluded.Add(@{path=$relative;bytes=$file.Length;sha256=(Get-StudyHash $file.FullName);reason='large_media_or_tensor_reference_only';verification='sha256_checked_this_archive'})
 }else{[void]$files.Add($file.FullName)}
}
foreach($folder in @(
 'experiments/parser_candidate_study/supplement_archive_v2',
 'experiments/parser_candidate_study/deepseek_ocr2_candidates_v1',
 'experiments/parser_candidate_study/deepseek_ocr2_scoring_v1',
 'experiments/parser_candidate_study/deepseek_ocr2_smoke_v1/environment',
 'experiments/parser_candidate_study/deepseek_ocr2_smoke_v1/model_download',
 'runs/parser_candidate_comparison/deepseek_ocr2_candidates_v1/candidate_20261116_01',
 'runs/parser_candidate_comparison/deepseek_ocr2_candidates_v1/candidate_20261116_02',
 'runs/parser_candidate_comparison/v1/frozen_scoring/deepseek_score_01',
 'runs/parser_candidate_comparison/v1/frozen_scoring/deepseek_score_02',
 'artifacts/parser_candidate_comparison/deepseek_ocr2_candidates_v1/raw/candidate_20261116_02',
 'tools/deepseek_ocr2_candidates_v1')){
 foreach($f in Get-ChildItem -LiteralPath "$studyRoot/$folder" -File -Recurse){Include-File $f.FullName}
}
foreach($e in $identity.code_sha256.PSObject.Properties){Include-File "$studyRoot/$($e.Name)"}
foreach($relative in @(
 'experiments/parser_candidate_study/v1/sample_pages.jsonl','experiments/parser_candidate_study/v1/sample_units.jsonl',
 'experiments/parser_candidate_study/v1/PROTOCOL.md','experiments/parser_candidate_study/v1/preparation_identity.json',
 'experiments/parser_candidate_study/v1/archive_v1/MANUSCRIPT_SUPPLEMENT_ZH.md',
 'experiments/parser_candidate_study/v1/archive_v1/RESULTS_TABLES.md',
 'experiments/parser_candidate_study/v1/archive_v1/numerical_summary.json',
 'experiments/parser_candidate_study/v1/archive_v1/archive_manifest.json',
 'experiments/parser_candidate_study/v1/archive_v1/archive_receipt.json',
 'configs/experiments/deepseek_ocr2_frozen_scoring_v1.yaml',
 'scripts/run_deepseek_ocr2_candidates.ps1','scripts/audit_deepseek_ocr2_candidates.ps1',
 'scripts/verify_deepseek_ocr2_candidate_results.ps1','scripts/summarize_deepseek_ocr2_candidates.ps1',
 'scripts/run_deepseek_ocr2_frozen_scoring.ps1','scripts/run_deepseek_ocr2_frozen_scoring.py',
 'scripts/summarize_deepseek_ocr2_scoring.ps1','scripts/test_deepseek_ocr2_scoring.py',
 'scripts/archive_parser_candidate_supplement_v2.ps1',$oldReceipt.archive_path)) {Include-File "$studyRoot/$relative"}
$oldCandidate=$identity.bindings.candidate_outputs.mineru_top_v1.path
if(-not [IO.Path]::IsPathRooted($oldCandidate)){$oldCandidate=Join-Path $studyRoot $oldCandidate}
Include-File $oldCandidate
$included=@($files | Sort-Object | ForEach-Object {@{path=(Rel $_);bytes=(Get-Item -LiteralPath $_).Length;sha256=(Get-StudyHash $_)}})
$modelIntegrity=J "$studyRoot/experiments/parser_candidate_study/deepseek_ocr2_smoke_v1/model_download/file_integrity.json"
$manifest=[ordered]@{
 schema='parser-candidate-paper-review-v2';created_at=(Get-Date -Format o);branch=$branch;baseline_commit=$head;paper_tag_commit=$tag;
 valid_runs=@('stage2_20261116_02','stage3_20261116_04','candidate_20261116_02','deepseek_score_02');included_files=$included;
 prior_archive_sha256=$oldReceipt.archive_sha256;old_archive_verified_files=$oldManifest.included_files.Count;
 deepseek_candidates_verified_files=$candidateManifest.files.Count;deepseek_scoring_verified_files=$scoreManifest.files.Count;
 exact_replay_evidence_from_previous_turn=$verification;new_model_execution=$false;new_metric_computation=$false;
 derived_not_copied=@{deepseek=$derived;mineru_previous=$oldManifest.derived_tensors_not_copied;verification='640 hashes checked this archive; no tensor forward executed'};
 media_not_copied=$excluded;
 original_resources_not_copied=@{root=$original;verification='historical_only; original large P/Q/model/image files not rehashed this archive';page_manifest='experiments/parser_candidate_study/v1/sample_pages.jsonl';P_Q_checkpoint_bindings=$identity.bindings;model_file_identity=$modelIntegrity;environment='experiments/parser_candidate_study/deepseek_ocr2_smoke_v1/environment/requirements.lock.txt'};
 limitations=@('review package, not standalone runtime','source text and absolute local paths included; local use only, not published','no new training, parser inference or scoring','checkpoint and image identities preserved from prior successful validation','main manuscript not edited; citation keys and table numbers require integration');
 self_hash_policy='manifest embedded in ZIP; final ZIP hash stored in external receipt'
}
$manifestPath="$studyDoc/archive_manifest.json"
Write-New $manifestPath ($manifest | ConvertTo-Json -Depth 90)
[IO.Directory]::CreateDirectory((Split-Path -Parent $studyZip)) | Out-Null
$zipStream=[IO.File]::Open($studyZip,[IO.FileMode]::CreateNew,[IO.FileAccess]::ReadWrite)
$zip=[IO.Compression.ZipArchive]::new($zipStream,[IO.Compression.ZipArchiveMode]::Create,$false)
try{
 foreach($e in $included){[IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip,"$studyRoot/$($e.path)",$e.path,[IO.Compression.CompressionLevel]::Optimal) | Out-Null}
 [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip,$manifestPath,(Rel $manifestPath),[IO.Compression.CompressionLevel]::Optimal) | Out-Null
}finally{$zip.Dispose();$zipStream.Dispose()}
$expected=@{};foreach($e in $included){$expected[$e.path]=$e.sha256};$expected[(Rel $manifestPath)]=Get-StudyHash $manifestPath
$zip=[IO.Compression.ZipFile]::OpenRead($studyZip)
try{
 Check ($zip.Entries.Count -eq $expected.Count) 'ZIP entry count differs'
 foreach($e in $zip.Entries){
  $stream=$e.Open();$hasher=[Security.Cryptography.SHA256]::Create()
  try{$actual=[Convert]::ToHexString($hasher.ComputeHash($stream)).ToLowerInvariant()}finally{$stream.Dispose();$hasher.Dispose()}
  Check ($expected.ContainsKey($e.FullName) -and $actual -eq $expected[$e.FullName]) "ZIP verification mismatch: $($e.FullName)"
 }
}finally{$zip.Dispose()}
$receipt=[ordered]@{status='verified';created_at=(Get-Date -Format o);archive_path=(Rel $studyZip);archive_sha256=(Get-StudyHash $studyZip);archive_bytes=(Get-Item $studyZip).Length;zip_entries_verified=$expected.Count;manifest_sha256=(Get-StudyHash $manifestPath);old_files_verified=$oldManifest.included_files.Count;candidate_files_verified=$candidateManifest.files.Count;scoring_files_verified=$scoreManifest.files.Count;derived_hashes_verified=640;new_parser_inference=$false;new_scoring=$false;new_training=$false;original_data_copied=$false;git_commit_created=$false;remote_push=$false;paper_tag_unchanged=$true}
Write-New "$studyDoc/archive_receipt.json" ($receipt | ConvertTo-Json -Depth 10)
$receipt | ConvertTo-Json -Depth 10
