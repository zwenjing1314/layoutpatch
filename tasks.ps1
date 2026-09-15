# tasks.ps1 - Windows unified entry (transparent, not black box)
# Usage:
#   ./tasks.ps1 help
#   ./tasks.ps1 check
#   ./tasks.ps1 mmdocir-prepare
#   ./tasks.ps1 mmdocir-smoke
#   ./tasks.ps1 mmdocir-colpali-full
#
# Status: check + mmdocir-prepare + mmdocir-smoke + mmdocir-colpali-full implemented (batch M3).
# mmdocir-prepare reads MMDocIR raw files via LAYOUTPATCH_DATA_ROOT (default ./data).
# ColPali pages/layouts parquet files are ~4GB; keep them out of git (see .gitignore).

param(
  [Parameter(Position=0)]
  [ValidateSet("help","check","mmdocir-prepare","mmdocir-smoke","mmdocir-colpali-full")]
  [string]$Task = "help"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
# This repository has exactly one runtime environment.  Ignore an activated
# Conda/venv shell and make every uv invocation target the project .venv.
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
$env:UV_PROJECT_ENVIRONMENT = Join-Path $ProjectRoot ".venv"
if (-not $env:UV_CACHE_DIR) { $env:UV_CACHE_DIR = ".uv-cache" }

function Get-GitCommit {
  try {
    $c = git rev-parse --short HEAD
    if ($c) { return "$c".Trim() }
  } catch {
    Write-Host "warn: git rev-parse failed"
  }
  return "unknown"
}

function Show-ExpHeader {
  param([string]$ExpId, [string]$Config, [string]$Dataset, [string]$Output)
  Write-Host ""
  Write-Host "[$ExpId]"
  Write-Host "  ProjectRoot: $ProjectRoot"
  Write-Host "  Environment: uv .venv (python $($env:UV_PROJECT_ENVIRONMENT))"
  Write-Host "  GitCommit:   $(Get-GitCommit)"
  Write-Host "  Config:      $Config"
  Write-Host "  Dataset:     $Dataset"
  Write-Host "  Output:      $Output"
  Write-Host ""
}

function Assert-UvColpaliCuda {
  Write-Host "CHECK: uv .venv must expose CUDA for ColPali tasks"
  & uv run --extra colpali python -c "import torch; assert torch.cuda.is_available(), 'CUDA unavailable'; print('cuda ok:', torch.cuda.get_device_name(0))"
  if ($LASTEXITCODE -ne 0) {
    throw "CUDA check failed. See docs/01-quickstart.md for environment setup."
  }
}

function Assert-MmdocirFullData {
  $check = "import polars as pl, sys; root='data/processed/mmdocir_evaluation'; counts={name: pl.read_parquet(f'{root}/{name}.parquet').height for name in ['documents','pages','nodes','queries']}; print('full data counts:', counts); expected={'documents':313,'pages':20395,'nodes':170338,'queries':1658}; sys.exit(0 if counts == expected else 1)"
  Write-Host "CHECK: data/processed/mmdocir_evaluation must be the frozen full MMDocIR preparation"
  & uv run --extra colpali python -c $check
  if ($LASTEXITCODE -ne 0) {
    throw "MMDocIR full data check failed. Run ./tasks.ps1 mmdocir-prepare without --limit-docs."
  }
}

switch ($Task) {
  "help" {
    Write-Host "tasks:"
    Write-Host "  check                 ruff + pytest (quality gate, no GPU needed)"
    Write-Host "  mmdocir-prepare       build MMDocIR parquet tables (needs raw data, see docs/01-quickstart.md)"
    Write-Host "  mmdocir-smoke         ColPali smoke retrieval (NOT REGISTERED YET)"
    Write-Host "  mmdocir-colpali-full  ColPali full page baseline (NOT REGISTERED YET)"
    Write-Host "usage: ./tasks.ps1 <task>"
  }
  "check" {
    Write-Host "RUN: uv run ruff check ."
    & uv run ruff check .
    if ($LASTEXITCODE -ne 0) { throw "ruff failed" }
    Write-Host "RUN: uv run pytest"
    & uv run pytest
    if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
    Write-Host "check: all green"
  }
  "mmdocir-prepare" {
    Show-ExpHeader -ExpId "M2-prepare" -Config "configs/datasets/mmdocir.yaml" `
      -Dataset "MMDocIR evaluation (raw)" -Output "data/processed/mmdocir_evaluation/"
    Write-Host "RUN: uv run lp prepare --dataset mmdocir"
    & uv run lp prepare --dataset mmdocir
    if ($LASTEXITCODE -ne 0) { throw "lp prepare failed" }
  }
  "mmdocir-smoke" {
    Show-ExpHeader -ExpId "M3-smoke" -Config "configs/experiments/mmdocir_colpali_smoke.yaml" `
      -Dataset "MMDocIR evaluation smoke (limit-docs)" -Output "runs/retrieval/mmdocir_colpali_smoke/"
    Write-Host "RUN: uv run --extra colpali lp prepare --dataset mmdocir --limit-docs 2 --output-dataset mmdocir_evaluation_smoke"
    & uv run --extra colpali lp prepare --dataset mmdocir --limit-docs 2 --output-dataset mmdocir_evaluation_smoke
    if ($LASTEXITCODE -ne 0) { throw "smoke prepare failed" }
    Write-Host "RUN: uv run --extra colpali lp retrieve --config configs/experiments/mmdocir_colpali_smoke.yaml"
    & uv run --extra colpali lp retrieve --config configs/experiments/mmdocir_colpali_smoke.yaml
    if ($LASTEXITCODE -ne 0) { throw "smoke retrieve failed" }
  }
  "mmdocir-colpali-full" {
    Assert-UvColpaliCuda
    Assert-MmdocirFullData
    Show-ExpHeader -ExpId "EXP-001" -Config "configs/experiments/mmdocir_colpali.yaml" `
      -Dataset "MMDocIR evaluation full (1658 queries)" -Output "runs/retrieval/mmdocir_colpali/"
    Write-Host "RUN: uv run --extra colpali lp retrieve --config configs/experiments/mmdocir_colpali.yaml"
    & uv run --extra colpali lp retrieve --config configs/experiments/mmdocir_colpali.yaml
    if ($LASTEXITCODE -ne 0) { throw "full retrieve failed" }
  }
}
