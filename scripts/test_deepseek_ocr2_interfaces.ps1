param([Parameter(Mandatory=$true)][ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$RunId)
$ErrorActionPreference='Stop'
$studyRoot=Split-Path -Parent $PSScriptRoot
$studyRun=Join-Path $studyRoot "runs/parser_candidate_comparison/deepseek_ocr2_smoke_v1/interfaces/$RunId"
New-Item -ItemType Directory -Path $studyRun -ErrorAction Stop | Out-Null
$studyTool=Join-Path $studyRoot 'tools/deepseek_ocr2_interfaces_v1'
$studyPlan=Join-Path $studyRoot 'experiments/parser_candidate_study/deepseek_ocr2_smoke_v1'
$studyImage='sha256:a59f549647c823db086de838a3837056901428f8bea69a1d124f12f78de91b9f'
$studyHashes=[ordered]@{}
foreach($studyFile in Get-ChildItem $studyTool -File){$studyHashes[$studyFile.Name]=(Get-FileHash $studyFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
@{image_id=$studyImage;code_sha256=$studyHashes;script_sha256=(Get-FileHash $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant();model_mounted=$false;gpu_enabled=$false;network='none';inference=$false;created_at=(Get-Date -Format o)} | ConvertTo-Json -Depth 8 | Set-Content "$studyRun/identity.json" -Encoding utf8
docker run --rm --pull=never --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m --mount "type=bind,source=$studyTool,target=/tool,readonly" --entrypoint python $studyImage -B /tool/test_interfaces.py 2>&1 | Tee-Object "$studyRun/tests.log"
if($LASTEXITCODE -ne 0){throw 'Interface tests failed'}
docker run --rm --pull=never --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m --mount "type=bind,source=$studyTool,target=/tool,readonly" --mount "type=bind,source=$studyPlan,target=/plan,readonly" --mount 'type=bind,source=C:/Users/WenJing/Documents/WorkTransfer/layoutpatch,target=/source,readonly' --mount "type=bind,source=$studyRun,target=/receipt" --entrypoint python $studyImage -B /tool/preflight.py 2>&1 | Tee-Object "$studyRun/preflight.log"
if($LASTEXITCODE -ne 0){throw 'Page preflight failed'}
$studyResults=[ordered]@{}
foreach($studyName in @('identity.json','tests.log','preflight.log','input_preflight.json')){$studyResults[$studyName]=(Get-FileHash "$studyRun/$studyName" -Algorithm SHA256).Hash.ToLowerInvariant()}
@{status='passed';files_sha256=$studyResults;model_loaded=$false;inference=$false} | ConvertTo-Json -Depth 8 | Set-Content "$studyRun/completed.json" -Encoding utf8
