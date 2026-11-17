param([Parameter(Mandatory=$true)][ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$RunId)
$ErrorActionPreference='Stop'
$studyRoot=Split-Path -Parent $PSScriptRoot
$studyRun=Join-Path $studyRoot "runs/parser_candidate_comparison/deepseek_ocr2_candidates_v1/$RunId"
$studyRaw=Join-Path $studyRoot "artifacts/parser_candidate_comparison/deepseek_ocr2_candidates_v1/raw/$RunId"
if((Test-Path $studyRun) -or (Test-Path $studyRaw)){throw 'Run already exists; no overwrite/retry'}
New-Item -ItemType Directory -Path $studyRun -ErrorAction Stop | Out-Null
New-Item -ItemType Directory -Path "$studyRun/reviews" -ErrorAction Stop | Out-Null
New-Item -ItemType Directory -Path $studyRaw -ErrorAction Stop | Out-Null
$studyTrial=Join-Path $studyRoot 'tools/deepseek_ocr2_candidates_v1'
$studyInterfaces=Join-Path $studyRoot 'tools/deepseek_ocr2_candidates_v1'
$studyPlan=Join-Path $studyRoot 'experiments/parser_candidate_study/deepseek_ocr2_candidates_v1'
$studyModel=Join-Path $studyRoot 'artifacts/parser_candidate_comparison/deepseek_ocr2_smoke_v1/model/aaa02f3811945a91062062994c5c4a3f4c0af2b0'
$studyImage='sha256:a59f549647c823db086de838a3837056901428f8bea69a1d124f12f78de91b9f'
$studySmoke=Join-Path $studyRoot 'artifacts/parser_candidate_comparison/deepseek_ocr2_smoke_v1/raw/smoke_20261116_01'
$studySmokeManifest=Get-Content "$studyRoot/experiments/parser_candidate_study/deepseek_ocr2_smoke_v1/trial/smoke_20261116_01/artifact_manifest.json" -Raw | ConvertFrom-Json
foreach($entry in $studySmokeManifest.files){if((Get-FileHash -LiteralPath (Join-Path $studyRoot $entry.path) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256){throw 'Smoke evidence changed; cannot reuse'} }
foreach($studyName in @('config.json','pages.jsonl','PROTOCOL.md')){Copy-Item -LiteralPath "$studyPlan/$studyName" -Destination "$studyRun/$studyName"}
$studyHashes=[ordered]@{}
foreach($studyFile in Get-ChildItem $studyTrial -File){$studyHashes[$studyFile.Name]=(Get-FileHash $studyFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
@{run_id=$RunId;created_at=(Get-Date -Format o);image_id=$studyImage;branch=(git -C $studyRoot branch --show-current);head=(git -C $studyRoot rev-parse HEAD);code_sha256=$studyHashes;script_sha256=(Get-FileHash $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant();manifest_sha256=(Get-FileHash "$studyPlan/pages.jsonl" -Algorithm SHA256).Hash.ToLowerInvariant();environment_lock_sha256=(Get-FileHash "$studyRoot/experiments/parser_candidate_study/deepseek_ocr2_smoke_v1/environment/requirements.lock.txt" -Algorithm SHA256).Hash.ToLowerInvariant();fixed_revision='aaa02f3811945a91062062994c5c4a3f4c0af2b0';model_load_dtype='bfloat16';network='none';training=$false;effect_evaluation=$false;visual_audit_before_metrics=$true;config_sha256=(Get-FileHash "$studyPlan/config.json" -Algorithm SHA256).Hash.ToLowerInvariant();protocol_sha256=(Get-FileHash "$studyPlan/PROTOCOL.md" -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Depth 8 | Set-Content "$studyRun/identity.json" -Encoding utf8
docker run --rm --pull=never --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m --mount "type=bind,source=$studyTrial,target=/trial,readonly" --entrypoint python $studyImage -B /trial/test_supervisor.py 2>&1 | Tee-Object "$studyRun/watchdog_tests.log"
if($LASTEXITCODE -ne 0){throw 'Watchdog tests failed; inference not started'}
docker run --rm --pull=never --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m --mount "type=bind,source=$studyTrial,target=/trial,readonly" --entrypoint python $studyImage -B /trial/test_interfaces.py 2>&1 | Tee-Object "$studyRun/interface_tests.log"
if($LASTEXITCODE -ne 0){throw 'Interface tests failed; inference not started'}
docker run --rm --pull=never --network none --read-only --mount "type=bind,source=$studyTrial,target=/trial,readonly" --mount "type=bind,source=$studyRoot/scripts,target=/workspace/scripts,readonly" --mount "type=bind,source=$studyRoot/src,target=/workspace/src,readonly" --entrypoint python $studyImage -B /trial/test_metrics.py 2>&1 | Tee-Object "$studyRun/metric_tests.log"
if($LASTEXITCODE -ne 0){throw 'Metric definition tests failed; inference not started'}
$studyArgs=@('run','--rm','--pull=never','--name',"layoutpatch-ocr2-$RunId",'--network','none','--gpus','all','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=1g','--env','HF_HOME=/tmp/hf','--env','HF_HUB_OFFLINE=1','--env','TRANSFORMERS_OFFLINE=1','--env','HF_HUB_DISABLE_IMPLICIT_TOKEN=1','--env','PYTHONDONTWRITEBYTECODE=1','--env','CUDA_VISIBLE_DEVICES=0','--mount',"type=bind,source=$studyTrial,target=/trial,readonly",'--mount',"type=bind,source=$studyInterfaces,target=/interfaces,readonly",'--mount',"type=bind,source=$studyModel,target=/snapshot,readonly",'--mount',"type=bind,source=$studyPlan/pages.jsonl,target=/plan/pages.jsonl,readonly",'--mount',"type=bind,source=$studyRoot/experiments/parser_candidate_study/deepseek_ocr2_smoke_v1/model_download/file_integrity.json,target=/evidence/file_integrity.json,readonly",'--mount',"type=bind,source=$studyRoot/experiments/parser_candidate_study/deepseek_ocr2_smoke_v1/interfaces/identity.json,target=/evidence/interface_identity.json,readonly",'--mount',"type=bind,source=$studyRun,target=/run",'--mount',"type=bind,source=$studyRaw,target=/raw")
# Mount only the named page inputs, renders and receipts; never the source repository.
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
$studyArgs+=@('--mount',"type=bind,source=$studyPlan/config.json,target=/plan/config.json,readonly")
foreach($studyReuse in @('2411.08382_p10','2412.17966_p3')){$studyArgs+=@('--mount',"type=bind,source=$studySmoke/$studyReuse,target=/reuse/$studyReuse,readonly")}
# Compose holds the same exact mounts without exceeding Windows command length.
$studyVolumes=@()
$studyEnv=@{}
for($studyIndex=0;$studyIndex -lt $studyArgs.Count;$studyIndex++){
    if($studyArgs[$studyIndex] -eq '--mount'){
        $studySpec=$studyArgs[$studyIndex+1]
        $studyFields=@{}
        foreach($studyPart in $studySpec.Split(',')){if($studyPart.Contains('=')){$studyKey,$studyValue=$studyPart.Split('=',2);$studyFields[$studyKey]=$studyValue}}
        $studyVolumes+=@{type='bind';source=$studyFields.source;target=$studyFields.target;read_only=$studySpec.EndsWith(',readonly')}
    }
    if($studyArgs[$studyIndex] -eq '--env'){$studyKey,$studyValue=$studyArgs[$studyIndex+1].Split('=',2);$studyEnv[$studyKey]=$studyValue}
}
@{services=@{worker=@{image=$studyImage;pull_policy='never';network_mode='none';gpus='all';read_only=$true;tmpfs=@('/tmp:rw,nosuid,nodev,size=1g');environment=$studyEnv;volumes=$studyVolumes;entrypoint=@('python');command=@('-B','-u','/trial/supervisor.py')}}} | ConvertTo-Json -Depth 12 | Set-Content "$studyRun/compose.json" -Encoding utf8
docker compose -p $RunId -f "$studyRun/compose.json" run --rm --no-deps worker -B /trial/preflight.py 2>&1 | Tee-Object "$studyRun/preflight.log"
if($LASTEXITCODE -ne 0){throw 'Preflight failed; inference not started'}
docker compose -p $RunId -f "$studyRun/compose.json" run --rm --no-deps --name "layoutpatch-ocr2-$RunId" worker 2>&1 | Tee-Object "$studyRun/supervisor.log"
if($LASTEXITCODE -ne 0){throw 'Trial stopped; inspect receipts. No automatic retry.'}
