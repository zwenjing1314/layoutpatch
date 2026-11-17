# Python performs read-only validation; PowerShell writes only this isolated archive.
$ErrorActionPreference='Stop'
$studyRoot=Split-Path -Parent $PSScriptRoot
Set-Location $studyRoot
$studyPython='C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/.venv/Scripts/python.exe'
$studyPayload=& $studyPython -B "$PSScriptRoot/archive_deepseek_ocr2_full_results.py"
if($LASTEXITCODE -ne 0){throw 'Archive validation failed; no output written'}
$studyData=$studyPayload|ConvertFrom-Json -Depth 100
$studyOut=[IO.Path]::GetFullPath((Join-Path $studyRoot 'experiments/parser_candidate_study/deepseek_ocr2_full_v1/results/full_20261117_01'))
if($studyData.status -ne 'passed' -or [IO.Path]::GetFullPath($studyData.output) -ne $studyOut){throw 'Invalid archive destination'}
if(Test-Path -LiteralPath $studyOut){throw 'Archive exists; refusing overwrite'}
[IO.Directory]::CreateDirectory($studyOut)|Out-Null
foreach($studyProp in $studyData.files.PSObject.Properties){
    if($studyProp.Name -notmatch '^[a-zA-Z0-9_]+\.(json|md)$'){throw 'Invalid archive filename'}
    $studyPath=Join-Path $studyOut $studyProp.Name
    $studyStream=[IO.File]::Open($studyPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
    try{$studyBytes=[Convert]::FromBase64String($studyProp.Value);$studyStream.Write($studyBytes,0,$studyBytes.Length)}finally{$studyStream.Dispose()}
}
$studyManifest=Get-Content (Join-Path $studyOut 'archive_manifest.json') -Raw|ConvertFrom-Json
foreach($studyProp in $studyManifest.archive_files.PSObject.Properties){
    if((Get-FileHash -LiteralPath (Join-Path $studyOut $studyProp.Name)).Hash.ToLowerInvariant() -ne $studyProp.Value){throw 'Archive copy hash mismatch'}
}
[pscustomobject]@{status='passed';files=@($studyData.files.PSObject.Properties).Count;report=(Join-Path $studyOut 'RESULTS.md')}|ConvertTo-Json
