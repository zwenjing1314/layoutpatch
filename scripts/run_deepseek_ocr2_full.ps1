param(
 [Parameter(Mandatory=$true)][ValidateSet('prepare','preflight','start','status')][string]$Stage,
 [Parameter(Mandatory=$true)][ValidatePattern('^full_[a-zA-Z0-9_]+$')][string]$RunId
)
$ErrorActionPreference='Stop'
$studyRoot=Split-Path -Parent $PSScriptRoot
$studyPlan=Join-Path $studyRoot 'experiments/parser_candidate_study/deepseek_ocr2_full_v1'
$studyRun=Join-Path $studyRoot "runs/parser_candidate_comparison/deepseek_ocr2_full_v1/$RunId"
$studyRaw=Join-Path $studyRoot "artifacts/parser_candidate_comparison/deepseek_ocr2_full_v1/raw/$RunId"
$studyCfg=Get-Content "$studyPlan/config.json" -Raw | ConvertFrom-Json -Depth 100
$studyImage=$studyCfg.image_id
$studyName="layoutpatch-ocr2-$RunId"
function FileHash([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
function WriteNew([string]$p,$value){$bytes=[Text.UTF8Encoding]::new($false).GetBytes(($value | ConvertTo-Json -Depth 100)+"`n");$f=[IO.File]::Open($p,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write);try{$f.Write($bytes,0,$bytes.Length)}finally{$f.Dispose()}}
function CheckInputs {
 if((git -C $studyRoot branch --show-current) -ne 'experiment/parser-candidate-study'){throw 'Wrong branch'}
 if((FileHash "$studyPlan/PROTOCOL.md") -ne $studyCfg.protocol_sha256){throw 'Protocol changed'}
 foreach($prop in $studyCfg.manifests.PSObject.Properties){if((FileHash "$studyPlan/$($prop.Name)") -ne $prop.Value){throw 'Manifest changed'}}
 if((FileHash "$studyRoot/tools/deepseek_ocr2_candidates_v1/interfaces.py") -ne $studyCfg.interfaces_sha256){throw 'Grounding policy changed'}
}
if($Stage -eq 'status'){
 docker inspect $studyName --format '{{json .State}}'
 foreach($file in @('state.json','supervisor.json')){if(Test-Path "$studyRun/$file"){Get-Content "$studyRun/$file" -Raw}}
 if(Test-Path "$studyRun/page_status.json"){$pages=Get-Content "$studyRun/page_status.json" -Raw | ConvertFrom-Json;$pages | Group-Object status | Select-Object Name,Count | ConvertTo-Json}
 exit 0
}
CheckInputs
if($Stage -eq 'prepare'){
 if((Test-Path $studyRun) -or (Test-Path $studyRaw)){throw 'Run exists: never overwrite'}
 [IO.Directory]::CreateDirectory("$studyRun/code") | Out-Null
 [IO.Directory]::CreateDirectory($studyRaw) | Out-Null
 Copy-Item "$studyRoot/tools/deepseek_ocr2_full_v1/*.py" "$studyRun/code/"
 foreach($file in @('config.json','PROTOCOL.md')){Copy-Item "$studyPlan/$file" "$studyRun/$file"}
 Copy-Item "$studyPlan/parser_pages.jsonl" "$studyRun/pages.jsonl"
 $vol=[Collections.Generic.List[object]]::new()
 function MountFile([string]$src,[string]$dst,[bool]$readOnly=$true){
  if(-not (Test-Path -LiteralPath $src)){throw "Missing mount: $src"}
  $vol.Add(@{type='bind';source=[IO.Path]::GetFullPath($src);target=$dst;read_only=$readOnly})
 }
 MountFile "$studyRun/code" '/trial'
 MountFile "$studyRoot/tools/deepseek_ocr2_candidates_v1" '/interfaces'
 MountFile "$studyRoot/artifacts/parser_candidate_comparison/deepseek_ocr2_smoke_v1/model/$($studyCfg.revision)" '/snapshot'
 MountFile "$studyRun/pages.jsonl" '/plan/pages.jsonl'
 MountFile "$studyRun/config.json" '/plan/config.json'
 MountFile "$studyRoot/experiments/parser_candidate_study/deepseek_ocr2_smoke_v1/model_download/file_integrity.json" '/evidence/file_integrity.json'
 MountFile $studyRun '/run' $false
 MountFile $studyRaw '/raw' $false
 $original='C:\Users\WenJing\Documents\WorkTransfer\layoutpatch\'
 $mounted=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
 foreach($line in Get-Content "$studyRun/pages.jsonl"){
  $page=$line | ConvertFrom-Json -Depth 100
  foreach($src in @($page.parser_input.image_path,$page.evaluation_reference.render_path,$page.evaluation_reference.receipt_path)){
   if(-not $src.StartsWith($original,[StringComparison]::OrdinalIgnoreCase)){throw 'Source path outside read-only original'}
   $relative=$src.Substring($original.Length).Replace('\','/')
   if($relative.Contains('..')){throw 'Unsafe relative path'}
   if($mounted.Add($src)){MountFile $src "/source/$relative"}
  }
 }
 foreach($studyPageId in $studyCfg.reuse_pages){MountFile "$studyRoot/artifacts/parser_candidate_comparison/deepseek_ocr2_candidates_v1/raw/candidate_20261116_02/$studyPageId" "/reuse/$studyPageId"}
 $envs=@{HF_HOME='/tmp/hf';HF_HUB_OFFLINE='1';TRANSFORMERS_OFFLINE='1';HF_HUB_DISABLE_IMPLICIT_TOKEN='1';PYTHONDONTWRITEBYTECODE='1';CUDA_VISIBLE_DEVICES='0';PYTHONPATH='/interfaces'}
 WriteNew "$studyRun/compose.json" @{services=@{worker=@{image=$studyImage;pull_policy='never';network_mode='none';gpus='all';read_only=$true;tmpfs=@('/tmp:rw,nosuid,nodev,size=1g');environment=$envs;volumes=$vol.ToArray();entrypoint=@('python');command=@('-B','-u','/trial/supervisor.py')}}}
 $code=@{};foreach($file in Get-ChildItem "$studyRun/code" -File){$code[$file.Name]=FileHash $file.FullName}
 WriteNew "$studyRun/identity.json" @{run_id=$RunId;created_at=(Get-Date -Format o);branch=(git -C $studyRoot branch --show-current);head=(git -C $studyRoot rev-parse HEAD);image_id=$studyImage;config_sha256=(FileHash "$studyRun/config.json");manifest_sha256=(FileHash "$studyRun/pages.jsonl");protocol_sha256=(FileHash "$studyRun/PROTOCOL.md");compose_sha256=(FileHash "$studyRun/compose.json");code_sha256=$code;runner_sha256=(FileHash $PSCommandPath);source_mounts_read_only=$true;raw_output=$studyRaw;model_mount_read_only=$true;network='none';training=$false;paper_editing=$false;full_comparison_authorized=$true}
 Write-Output "Prepared $studyRun"
 exit 0
}
$identity=Get-Content "$studyRun/identity.json" -Raw | ConvertFrom-Json -Depth 100
foreach($name in @('config','manifest','protocol','compose')){
 $file=@{config='config.json';manifest='pages.jsonl';protocol='PROTOCOL.md';compose='compose.json'}[$name]
 if((FileHash "$studyRun/$file") -ne $identity."${name}_sha256"){throw 'Run identity changed'}
}
foreach($prop in $identity.code_sha256.PSObject.Properties){if((FileHash "$studyRun/code/$($prop.Name)") -ne $prop.Value){throw 'Snapshot code changed'}}
if($Stage -eq 'preflight'){
 if(Test-Path "$studyRun/preflight_before_gpu.json"){throw 'Preflight receipt already exists'}
 docker compose -p $RunId -f "$studyRun/compose.json" run --rm --no-deps worker -B /trial/worker.py --preflight 2>&1 | Tee-Object "$studyRun/preflight.log"
 if($LASTEXITCODE -ne 0){throw 'Input preflight failed before OCR'}
 exit 0
}
if(Test-Path "$studyRun/launch.json"){throw 'Run already launched; no automatic retry'}
$preflight=Get-Content "$studyRun/preflight_before_gpu.json" -Raw | ConvertFrom-Json -Depth 100
if($preflight.statuses.Count -ne 837 -or $preflight.model_loaded -ne $false -or $preflight.gold_read -ne $false){throw 'Missing full input preflight'}
WriteNew "$studyRun/launch.json" @{requested_at=(Get-Date -Format o);container_name=$studyName;run_id=$RunId;preflight_sha256=(FileHash "$studyRun/preflight_before_gpu.json");new_pages=797;reused_pages=40;protocol_sha256=$studyCfg.protocol_sha256}
docker compose -p $RunId -f "$studyRun/compose.json" run -d --no-deps --name $studyName worker
if($LASTEXITCODE -ne 0){throw 'Container launch failed; inspect before another attempt'}
