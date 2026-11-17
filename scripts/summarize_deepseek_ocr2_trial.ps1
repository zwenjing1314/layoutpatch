# Read-only result aggregation; no model, page parsing or inference calls.
$ErrorActionPreference='Stop'
$studyRoot=Split-Path -Parent $PSScriptRoot
$studyRun=Join-Path $studyRoot 'runs/parser_candidate_comparison/deepseek_ocr2_smoke_v1/trial/smoke_20261116_01'
$studyRaw=Join-Path $studyRoot 'artifacts/parser_candidate_comparison/deepseek_ocr2_smoke_v1/raw/smoke_20261116_01'
$studyDoc=Join-Path $studyRoot 'experiments/parser_candidate_study/deepseek_ocr2_smoke_v1/trial/smoke_20261116_01'
if(Test-Path "$studyDoc/summary.json"){throw 'Summary already exists; preserve archived evidence'}
function Read-Json([string]$Path){Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -Depth 100}
function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
$studyStatus=Read-Json "$studyRun/page_status.json"
$studySupervisor=Read-Json "$studyRun/supervisor.json"
if($studyStatus.Count -ne 4 -or $studySupervisor.status -ne 'completed'){throw 'Trial incomplete'}
$studyIdentity=Read-Json "$studyRun/identity.json"
foreach($entry in $studyIdentity.code_sha256.PSObject.Properties){if((Hash "$studyRoot/tools/deepseek_ocr2_trial_v1/$($entry.Name)") -ne $entry.Value){throw 'Trial code hash changed'}}
if((Hash "$studyRoot/scripts/run_deepseek_ocr2_trial.ps1") -ne $studyIdentity.script_sha256){throw 'Launcher hash changed'}
New-Item -ItemType Directory -Path $studyDoc -Force | Out-Null
$studyPages=@()
$studyTypes=@{}
foreach($studyItem in $studyStatus){
    $studyId=$studyItem.page_id
    $studyPage=Join-Path $studyRaw $studyId
    $studyReceipt=Read-Json "$studyPage/receipt.json"
    $studyGeneration=@(Read-Json "$studyPage/generation.json")
    $studyAudit=Read-Json "$studyPage/candidate_audit.json"
    $studyRuntime=Read-Json "$studyPage/runtime.json"
    $studyReview=Read-Json "$studyRun/reviews/$studyId.json"
    if($studyItem.status -ne 'passed' -or $studyReceipt.status -ne 'exported' -or -not $studyReview.coordinate_review_passed){throw 'Page not technically passed'}
    if($studyGeneration.Count -ne 1 -or $studyGeneration[0].status -ne 'eos' -or $studyGeneration[0].reached_limit){throw 'Generation incomplete'}
    foreach($pair in @(@('raw.txt',$studyReceipt.raw_sha256),@('candidates.json',$studyReceipt.candidates_sha256),@('overlay.png',$studyReview.overlay_sha256))){if((Hash "$studyPage/$($pair[0])") -ne $pair[1]){throw 'Output hash mismatch'}}
    foreach($entry in $studyAudit.types.PSObject.Properties){$studyTypes[$entry.Name]+=$entry.Value}
    $studyPages+=@{page_id=$studyId;status=$studyItem.status;candidate_count=$studyAudit.candidate_count;raw_box_count=$studyAudit.raw_box_count;types=$studyAudit.types;unknown_labels=$studyAudit.unknown_labels;area_fractions=$studyAudit.area_fractions;input_tokens=$studyGeneration[0].input_tokens;new_tokens=$studyGeneration[0].new_tokens;generation_seconds=$studyGeneration[0].elapsed_seconds;page_wall_seconds=$studyRuntime.page_wall_seconds;termination=$studyGeneration[0].status;resources=$studyRuntime.resources;overlay_sha256=$studyReview.overlay_sha256}
    $studyPageDoc=Join-Path $studyDoc $studyId
    New-Item -ItemType Directory -Path $studyPageDoc -ErrorAction Stop | Out-Null
    foreach($studyName in @('raw.txt','candidates.json','generation.json','receipt.json','runtime.json','candidate_audit.json')){Copy-Item -LiteralPath "$studyPage/$studyName" -Destination "$studyPageDoc/$studyName"}
    Copy-Item -LiteralPath "$studyRun/reviews/$studyId.json" -Destination "$studyPageDoc/visual_review.json"
}
$studyLoad=Read-Json "$studyRun/model_load.json"
$studySummary=[ordered]@{status='four_page_technical_trial_passed_with_recorded_label_and_boundary_limitations';run_id='smoke_20261116_01';model_id='deepseek-ai/DeepSeek-OCR-2';revision=$studyIdentity.fixed_revision;pages_planned=4;pages_attempted=4;pages_passed=4;failed_pages=0;technical_failure_rate=0.0;total_candidates=($studyPages | Measure-Object candidate_count -Sum).Sum;types=$studyTypes;total_page_wall_seconds=($studyPages | Measure-Object page_wall_seconds -Sum).Sum;model_load_seconds=$studyLoad.elapsed_seconds;supervisor=$studySupervisor;pages=$studyPages;gold_used=$false;effect_evaluation=$false;training=$false;parameters_changed=$false;candidate_policy='deepseek-ocr2-grounding-v1';known_index_total_size_discrepancy='official bytes verified; actual load passed';next_task_recommended='freeze schema mapping decision then fixed-40-page candidate generation and reachability audit; not scoring'}
$studySummary | ConvertTo-Json -Depth 20 | Set-Content "$studyDoc/summary.json" -Encoding utf8
foreach($studyName in @('identity.json','model_load.json','loading_info.json','supervisor.json','page_status.json','input_preflight.json','preload_verification.json','preservation_check.json','watchdog_tests.log')){Copy-Item -LiteralPath "$studyRun/$studyName" -Destination "$studyDoc/$studyName"}
$studyFiles=@()
foreach($studyFolder in @($studyRun,$studyRaw)){
    foreach($studyFile in Get-ChildItem -LiteralPath $studyFolder -Recurse -File){$studyFiles+=@{path=[IO.Path]::GetRelativePath($studyRoot,$studyFile.FullName).Replace('\','/');bytes=$studyFile.Length;sha256=(Hash $studyFile.FullName)}}
}
@{run_id='smoke_20261116_01';files=$studyFiles;summary_sha256=(Hash "$studyDoc/summary.json");created_at=(Get-Date -Format o);raw_outputs_preserved=$true;source_data_copied=$false;weights_copied=$false} | ConvertTo-Json -Depth 10 | Set-Content "$studyDoc/artifact_manifest.json" -Encoding utf8
[pscustomobject]$studySummary | Select-Object status,total_candidates,types,total_page_wall_seconds,model_load_seconds | ConvertTo-Json -Depth 5
