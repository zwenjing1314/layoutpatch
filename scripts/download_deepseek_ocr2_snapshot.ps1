param([ValidateSet('download','verify')][string]$Stage='download')
$ErrorActionPreference='Stop'
$studyRoot=Split-Path -Parent $PSScriptRoot
$studyModel=Join-Path $studyRoot 'artifacts/parser_candidate_comparison/deepseek_ocr2_smoke_v1/model/aaa02f3811945a91062062994c5c4a3f4c0af2b0'
$studyRun=Join-Path $studyRoot 'runs/parser_candidate_comparison/deepseek_ocr2_smoke_v1/model_download/download_20261116_03'
$studyTool=Join-Path $studyRoot 'tools/deepseek_ocr2_download_v1'
$studyPrior=Join-Path $studyRoot 'experiments/parser_candidate_study/v1'
$studyImage='sha256:a59f549647c823db086de838a3837056901428f8bea69a1d124f12f78de91b9f'
if($Stage -eq 'download' -and ((Test-Path (Join-Path $studyRun 'download_identity.json')) -or (Test-Path (Join-Path $studyRun 'transport_identity.json')))){throw 'Download attempt already recorded; preserve evidence before resuming'}
$studyArgs=@('run','--rm','--pull=never','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=256m','--name',"layoutpatch-ocr2-model-$Stage",'--env','HF_HUB_OFFLINE=0','--env','HF_HUB_DISABLE_IMPLICIT_TOKEN=1','--env','HF_HUB_DISABLE_XET=1','--env','HF_HOME=/tmp/hf','--env','HF_HUB_DOWNLOAD_TIMEOUT=180','--env','HF_HUB_ETAG_TIMEOUT=30','--mount',"type=bind,source=$studyTool,target=/tool,readonly",'--mount',"type=bind,source=$studyPrior,target=/prior,readonly",'--mount',"type=bind,source=$studyRun,target=/receipt")
if($Stage -eq 'verify'){$studyArgs+=@('--network','none','--mount',"type=bind,source=$studyModel,target=/snapshot,readonly")}else{$studyArgs+=@('--mount',"type=bind,source=$studyModel,target=/snapshot")}
$studyArgs+=@('--entrypoint','python',$studyImage,'-u','/tool/download_and_verify.py')
if($Stage -eq 'verify'){$studyArgs+='--verify-only'}
if($Stage -eq 'download') {
    $studySegmentArgs = @($studyArgs)
    $studySegmentArgs[$studySegmentArgs.Count-1]='/tool/segmented_download.py'
    docker @studySegmentArgs 2>&1 | Tee-Object -FilePath (Join-Path $studyRun 'segmented_download.log')
    if($LASTEXITCODE -ne 0){throw 'Segmented download failed; preserve chunks and logs'}
}
docker @studyArgs 2>&1 | Tee-Object -FilePath (Join-Path $studyRun "$Stage.log")
if($LASTEXITCODE -ne 0){throw "Model $Stage failed; preserve logs and partial downloads"}

