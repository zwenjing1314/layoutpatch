param([ValidateSet('initialize','verify')][string]$Stage='verify')
$ErrorActionPreference='Stop'
$studyRoot=Split-Path -Parent $PSScriptRoot
$studyModel=Join-Path $studyRoot 'artifacts/parser_candidate_comparison/deepseek_ocr2_smoke_v1/model/aaa02f3811945a91062062994c5c4a3f4c0af2b0'
$studyRun=Join-Path $studyRoot 'runs/parser_candidate_comparison/deepseek_ocr2_smoke_v1/model_download/offline_20261116_01'
$studyTool=Join-Path $studyRoot 'tools/deepseek_ocr2_download_v1'
$studyPrior=Join-Path $studyRoot 'experiments/parser_candidate_study/v1'
$studyImage='sha256:a59f549647c823db086de838a3837056901428f8bea69a1d124f12f78de91b9f'
if($Stage -eq 'initialize' -and (Test-Path "$studyRun/verification_identity.json")){throw 'Offline initialization already recorded'}
$studyMode=if($Stage -eq 'initialize'){'--offline-initialize'}else{'--verify-only'}
docker run --rm --pull=never --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m --env HF_HUB_OFFLINE=1 --env HF_HUB_DISABLE_IMPLICIT_TOKEN=1 --mount "type=bind,source=$studyTool,target=/tool,readonly" --mount "type=bind,source=$studyPrior,target=/prior,readonly" --mount "type=bind,source=$studyModel,target=/snapshot,readonly" --mount "type=bind,source=$studyRun,target=/receipt" --entrypoint python $studyImage -u /tool/download_and_verify.py $studyMode 2>&1 | Tee-Object -FilePath "$studyRun/$Stage.log"
if($LASTEXITCODE -ne 0){throw 'Offline model integrity verification failed'}
