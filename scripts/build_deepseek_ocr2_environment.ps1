param([ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$RunId = 'env_20261116_01')
$ErrorActionPreference = 'Stop'
$studyRoot = Split-Path -Parent $PSScriptRoot
$studyContext = Join-Path $studyRoot 'tools/deepseek_ocr2_smoke_v1'
$studyRun = Join-Path $studyRoot "runs/parser_candidate_comparison/deepseek_ocr2_smoke_v1/environment/$RunId"
if (-not (Test-Path $studyRun)) { throw 'Create a new isolated run directory before execution' }
if (Test-Path (Join-Path $studyRun 'build_identity.json')) { throw 'Build identity already exists; preserve this attempt and use a new run ID' }
$studyImage = "layoutpatch-deepseek-ocr2-env:$RunId"
$studyCuda = docker image inspect nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04 | ConvertFrom-Json -Depth 50
if ($LASTEXITCODE -ne 0 -or -not $studyCuda[0].RepoDigests) { throw 'Pinned CUDA base not available' }
$studyBase = @($studyCuda[0].RepoDigests | Where-Object { $_ -like 'nvidia/cuda@sha256:*' })[0]
if (-not $studyBase) { throw 'Missing CUDA repository digest' }
$studyFiles = [ordered]@{}
Get-ChildItem -LiteralPath $studyContext -File -Recurse | Sort-Object FullName | ForEach-Object { $studyFiles[[System.IO.Path]::GetRelativePath($studyContext,$_.FullName).Replace('\','/')] = (Get-FileHash $_.FullName).Hash.ToLower() }
$studyIdentity = [ordered]@{run_id=$RunId;created_at=(Get-Date -Format o);host='Windows 11';backend='Docker Desktop Linux / WSL2';cuda_base=$studyBase;uv_source=(Get-Content (Join-Path $studyContext 'uv_source.json') -Raw | ConvertFrom-Json);image_tag=$studyImage;build_context_sha256=$studyFiles;build_script_sha256=(Get-FileHash $PSCommandPath).Hash.ToLower();scope='environment_install_and_synthetic_GPU_validation_only';model_download=$false;ocr_inference=$false;training=$false;source_data_mount=$false}
$studyIdentity | ConvertTo-Json -Depth 12 | Set-Content -Encoding utf8 (Join-Path $studyRun 'build_identity.json')
docker build --platform linux/amd64 --progress plain --build-arg "CUDA_BASE=$studyBase" -t $studyImage $studyContext 2>&1 | Tee-Object -FilePath (Join-Path $studyRun 'build.log')
if ($LASTEXITCODE -ne 0) { throw "Image build failed; retain $studyRun/build.log" }
docker image inspect $studyImage | Set-Content -Encoding utf8 (Join-Path $studyRun 'image_inspect.json')
$studyImageId = (docker image inspect $studyImage --format '{{.Id}}').Trim()
$studyProbe = docker run --rm --pull=never --network none --gpus all --read-only --tmpfs /tmp:rw,nosuid,nodev,size=256m --name "layoutpatch-ocr2-$RunId-probe" $studyImageId 2> (Join-Path $studyRun 'probe.stderr.log')
$studyProbe | Set-Content -Encoding utf8 (Join-Path $studyRun 'probe.stdout.log')
if ($LASTEXITCODE -ne 0) { throw 'Synthetic environment validation failed; retain logs' }
# NVIDIA base image banners precede JSON; preserve complete stdout separately.
$studyJoined = $studyProbe -join "`n"
$studyJsonStart = $studyJoined.IndexOf('{')
if ($studyJsonStart -lt 0) { throw 'Probe JSON absent' }
$studyReport = $studyJoined.Substring($studyJsonStart) | ConvertFrom-Json -Depth 20
if ($studyReport.status -ne 'passed' -or $studyReport.model_loaded -or $studyReport.ocr_inference) { throw 'Invalid probe outcome' }
$studyReport | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 (Join-Path $studyRun 'probe.json')
$studyContainer = docker create --network none --entrypoint /bin/true $studyImageId
if ($LASTEXITCODE -ne 0) { throw 'Could not create stopped container for lock extraction' }
try {
    foreach ($studyLock in @('requirements.lock.txt','os-packages.lock.tsv','flash-wheel.sha256','uv-version.txt','python-version.txt')) {
        docker cp "${studyContainer}:/opt/environment/$studyLock" (Join-Path $studyRun $studyLock)
        if ($LASTEXITCODE -ne 0) { throw "Could not export $studyLock" }
    }
} finally { docker rm $studyContainer | Out-Null }
$studyChecks = [ordered]@{}
Get-ChildItem -LiteralPath $studyRun -File | Sort-Object Name | ForEach-Object { $studyChecks[$_.Name] = (Get-FileHash $_.FullName).Hash.ToLower() }
[ordered]@{status='environment_verified_no_model';image_id=$studyImageId;image_tag=$studyImage;cuda_base=$studyBase;files_sha256=$studyChecks;model_download=$false;ocr_inference=$false;training=$false;source_environment_modified=$false} | ConvertTo-Json -Depth 15 | Set-Content -Encoding utf8 (Join-Path $studyRun 'completed.json')
Write-Output "Environment verified: $studyImageId"



