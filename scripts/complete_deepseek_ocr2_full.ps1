param(
 [Parameter(Mandatory=$true)][ValidatePattern('^full_[a-zA-Z0-9_]+$')][string]$RunId,
 [Parameter(Mandatory=$true)][ValidatePattern('^full_score_[a-zA-Z0-9_]+$')][string]$ScoreRunId
)
# Local experiment pipeline. No scheduling service, network messages or manuscript writes.
$ErrorActionPreference='Stop'
$studyRoot=Split-Path -Parent $PSScriptRoot
Set-Location $studyRoot
$studyRun=Join-Path $studyRoot "runs/parser_candidate_comparison/deepseek_ocr2_full_v1/$RunId"
$studyState=Join-Path $studyRun 'pipeline_state.json'
$studyStart=Get-Date
function State([string]$phase,[string]$detail=''){
 $value=@{phase=$phase;detail=$detail;updated_at=(Get-Date -Format o);run_id=$RunId;score_run_id=$ScoreRunId;process_id=$PID}
 $tmp="$studyState.tmp";[IO.File]::WriteAllText($tmp,($value | ConvertTo-Json)+"`n",[Text.UTF8Encoding]::new($false))
 Move-Item -LiteralPath $tmp -Destination $studyState -Force
}
function Guard {
 $saved=Get-Content "$studyRun/pipeline_code_identity.json" -Raw | ConvertFrom-Json -Depth 100
 foreach($prop in $saved.PSObject.Properties){if((Get-FileHash -LiteralPath (Join-Path $studyRoot $prop.Name)).Hash.ToLowerInvariant() -ne $prop.Value){throw "Pipeline code changed: $($prop.Name)"}}
}
try {
 Guard;State 'waiting_for_ocr'
 while(-not (Test-Path "$studyRun/supervisor.json")){
  if(((Get-Date)-$studyStart).TotalSeconds -gt 90000){throw 'OCR outcome not available after monitoring limit'}
  Start-Sleep -Seconds 30
 }
 $outcome=Get-Content "$studyRun/supervisor.json" -Raw | ConvertFrom-Json
 if($outcome.status -ne 'completed'){throw "OCR stopped with status $($outcome.status); no retry or scoring"}
 Guard;State 'sealing_candidates'
 & "$PSScriptRoot/audit_deepseek_ocr2_full.ps1" -Stage seal -RunId $RunId
 State 'waiting_for_visual_review' 'Inspect the preregistered full-resolution overlays and anomalies; no gold-based adjustments. Scoring cannot start before a passed review bound to the export hash.'
 while(-not (Test-Path "$studyRun/visual_review.json")){
  if(((Get-Date)-$studyStart).TotalSeconds -gt 172800){throw 'Visual review unavailable; outputs preserved, no scoring'}
  Start-Sleep -Seconds 30
 }
 $review=Get-Content "$studyRun/visual_review.json" -Raw | ConvertFrom-Json
 if($review.status -ne 'passed' -or $review.gold_used -ne $false){throw 'Visual review did not pass'}
 Guard;State 'candidate_metrics'
 & "$PSScriptRoot/audit_deepseek_ocr2_full.ps1" -Stage metrics -RunId $RunId
 & "$PSScriptRoot/audit_deepseek_ocr2_full.ps1" -Stage verify -RunId $RunId
 Guard;State 'scoring_preflight'
 & "$PSScriptRoot/run_deepseek_ocr2_full_scoring.ps1" -Stage preflight -RunId $ScoreRunId -CandidateRunId $RunId
 State 'scoring'
 & "$PSScriptRoot/run_deepseek_ocr2_full_scoring.ps1" -Stage score -RunId $ScoreRunId -CandidateRunId $RunId
 State 'verifying_scores'
 & "$PSScriptRoot/run_deepseek_ocr2_full_scoring.ps1" -Stage verify -RunId $ScoreRunId -CandidateRunId $RunId
 State 'completed' 'Full candidate audit, frozen scoring and replay completed; no manuscript edits.'
}catch{
 State 'stopped' $_.Exception.Message
 throw
}
