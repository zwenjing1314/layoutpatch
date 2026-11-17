# Build a local review archive from frozen results; no Python/model execution.
$ErrorActionPreference = 'Stop'
$studyRoot = Split-Path -Parent $PSScriptRoot
$studyDoc = Join-Path $studyRoot 'experiments/parser_candidate_study/v1/archive_v1'
$studyStage2 = Join-Path $studyRoot 'runs/parser_candidate_comparison/v1/candidate_audit/stage2_20261116_02'
$studyStage3 = Join-Path $studyRoot 'runs/parser_candidate_comparison/v1/frozen_scoring/stage3_20261116_04'
$studyArchive = Join-Path $studyRoot 'artifacts/parser_candidate_comparison/v1/archives/supplement_v1.zip'
if (Test-Path -LiteralPath $studyArchive) { throw 'Archive exists; never overwrite an archive.' }
function Read-StudyJson([string]$Path) { Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -Depth 100 }
function Get-StudyHash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Write-StudyText([string]$Path, [string]$Text) {
    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    try { $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Text); $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
}
function Percent($Value) { ([double]$Value * 100).ToString('F2', [cultureinfo]::InvariantCulture) }
foreach ($run in @($studyStage2,$studyStage3)) {
    $completion = Read-StudyJson (Join-Path $run 'completed.json')
    if ($completion.status -ne 'completed') { throw 'Incomplete source run' }
    foreach ($entry in $completion.files_sha256.PSObject.Properties) {
        if ((Get-StudyHash (Join-Path $run $entry.Name)) -ne $entry.Value) { throw "Source result hash mismatch: $($entry.Name)" }
    }
}
$identity = Read-StudyJson (Join-Path $studyStage3 'identity.json')
foreach ($entry in $identity.code_sha256.PSObject.Properties) {
    if ((Get-StudyHash (Join-Path $studyRoot $entry.Name)) -ne $entry.Value) { throw "Frozen code changed: $($entry.Name)" }
}
$validation = Read-StudyJson (Join-Path $studyRoot 'experiments/parser_candidate_study/v1/stage3_validation.json')
foreach ($entry in $validation.supplemental_files_sha256.PSObject.Properties) {
    if ((Get-StudyHash (Join-Path $studyRoot $entry.Name)) -ne $entry.Value) { throw "Supplemental evidence hash mismatch: $($entry.Name)" }
}
$stage2 = Read-StudyJson (Join-Path $studyStage2 'metrics.json')
$stage3 = Read-StudyJson (Join-Path $studyStage3 'metrics.json')
$forward = Read-StudyJson (Join-Path $studyStage3 'forward_verification.json')
if ($forward.status -ne 'passed' -or $forward.forward_replay_exact_P_prime -ne 240) { throw 'Forward verification missing' }
$derived = @(Get-Content (Join-Path $studyStage3 'derived_manifest.jsonl') | ForEach-Object { $_ | ConvertFrom-Json -Depth 40 })
if ($derived.Count -ne 320) { throw 'Derived count mismatch' }
foreach ($entry in $derived) {
    if ((Get-StudyHash $entry.path) -ne $entry.sha256) { throw "Derived hash mismatch: $($entry.path)" }
}
$numerical = [ordered]@{schema='parser-candidate-paper-summary-v1';scale='fractions_0_to_1_except_counts';source_runs=@('stage2_20261116_02','stage3_20261116_04');candidate_reachability=$stage2.metrics;candidate_paired=$stage2.paired_new_minus_old;denominators=$stage3.denominators;scoring=$stage3.summary;paired=$stage3.paired;strata=$stage3.strata;source_sha256=@{candidate_metrics=(Get-StudyHash (Join-Path $studyStage2 'metrics.json'));scoring_metrics=(Get-StudyHash (Join-Path $studyStage3 'metrics.json'))}}
Write-StudyText (Join-Path $studyDoc 'numerical_summary.json') ($numerical | ConvertTo-Json -Depth 60)
$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add('# 论文附表（从冻结JSON直接生成）')
$lines.Add('')
$lines.Add('问题宏平均；D均值及ddof=1标准差；数值为百分数，差值及区间为百分点。JSON保留原始精度。')
$lines.Add('')
$lines.Add('## 候选可达性')
$lines.Add('')
$lines.Add('| 指标 | 旧 | 新 | Δ |')
$lines.Add('|---|---:|---:|---:|')
foreach ($entry in $stage2.metrics.mineru_top_v1.PSObject.Properties) {
    $new = $stage2.metrics.mineru_top_plus_annotations_v1.($entry.Name)
    $lines.Add("| $($entry.Name) | $(Percent $entry.Value) | $(Percent $new) | $(Percent ($new-$entry.Value)) |")
}
$lines.Add('')
$lines.Add('## 排序主表与逐seed表')
$lines.Add('')
$lines.Add('| 方法 | 指标 | 旧 | 新 | Δ | 旧/新seed标准差 |')
$lines.Add('|---|---|---:|---:|---:|---:|')
foreach ($method in @('A','B','D-no-text_seed_0','D-no-text_seed_1','D-no-text_seed_2','D-no-text')) {
    foreach ($metric in @('hit1@0.5','cov@5','gold_recall@5@0.5')) {
        $old=$stage3.summary.mineru_top_v1.$method.$metric
        $new=$stage3.summary.mineru_top_plus_annotations_v1.$method.$metric
        $sd='—'
        if ($method -eq 'D-no-text') { $sd="$(Percent $old.std_ddof1) / $(Percent $new.std_ddof1)"; $old=$old.mean; $new=$new.mean }
        $lines.Add("| $method | $metric | $(Percent $old) | $(Percent $new) | $(Percent ($new-$old)) | $sd |")
    }
}
$lines.Add('')
$lines.Add('## 配对区间与题级变化（D先平均三个seed）')
$lines.Add('')
$lines.Add('| 方法 | 指标 | Δ | 95% CI | Top-1校正98.3333% CI | 改善/退步/不变 |')
$lines.Add('|---|---|---:|---|---|---|')
foreach ($method in @('A','B','D-no-text')) {
    foreach ($metric in @('hit1@0.5','cov@5','gold_recall@5@0.5')) {
        $value=$stage3.paired.$method.$metric
        $adjusted='不适用（次要指标）'
        if ($metric -eq 'hit1@0.5') { $adjusted="[$(Percent $value.bonferroni_ci_low), $(Percent $value.bonferroni_ci_high)]" }
        $lines.Add("| $method | $metric | $(Percent $value.mean_diff) | [$(Percent $value.ci95_low), $(Percent $value.ci95_high)] | $adjusted | $($value.improved)/$($value.worsened)/$($value.unchanged) |")
    }
}
$lines.Add('')
$lines.Add('八层完整结果保留在 numerical_summary.json.strata；不从分层结果挑选最佳层作为主结果。')
Write-StudyText (Join-Path $studyDoc 'RESULTS_TABLES.md') ($lines -join "`n")
# Include small reviewable records. Large tensors/images and original resources remain referenced.
$files = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
foreach ($folder in @('experiments/parser_candidate_study/v1','runs/parser_candidate_comparison/v1/candidate_audit/stage2_20261116_02','runs/parser_candidate_comparison/v1/frozen_scoring/stage3_20261116_04')) {
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $studyRoot $folder) -File -Recurse) { [void]$files.Add($file.FullName) }
}
foreach ($pattern in @('configs/experiments/parser_candidate*.yaml','scripts/*parser_candidate*.py','scripts/*parser_candidate*.ps1','scripts/parser_study_support.py','tests/datasets/test_parser_candidate*.py','src/layoutpatch/datasets/parser_candidates.py')) {
    foreach ($file in Get-ChildItem -Path (Join-Path $studyRoot $pattern) -File) { [void]$files.Add($file.FullName) }
}
foreach ($run in @('stage3_20261116_01','stage3_20261116_02','stage3_20261116_03')) {
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $studyRoot "runs/parser_candidate_comparison/v1/frozen_scoring/$run") -File -Recurse) { [void]$files.Add($file.FullName) }
}
[void]$files.Add((Join-Path $studyRoot 'runs/parser_candidate_comparison/v1/candidate_audit/stage2_20261116_01/failed_attempt.json'))
$export = Read-StudyJson (Join-Path $studyStage2 'export_manifest.json')
foreach ($entry in $export.outputs.PSObject.Properties) {
    if ((Get-StudyHash $entry.Value.path) -ne $entry.Value.sha256) { throw 'Candidate hash mismatch' }
    [void]$files.Add($entry.Value.path)
}
$included = @($files | Sort-Object | ForEach-Object {
    $relative=[System.IO.Path]::GetRelativePath($studyRoot,$_).Replace('\','/')
    if ($relative.StartsWith('..')) { throw 'Outside worktree inclusion rejected' }
    [ordered]@{path=$relative;bytes=(Get-Item -LiteralPath $_).Length;sha256=(Get-StudyHash $_)}
})
$manifest=[ordered]@{schema='parser-candidate-review-archive-v1';created_at=(Get-Date -Format o);branch='experiment/parser-candidate-study';baseline_commit='02693ee908aec8a12ef53b3492892f84cf588499';valid_runs=@('stage2_20261116_02','stage3_20261116_04');included_files=$included;manifest_self_hash_policy='manifest is embedded in ZIP; final ZIP hash recorded in external receipt';derived_tensors_not_copied=$derived;derived_sha256_verified=320;original_read_only_dependencies='See scoring identity.bindings, stage1 preparation_identity and sample_pages; P/Q/checkpoints/raw/page images/environment are not bundled';limitations=@('review archive, not standalone runtime','original absolute paths retained for traceability','partial invalid-run tensors retained in place, not copied','no new inference or metrics computation')}
$manifestPath=Join-Path $studyDoc 'archive_manifest.json'
Write-StudyText $manifestPath ($manifest | ConvertTo-Json -Depth 80)
[System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($studyArchive)) | Out-Null
$zipStream=[System.IO.File]::Open($studyArchive,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::ReadWrite)
$zip=[System.IO.Compression.ZipArchive]::new($zipStream,[System.IO.Compression.ZipArchiveMode]::Create,$false)
try {
    foreach ($entry in $included) { [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip,(Join-Path $studyRoot $entry.path),$entry.path,[System.IO.Compression.CompressionLevel]::Optimal) | Out-Null }
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip,$manifestPath,'experiments/parser_candidate_study/v1/archive_v1/archive_manifest.json',[System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
} finally { $zip.Dispose(); $zipStream.Dispose() }
$expected=@{}; foreach ($entry in $included) { $expected[$entry.path]=$entry.sha256 }
$expected['experiments/parser_candidate_study/v1/archive_v1/archive_manifest.json']=Get-StudyHash $manifestPath
$zip=[System.IO.Compression.ZipFile]::OpenRead($studyArchive)
try {
    if ($zip.Entries.Count -ne $expected.Count) { throw 'ZIP entry count mismatch' }
    foreach ($entry in $zip.Entries) {
        $stream=$entry.Open(); $hasher=[System.Security.Cryptography.SHA256]::Create()
        try { $actual=[Convert]::ToHexString($hasher.ComputeHash($stream)).ToLowerInvariant() } finally { $stream.Dispose(); $hasher.Dispose() }
        if (-not $expected.ContainsKey($entry.FullName) -or $actual -ne $expected[$entry.FullName]) { throw "ZIP entry hash mismatch: $($entry.FullName)" }
    }
} finally { $zip.Dispose() }
$receipt=[ordered]@{status='verified';archive_path=[System.IO.Path]::GetRelativePath($studyRoot,$studyArchive).Replace('\','/');archive_sha256=(Get-StudyHash $studyArchive);archive_bytes=(Get-Item $studyArchive).Length;zip_entries_verified=$expected.Count;manifest_sha256=(Get-StudyHash $manifestPath);existing_completed_checks_passed=$true;frozen_code_checks_passed=$true;supplemental_evidence_checks_passed=$true;derived_hashes_verified=320;new_inference=$false;new_training=$false;original_data_copied=$false;git_commit_created=$false;remote_push=$false}
Write-StudyText (Join-Path $studyDoc 'archive_receipt.json') ($receipt | ConvertTo-Json -Depth 10)
$receipt | ConvertTo-Json -Depth 10
