param(
    [Parameter(Mandatory = $true)][ValidateSet('score', 'verify', 'preflight')][string]$Stage,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$RunId,
    [Parameter(Mandatory = $true)][ValidatePattern('^full_[a-zA-Z0-9_]+$')][string]$CandidateRunId,
    [string]$Python = 'C:\Users\WenJing\Documents\WorkTransfer\layoutpatch\.venv\Scripts\python.exe'
)
$ErrorActionPreference = 'Stop'
if(-not $RunId.StartsWith('full_score_')){throw 'Dedicated DeepSeek run ID required'}
$studyRoot = Split-Path -Parent $PSScriptRoot
$studyAllowed = @(
    "runs/parser_candidate_comparison/v1/full_frozen_scoring/$RunId",
    "artifacts/parser_candidate_comparison/v1/full_derived/$RunId"
) | ForEach-Object { [System.IO.Path]::GetFullPath((Join-Path $studyRoot $_)) }
$studyStart = [System.Diagnostics.ProcessStartInfo]::new()
$studyStart.FileName = $Python
$studyStart.WorkingDirectory = $studyRoot
$studyCache = Join-Path $studyRoot 'artifacts/parser_candidate_comparison/v1/runtime_cache/full_scoring/torchinductor'
[System.IO.Directory]::CreateDirectory($studyCache) | Out-Null
[System.IO.Directory]::CreateDirectory((Join-Path $studyCache 'dynamo')) | Out-Null
$studyStart.Environment['TORCHINDUCTOR_CACHE_DIR'] = $studyCache
$studyStart.Environment['CUDA_CACHE_DISABLE'] = '1'
$studyStart.UseShellExecute = $false
$studyStart.CreateNoWindow = $true
$studyStart.RedirectStandardInput = $true
$studyStart.RedirectStandardOutput = $true
$studyStart.RedirectStandardError = $true
foreach ($studyArg in @('-B', (Join-Path $PSScriptRoot 'run_deepseek_ocr2_full_scoring.py'), '--run-id', $RunId, '--stage', $Stage, '--write-broker', '--candidate-run', "runs/parser_candidate_comparison/deepseek_ocr2_full_v1/$CandidateRunId")) {
    $studyStart.ArgumentList.Add($studyArg)
}
$studyProcess = [System.Diagnostics.Process]::Start($studyStart)
$studyErrors = $studyProcess.StandardError.ReadToEndAsync()
$studyWatch=[Diagnostics.Stopwatch]::StartNew()
try {
    while ($true) {
        $studyRead=$studyProcess.StandardOutput.ReadLineAsync()
        while(-not $studyRead.Wait(1000)) {
            if($studyWatch.Elapsed.TotalSeconds -gt 7200) {
                Write-Output 'Hard timeout exceeded; terminating scoring process tree and preserving partial outputs.'
                $studyProcess.Kill($true)
                throw 'Scoring exceeded 7200 second hard timeout'
            }
        }
        $studyLine=$studyRead.Result
        if($null -eq $studyLine){break}
        $studyEvent = $studyLine | ConvertFrom-Json -Depth 100
        if ($studyEvent.event -ne 'study_write') { Write-Output $studyLine; continue }
        $studyPath = [System.IO.Path]::GetFullPath($studyEvent.path)
        $studyAllowedPath = $false
        foreach ($studyPrefix in $studyAllowed) {
            if ($studyPath.StartsWith($studyPrefix + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { $studyAllowedPath = $true }
        }
        if (-not $studyAllowedPath) { throw "Write outside isolated run rejected: $studyPath" }
        # Reject existing junctions/symlinks in the destination ancestry.
        $studyAncestor = [System.IO.Path]::GetDirectoryName($studyPath)
        while ($studyAncestor -and $studyAncestor -ne $studyRoot) {
            if (Test-Path -LiteralPath $studyAncestor) {
                if (((Get-Item -Force -LiteralPath $studyAncestor).Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Reparse-point output rejected: $studyAncestor" }
            }
            $studyAncestor = [System.IO.Path]::GetDirectoryName($studyAncestor)
        }
        [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($studyPath)) | Out-Null
        $studyStream = [System.IO.File]::Open($studyPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
        try {
            $studyBytes = [System.Convert]::FromBase64String($studyEvent.base64)
            $studyStream.Write($studyBytes, 0, $studyBytes.Length)
        } finally { $studyStream.Dispose() }
        $studyProcess.StandardInput.WriteLine('ok')
        $studyProcess.StandardInput.Flush()
    }
    $studyProcess.WaitForExit()
    $studyErrorText = $studyErrors.GetAwaiter().GetResult()
    if ($studyErrorText) { Write-Output $studyErrorText }
    if ($studyProcess.ExitCode -ne 0) { throw "Study process failed with exit code $($studyProcess.ExitCode). Existing outputs retained; no automatic retry." }
} catch {
    if (-not $studyProcess.HasExited) {
        $studyProcess.StandardInput.WriteLine('error: write broker stopped')
        $studyProcess.StandardInput.Close()
    }
    throw
} finally { $studyProcess.Dispose() }




