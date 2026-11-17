param(
 [Parameter(Mandatory=$true)][ValidateSet('seal','metrics','verify')][string]$Stage,
 [Parameter(Mandatory=$true)][ValidatePattern('^full_[a-zA-Z0-9_]+$')][string]$RunId
)
$ErrorActionPreference='Stop'
$studyRoot=Split-Path -Parent $PSScriptRoot
$studyRun=Join-Path $studyRoot "runs/parser_candidate_comparison/deepseek_ocr2_full_v1/$RunId"
$studyRaw=Join-Path $studyRoot "artifacts/parser_candidate_comparison/deepseek_ocr2_full_v1/raw/$RunId"
$studyPlan=Join-Path $studyRoot 'experiments/parser_candidate_study/deepseek_ocr2_full_v1'
$studyConfig=Get-Content "$studyPlan/config.json" -Raw | ConvertFrom-Json -Depth 100
$studyIdentity=Get-Content "$studyRun/identity.json" -Raw | ConvertFrom-Json -Depth 100
if((Get-FileHash "$studyPlan/config.json").Hash.ToLowerInvariant() -ne $studyIdentity.config_sha256){throw 'Full protocol binding changed'}
docker run --rm --pull=never --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=256m --mount "type=bind,source=$studyRoot/tools/deepseek_ocr2_full_v1,target=/full,readonly" --mount "type=bind,source=$studyRoot/tools/deepseek_ocr2_candidates_v1,target=/interfaces,readonly" --mount "type=bind,source=$studyRoot/scripts,target=/workspace/scripts,readonly" --mount "type=bind,source=$studyRoot/src,target=/workspace/src,readonly" --mount "type=bind,source=$studyPlan,target=/plan,readonly" --mount "type=bind,source=$studyRaw,target=/raw,readonly" --mount "type=bind,source=$studyRun,target=/run" --entrypoint python $studyConfig.image_id -B /full/audit.py $Stage 2>&1 | Tee-Object "$studyRun/audit_$Stage.log"
if($LASTEXITCODE -ne 0){throw 'Audit did not pass; preserve outputs and investigate'}
