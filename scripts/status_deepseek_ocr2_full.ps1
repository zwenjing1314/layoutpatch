param([Parameter(Mandatory=$false)][ValidatePattern('^full_[a-zA-Z0-9_]+$')][string]$RunId='full_20261117_01')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$run=Join-Path $root "runs/parser_candidate_comparison/deepseek_ocr2_full_v1/$RunId"
if(-not (Test-Path "$run/page_status.json")){throw "Run not found: $RunId"}
$rows=Get-Content "$run/page_status.json" -Raw | ConvertFrom-Json
$done=@($rows | Where-Object status -eq 'exported')
$failed=@($rows | Where-Object {$_.status -notin @('exported','not_attempted','running')})
$state=if(Test-Path "$run/state.json"){Get-Content "$run/state.json" -Raw | ConvertFrom-Json}else{$null}
$pipeline=if(Test-Path "$run/pipeline_state.json"){Get-Content "$run/pipeline_state.json" -Raw | ConvertFrom-Json}else{$null}
$container=docker ps -a --filter "name=layoutpatch-ocr2-$RunId" --format '{{.Names}} | {{.Status}}' 2>$null
if($LASTEXITCODE -ne 0){$container='Docker status unavailable in this shell; file progress is shown below'}
[ordered]@{
 checked_at=(Get-Date -Format o)
 run_id=$RunId
 container=$container
 pipeline_phase=$pipeline.phase
 worker_phase=$state.phase
 worker_page=$state.page_id
 total=$rows.Count
 exported=$done.Count
 new_inference=@($done | Where-Object raw_reused -ne $true).Count
 reused=@($done | Where-Object raw_reused -eq $true).Count
 running=@($rows | Where-Object status -eq 'running' | Select-Object -ExpandProperty page_id)
 pending=@($rows | Where-Object status -eq 'not_attempted').Count
 failed=$failed
 next_step=if(Test-Path "$run/visual_review.json"){'scoring_or_complete'}else{'finish_ocr_then_visual_review'}
} | ConvertTo-Json -Depth 8
