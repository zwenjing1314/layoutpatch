param(
    [Parameter(Mandatory = $true)][string]$SourceRoot,
    [Parameter(Mandatory = $true)][string]$Python,
    [switch]$VerifyOnly
)
$ErrorActionPreference = 'Stop'
$studyRoot = Split-Path -Parent $PSScriptRoot
$studySource = (Resolve-Path -LiteralPath $SourceRoot).Path
if ($studySource -eq $studyRoot) { throw 'Source archive and experiment worktree must differ.' }
$studyTracked = Join-Path $studyRoot 'experiments/parser_candidate_study/v1'
$studyRun = Join-Path $studyRoot 'runs/parser_candidate_comparison/v1/preparation'

# Python only reads and emits JSON. This wrapper owns all writes. Never invokes
# uv sync, pip, a parser, an encoder, a scoring entry, or training.
$studyJson = & $Python -B (Join-Path $PSScriptRoot 'prepare_parser_candidate_study.py') --source-root $studySource
if ($LASTEXITCODE -ne 0) { throw 'Preparation failed; no result files saved.' }
$studyBundle = ($studyJson -join "`n") | ConvertFrom-Json -Depth 100
$studyOutputs = [ordered]@{
    'sample_pages.jsonl' = (($studyBundle.sample_pages | ForEach-Object { ConvertTo-Json -InputObject $_ -Compress -Depth 100 }) -join "`n") + "`n"
    'sample_units.jsonl' = (($studyBundle.sample_units | ForEach-Object { ConvertTo-Json -InputObject $_ -Compress -Depth 100 }) -join "`n") + "`n"
    'stage1_audit.json' = (ConvertTo-Json -InputObject $studyBundle.audit -Depth 100) + "`n"
    'old_sample_gold_diagnostics.jsonl' = (($studyBundle.old_sample_gold_diagnostics | ForEach-Object { ConvertTo-Json -InputObject $_ -Compress -Depth 100 }) -join "`n") + "`n"
}
if ($VerifyOnly) {
    foreach ($studyName in $studyOutputs.Keys) {
        $studyTarget = Join-Path $studyTracked $studyName
        if ([System.IO.File]::ReadAllText($studyTarget) -cne $studyOutputs[$studyName]) {
            throw "Saved preparation differs: $studyName"
        }
    }
    Write-Output 'PASS: all four preparation files reproduce exactly; source archives read only.'
    return
}
$studyTargets = @($studyOutputs.Keys | ForEach-Object { Join-Path $studyTracked $_ })
$studyTargets += Join-Path $studyRun 'bundle.json'
foreach ($studyTarget in $studyTargets) {
    if (Test-Path -LiteralPath $studyTarget) { throw "Refusing to overwrite: $studyTarget; use -VerifyOnly." }
}
New-Item -ItemType Directory -Path $studyTracked, $studyRun -Force | Out-Null
function Write-StudyExclusive([string]$Path, [string]$Text) {
    $studyStream = [System.IO.File]::Open($Path, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    try {
        $studyBytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Text)
        $studyStream.Write($studyBytes, 0, $studyBytes.Length)
    } finally { $studyStream.Dispose() }
}
foreach ($studyName in $studyOutputs.Keys) {
    Write-StudyExclusive (Join-Path $studyTracked $studyName) $studyOutputs[$studyName]
}
Write-StudyExclusive (Join-Path $studyRun 'bundle.json') (($studyJson -join "`n") + "`n")
$studyBundle.audit.sample_denominators | ConvertTo-Json
