param([Parameter(Mandatory=$true)][ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$RunId)
$ErrorActionPreference='Stop'
$studyRoot=Split-Path -Parent $PSScriptRoot
$studyRun=Join-Path $studyRoot "runs/parser_candidate_comparison/deepseek_ocr2_smoke_v1/trial/$RunId"
$studyRaw=Join-Path $studyRoot "artifacts/parser_candidate_comparison/deepseek_ocr2_smoke_v1/raw/$RunId"
if((Test-Path $studyRun) -or (Test-Path $studyRaw)){throw 'Run already exists; no overwrite/retry'}
New-Item -ItemType Directory -Path $studyRun -ErrorAction Stop | Out-Null
New-Item -ItemType Directory -Path "$studyRun/reviews" -ErrorAction Stop | Out-Null
New-Item -ItemType Directory -Path $studyRaw -ErrorAction Stop | Out-Null
$studyTrial=Join-Path $studyRoot 'tools/deepseek_ocr2_trial_v1'
$studyInterfaces=Join-Path $studyRoot 'tools/deepseek_ocr2_interfaces_v1'
$studyPlan=Join-Path $studyRoot 'experiments/parser_candidate_study/deepseek_ocr2_smoke_v1'
$studyModel=Join-Path $studyRoot 'artifacts/parser_candidate_comparison/deepseek_ocr2_smoke_v1/model/aaa02f3811945a91062062994c5c4a3f4c0af2b0'
$studyImage='sha256:a59f549647c823db086de838a3837056901428f8bea69a1d124f12f78de91b9f'
$studyHashes=[ordered]@{}
foreach($studyFile in Get-ChildItem $studyTrial -File){$studyHashes[$studyFile.Name]=(Get-FileHash $studyFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
@{run_id=$RunId;created_at=(Get-Date -Format o);image_id=$studyImage;branch=(git -C $studyRoot branch --show-current);head=(git -C $studyRoot rev-parse HEAD);code_sha256=$studyHashes;script_sha256=(Get-FileHash $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant();manifest_sha256=(Get-FileHash "$studyPlan/pages.jsonl" -Algorithm SHA256).Hash.ToLowerInvariant();environment_lock_sha256=(Get-FileHash "$studyPlan/environment/requirements.lock.txt" -Algorithm SHA256).Hash.ToLowerInvariant();fixed_revision='aaa02f3811945a91062062994c5c4a3f4c0af2b0';model_load_dtype='bfloat16';network='none';training=$false;effect_evaluation=$false;manual_visual_gate_each_page=$true} | ConvertTo-Json -Depth 8 | Set-Content "$studyRun/identity.json" -Encoding utf8
docker run --rm --pull=never --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m --mount "type=bind,source=$studyTrial,target=/trial,readonly" --entrypoint python $studyImage -B /trial/test_supervisor.py 2>&1 | Tee-Object "$studyRun/watchdog_tests.log"
if($LASTEXITCODE -ne 0){throw 'Watchdog tests failed; inference not started'}
$studyArgs=@('run','--rm','--pull=never','--name',"layoutpatch-ocr2-$RunId",'--network','none','--gpus','all','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=1g','--env','HF_HOME=/tmp/hf','--env','HF_HUB_OFFLINE=1','--env','TRANSFORMERS_OFFLINE=1','--env','HF_HUB_DISABLE_IMPLICIT_TOKEN=1','--env','PYTHONDONTWRITEBYTECODE=1','--env','CUDA_VISIBLE_DEVICES=0','--mount',"type=bind,source=$studyTrial,target=/trial,readonly",'--mount',"type=bind,source=$studyInterfaces,target=/interfaces,readonly",'--mount',"type=bind,source=$studyModel,target=/snapshot,readonly",'--mount',"type=bind,source=$studyPlan/pages.jsonl,target=/plan/pages.jsonl,readonly",'--mount',"type=bind,source=$studyPlan/model_download/file_integrity.json,target=/evidence/file_integrity.json,readonly",'--mount',"type=bind,source=$studyPlan/interfaces/identity.json,target=/evidence/interface_identity.json,readonly",'--mount',"type=bind,source=$studyRun,target=/run",'--mount',"type=bind,source=$studyRaw,target=/raw")
# Mount only the twelve named page inputs, renders and receipts; never the source repository.
$studyOriginal='C:\Users\WenJing\Documents\WorkTransfer\layoutpatch\'
foreach($studyLine in Get-Content "$studyPlan/pages.jsonl"){
    $studyPage=$studyLine | ConvertFrom-Json
    foreach($studySource in @($studyPage.parser_input.image_path,$studyPage.evaluation_reference.render_path,$studyPage.evaluation_reference.receipt_path)){
        if(-not $studySource.StartsWith($studyOriginal,[StringComparison]::OrdinalIgnoreCase)){throw 'Source outside original project'}
        $studyRelative=$studySource.Substring($studyOriginal.Length).Replace('\','/')
        if($studyRelative.Contains('..')){throw 'Invalid input path'}
        $studyArgs+=@('--mount',"type=bind,source=$studySource,target=/source/$studyRelative,readonly")
    }
}
$studyArgs+=@('--entrypoint','python',$studyImage,'-B','-u','/trial/supervisor.py')
docker @studyArgs 2>&1 | Tee-Object "$studyRun/supervisor.log"
if($LASTEXITCODE -ne 0){throw 'Trial stopped; inspect receipts. No automatic retry.'}
