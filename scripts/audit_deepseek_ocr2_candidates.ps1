param([ValidateSet('seal','metrics','verify')][Parameter(Mandatory=$true)][string]$Stage)
$ErrorActionPreference='Stop'
$studyRoot=Split-Path -Parent $PSScriptRoot
$studyRun=Join-Path $studyRoot 'runs/parser_candidate_comparison/deepseek_ocr2_candidates_v1/candidate_20261116_02'
$studyRaw=Join-Path $studyRoot 'artifacts/parser_candidate_comparison/deepseek_ocr2_candidates_v1/raw/candidate_20261116_02'
$studyTool=Join-Path $studyRoot 'tools/deepseek_ocr2_candidates_v1'
$studyConfig=Join-Path $studyRoot 'experiments/parser_candidate_study/deepseek_ocr2_candidates_v1'
$studyIdentity=Get-Content "$studyRun/identity.json" -Raw | ConvertFrom-Json
foreach($entry in $studyIdentity.code_sha256.PSObject.Properties){if((Get-FileHash "$studyTool/$($entry.Name)" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value){throw 'Frozen parser/audit code changed'}}
if((Get-FileHash "$studyConfig/config.json" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $studyIdentity.config_sha256){throw 'Frozen config changed'}
if($Stage -eq 'seal' -and -not (Test-Path "$studyRun/supervisor.json")){throw 'Generation not finished'}
$studyArgs=@('run','--rm','--pull=never','--network','none','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=64m','--mount',"type=bind,source=$studyTool,target=/trial,readonly",'--mount',"type=bind,source=$studyRoot/scripts,target=/workspace/scripts,readonly",'--mount',"type=bind,source=$studyRoot/src,target=/workspace/src,readonly",'--mount',"type=bind,source=$studyRun,target=/run",'--mount',"type=bind,source=$studyRaw,target=/raw,readonly",'--mount',"type=bind,source=$studyRoot/experiments/parser_candidate_study/v1/sample_pages.jsonl,target=/eval/sample_pages.jsonl,readonly")
if($Stage -ne 'seal'){
    $studyArgs+=@('--mount',"type=bind,source=$studyRoot/experiments/parser_candidate_study/v1/sample_units.jsonl,target=/eval/sample_units.jsonl,readonly",'--mount',"type=bind,source=$studyRoot/artifacts/parser_candidate_comparison/v1/candidates/mineru_top_v1/stage2_20261116_02/candidates.jsonl,target=/eval/old_candidates.jsonl,readonly")
}
$studyArgs+=@('--entrypoint','python','sha256:a59f549647c823db086de838a3837056901428f8bea69a1d124f12f78de91b9f','-B','/trial/audit.py',$Stage)
docker @studyArgs 2>&1 | Tee-Object "$studyRun/audit_$Stage.log"
if($LASTEXITCODE -ne 0){throw 'Candidate audit failed; preserve existing outputs'}
