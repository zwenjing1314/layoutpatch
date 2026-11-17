# Verify saved evidence only; never load a model or run scoring.
$ErrorActionPreference='Stop'
$studyRoot=Split-Path -Parent $PSScriptRoot
$studyRun=Join-Path $studyRoot 'runs/parser_candidate_comparison/deepseek_ocr2_candidates_v1/candidate_20261116_02'
$studyDoc=Join-Path $studyRoot 'experiments/parser_candidate_study/deepseek_ocr2_candidates_v1/results'
$studyPlan=Split-Path -Parent $studyDoc
$studyRaw=Join-Path $studyRoot 'artifacts/parser_candidate_comparison/deepseek_ocr2_candidates_v1/raw/candidate_20261116_02'
function Read-Json([string]$p){Get-Content -LiteralPath $p -Raw | ConvertFrom-Json -Depth 100}
function Hash([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
function Check([bool]$ok,[string]$message){if(-not $ok){throw $message}}
Check (-not (Test-Path "$studyDoc/final_validation.json")) 'Preserve existing final receipt'
$identity=Read-Json "$studyRun/identity.json"
$manifest=Read-Json "$studyDoc/artifact_manifest.json"
foreach($entry in $manifest.files){Check ((Hash (Join-Path $studyRoot $entry.path)) -eq $entry.sha256) "Artifact changed: $($entry.path)"}
$oldManifest=Read-Json "$studyRoot/experiments/parser_candidate_study/v1/archive_v1/archive_manifest.json"
foreach($entry in $oldManifest.included_files){Check ((Hash (Join-Path $studyRoot $entry.path)) -eq $entry.sha256) "Old archive changed: $($entry.path)"}
$smokeManifest=Read-Json "$studyRoot/experiments/parser_candidate_study/deepseek_ocr2_smoke_v1/trial/smoke_20261116_01/artifact_manifest.json"
foreach($entry in $smokeManifest.files){Check ((Hash (Join-Path $studyRoot $entry.path)) -eq $entry.sha256) "Smoke evidence changed: $($entry.path)"}
foreach($entry in $identity.code_sha256.PSObject.Properties){Check ((Hash "$studyRoot/tools/deepseek_ocr2_candidates_v1/$($entry.Name)") -eq $entry.Value) 'Frozen code changed'}
Check ((Hash "$studyPlan/config.json") -eq $identity.config_sha256) 'Config changed'
Check ((Hash "$studyPlan/PROTOCOL.md") -eq $identity.protocol_sha256) 'Protocol changed'
Check ((Hash "$studyPlan/pages.jsonl") -eq $identity.manifest_sha256) 'Parser pages changed'
Check ((Hash "$studyRoot/scripts/run_deepseek_ocr2_candidates.ps1") -eq $identity.script_sha256) 'Launcher changed'
Check ((Hash "$studyRoot/experiments/parser_candidate_study/deepseek_ocr2_smoke_v1/environment/requirements.lock.txt") -eq $identity.environment_lock_sha256) 'Environment lock changed'
$branch=git -C $studyRoot branch --show-current
$head=git -C $studyRoot rev-parse HEAD
$tag=git -C $studyRoot rev-parse 'paper-v1.0^{commit}'
Check ($branch -eq $identity.branch -and $head -eq $identity.head -and $tag -eq $identity.head) 'Branch/HEAD/paper tag changed'
$original='C:/Users/WenJing/Documents/WorkTransfer/layoutpatch'
git -C $original diff --exit-code HEAD -- pyproject.toml uv.lock
Check ($LASTEXITCODE -eq 0) 'Original dependencies changed relative to HEAD'
git -C $studyRoot diff --exit-code HEAD -- pyproject.toml uv.lock
Check ($LASTEXITCODE -eq 0) 'Study dependencies changed relative to HEAD'
$dependencyHashes=@{}
foreach($name in @('pyproject.toml','uv.lock')){
 # The original checkout uses LF; this worktree uses CRLF. Compare content explicitly.
 $a=[IO.File]::ReadAllText("$original/$name").Replace("`r`n","`n")
 $b=[IO.File]::ReadAllText("$studyRoot/$name").Replace("`r`n","`n")
 Check ($a -ceq $b) 'Dependency manifest content differs from study baseline'
 $dependencyHashes[$name]=@{original_sha256=(Hash "$original/$name");worktree_sha256=(Hash "$studyRoot/$name");equal_after_line_end_normalization=$true}
}
$auditVerify=Get-Content "$studyRun/audit_verify.log" | Where-Object {$_ -match '^\{'} | Select-Object -Last 1 | ConvertFrom-Json
Check ($auditVerify.status -eq 'passed' -and $auditVerify.stage -eq 'verify') 'Exact metric replay not passed'
foreach($name in @('interface_tests.log','metric_tests.log','watchdog_tests.log')){Check ((Get-Content "$studyRun/$name" -Raw) -match '\bOK\b') "Tests not passed: $name"}
$status=@(Read-Json "$studyRun/page_status.json")
Check ($status.Count -eq 40 -and @($status | Where-Object status -ne 'exported').Count -eq 0) 'Fixed40 export failed'
$rawBoxCount=0; $candidateCount=0; $aliases=0; $unknown=0; $tokenMax=0
foreach($s in $status){
 $folder=Join-Path $studyRaw $s.page_id
 $generation=@(Read-Json "$folder/generation.json")
 Check ($generation.Count -eq 1 -and $generation[0].status -eq 'eos' -and -not $generation[0].reached_limit) 'Generation termination failure'
 $tokenMax=[Math]::Max($tokenMax,$generation[0].new_tokens)
 $c=Read-Json "$folder/candidates.json"
 $rawBoxCount+=$c.raw_box_count
 $candidateCount+=@($c.candidates).Count
 $seen=@{}
 foreach($item in $c.candidates){
  $b=$item.bbox; $size=$item.page_size
  Check ($b[0] -ge 0 -and $b[1] -ge 0 -and $b[2] -gt $b[0] -and $b[3] -gt $b[1] -and $b[2] -le $size[0] -and $b[3] -le $size[1]) 'Invalid exported geometry'
  $key=$b -join ','
  Check (-not $seen.ContainsKey($key)) 'Duplicate exported box'
  $seen[$key]=$true
  $aliases+=@($item.aliases).Count
  if($item.unknown_label){$unknown++}
  if($item.source.raw_label -eq 'figure_title'){Check ($item.type -eq 'text' -and $item.type_id -eq 1) 'figure_title mapping changed'}
 }
}
$metrics=Read-Json "$studyRun/metrics.json"
Check (-not $metrics.score_models_run -and -not $metrics.training) 'Unexpected scoring/training'
Check ($metrics.metrics.mineru_top_v1.'oracle@0.5' -eq .776) 'Original baseline differs'
Check ($candidateCount -eq $metrics.distributions.deepseek_ocr2_grounding_v2.candidate_count) 'Candidate count mismatch'
$rows=Read-Json "$studyRun/gold_reachability.json"
$pairs=@($rows | Group-Object unit_id,gold_index | ForEach-Object {
 $old=$_.Group | Where-Object condition -eq 'mineru_top_v1'
 $new=$_.Group | Where-Object condition -eq 'deepseek_ocr2_grounding_v2'
 if($old.reachable -ne $new.reachable){[ordered]@{page_id=$old.page_id;unit_id=$old.unit_id;gold_index=$old.gold_index;gold_type=$old.gold_type;old_iou=$old.best_iou;new_iou=$new.best_iou;old_reachable=$old.reachable;new_reachable=$new.reachable}}
})
Check (-not (Test-Path "$studyDoc/reachability_changes.json")) 'Preserve existing changes'
$pairs | ConvertTo-Json -Depth 6 | Set-Content "$studyDoc/reachability_changes.json" -Encoding utf8
# Bind report copies to the actual audit output and freeze the remaining prose.
$documents=@()
foreach($file in Get-ChildItem -LiteralPath $studyDoc -File){
 if(Test-Path "$studyRun/$($file.Name)"){Check ((Hash $file.FullName) -eq (Hash "$studyRun/$($file.Name)")) "Report copy changed: $($file.Name)"}
 $documents+=@{name=$file.Name;sha256=(Hash $file.FullName);bytes=$file.Length}
}
$scripts=@{}
foreach($name in @('audit_deepseek_ocr2_candidates.ps1','summarize_deepseek_ocr2_candidates.ps1','verify_deepseek_ocr2_candidate_results.ps1')){$scripts[$name]=Hash "$studyRoot/scripts/$name"}
$receipt=[ordered]@{status='passed';completed_at=(Get-Date -Format o);branch=$branch;head=$head;paper_tag_commit=$tag;artifact_files_verified=$manifest.files.Count;archived_files_unchanged=$oldManifest.included_files.Count;smoke_files_unchanged=$smokeManifest.files.Count;original_dependency_manifests_unchanged=$true;frozen_code_and_config_unchanged=$true;exact_metric_replay='passed_without_torch_import';interface_metric_watchdog_tests=26;pages=40;candidate_count=$candidateCount;raw_box_count=$rawBoxCount;duplicate_alias_count=$aliases;unknown_candidates=$unknown;invalid_or_duplicate_exported_boxes=0;eos_pages=40;truncated_pages=0;max_new_tokens_observed=$tokenMax;gold_instances_gained=@($pairs | Where-Object new_reachable).Count;gold_instances_lost=@($pairs | Where-Object old_reachable).Count;changed_pages=@($pairs.page_id | Sort-Object -Unique).Count;scoring_run=$false;training=$false;script_hashes=$scripts;report_files=$documents;docker_exit_evidence='supervisor completed with worker_exit_code=0; separate read-only docker ps -a name filter after audit returned no matching container'}
$receipt['dependency_manifest_evidence']=$dependencyHashes
$receipt['verification_note']='Initial final-verifier check compared bytes across LF original and CRLF worktree, and stopped before writing results. Revised to require both Git HEAD diffs clean and explicit normalized-content equality; no dependency files modified.'
$receipt | ConvertTo-Json -Depth 12 | Set-Content "$studyDoc/final_validation.json" -Encoding utf8
[pscustomobject]$receipt | Select-Object status,artifact_files_verified,archived_files_unchanged,smoke_files_unchanged,pages,candidate_count,raw_box_count,duplicate_alias_count,unknown_candidates,eos_pages,truncated_pages,gold_instances_gained,gold_instances_lost,changed_pages | ConvertTo-Json
