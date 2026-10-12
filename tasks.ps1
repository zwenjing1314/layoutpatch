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
  [ValidateSet("help","check","mmdocir-prepare","mmdocir-smoke","mmdocir-colpali-full","mmdocir-bge-m3-full","mmdocir-hybrid-full","phase1b-stratify","phase1c-baselines","phase1c-smoke","phase2r-arxivqa","phase2r-dude","phase2r-arxivqa-dude","phase2r-arxivqa-notext","fusion-arxivqa","region-ann-pilot","route-v2-identity","route-v2-data","route-v2-queries","route-v2-external-tests","route-v2-external-audit","route-v2-external-status","route-v2-external-tool-status","route-v2-external-contract","route-v2-external-pages","route-v2-external-images","route-v2-external-final-review","route-v2-external-full-prep","route-v2-external-encoding","route-v2-external-encoding-tests","route-v2-external-eval-tests","route-v2-external-eval-preflight","route-v2-external-eval","route-v2-external-eval-verify","route-v2-e-tests","route-v2-e-check","route-v2-e-train","route-v2-e-external","route-v2-e-verify","route-v2-exp3-tests","route-v2-exp3","route-v2-exp2-result-check","route-v2-exp2-verify","route-v2-d-dev-nodes","route-v2-d-tests","route-v2-d-verify","route-v2-exp2","route-v2-d-nodes","route-v2-d-smoke","route-v2-exp1-verify","route-v2-exp1-result-check","route-v2-exp1-tests","route-v2-exp1","route-v2-cache-tests","route-v2-smoke")]
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

function Invoke-RouteV2Step {
  # Runs one offline route-v2 step unless its output already exists (outputs are never replaced).
  param([string]$Script, [string]$Output)
  if (Test-Path -LiteralPath $Output) {
    Write-Host "SKIP: $Script (exists: $Output)"
    return
  }
  Write-Host "RUN: uv run --offline --no-sync python $Script"
  & uv run --offline --no-sync python $Script
  if ($LASTEXITCODE -ne 0) { throw "$Script failed" }
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
  & uv run python -c $check
  if ($LASTEXITCODE -ne 0) {
    throw "MMDocIR full data check failed. Run ./tasks.ps1 mmdocir-prepare without --limit-docs."
  }
}

function Assert-BgeM3Cached {
  $check = "from sentence_transformers import SentenceTransformer; m=SentenceTransformer('BAAI/bge-m3', local_files_only=True); print('bge-m3 ok:', m.get_sentence_embedding_dimension())"
  Write-Host "CHECK: BAAI/bge-m3 must be loadable from local HF cache (local_files_only=True)"
  & uv run python -c $check
  if ($LASTEXITCODE -ne 0) {
    throw "BAAI/bge-m3 is not in local cache. Download it first (e.g. huggingface-cli download BAAI/bge-m3). No TF-IDF fallback allowed for EXP-003/EXP-004."
  }
}

switch ($Task) {
  "help" {
    Write-Host "tasks:"
    Write-Host "  check                 ruff + pytest (quality gate, no GPU needed)"
    Write-Host "  mmdocir-prepare       build MMDocIR parquet tables (needs raw data, see docs/01-quickstart.md)"
    Write-Host "  mmdocir-smoke         ColPali smoke retrieval (NOT REGISTERED YET)"
    Write-Host "  mmdocir-colpali-full  ColPali full page baseline (NOT REGISTERED YET)"
    Write-Host "  mmdocir-bge-m3-full   BGE-M3 dense full page baseline EXP-003 (1A, requires local BAAI/bge-m3)"
    Write-Host "  mmdocir-hybrid-full   BM25+BGE-M3 RRF hybrid full page baseline EXP-004 (1A)"
    Write-Host "  phase1b-stratify      Phase 1B stratification + cases + gate support EXP-005 (1B, CPU)"
    Write-Host "  phase1c-smoke         Phase 1C smoke 2 docs EXP-006 (needs GPU, cache-only pages)"
    Write-Host "  phase1c-baselines     Phase 1C full 1343A/45B EXP-006 (needs GPU, cache-only pages)"
    Write-Host "  phase2r-arxivqa       Phase 2-R ArxivQA train + one dev_eval judgment"
    Write-Host "  phase2r-dude          Phase 2-R DUDE train + one dev_eval judgment"
    Write-Host "  phase2r-arxivqa-notext  ArxivQA no-text control; does not replace the current head"
    Write-Host "  fusion-arxivqa         Phase 2 ArxivQA fusion train + one dev_eval judgment"
    Write-Host "  region-ann-pilot       40-question local annotation workbook + format check; not training"
    Write-Host "  route-v2-identity      pinned external source + identity screening/verification (no scoring)"
    Write-Host "  route-v2-data          data roles, coordinate gate, region units/audit, supervision overlays"
    Write-Host "  route-v2-smoke         <=16 source_train questions, <=200 steps; stops if a precondition fails"
    Write-Host "  route-v2-external-pages fixed SciEGQA eight-page MinerU Basic ONNX render/parse audit"
    Write-Host "  route-v2-external-images download/check/extract fixed eight official images and audit PDF mapping"
    Write-Host "  route-v2-external-eval-tests synthetic statistics and read-only boundary checks"
    Write-Host "  route-v2-external-eval-preflight read-only frozen SciEGQA scoring admission check"
    Write-Host "  route-v2-external-eval  EXP-017 frozen given-correct-page localization; reuses a verified run"
    Write-Host "  route-v2-external-eval-verify read-only recomputation from saved predictions"
    Write-Host "  route-v2-e-tests       unique E candidate-ranker targeted lint and tests"
    Write-Host "  route-v2-e-check       one synthetic training-side implementation check"
    Write-Host "  route-v2-e-train       EXP-018 unique E seed 0/1/2 formal training"
    Write-Host "  route-v2-e-external    one post-hoc external supplement; score E only"
    Write-Host "  route-v2-e-verify      read-only recomputation from saved supplement"
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
  "mmdocir-bge-m3-full" {
    Assert-MmdocirFullData
    Assert-BgeM3Cached
    Show-ExpHeader -ExpId "EXP-003" -Config "configs/experiments/mmdocir_bge_m3_page.yaml" `
      -Dataset "MMDocIR evaluation full (1658 queries)" -Output "runs/retrieval/mmdocir_bge_m3_page/"
    Write-Host "RUN: uv run lp retrieve --config configs/experiments/mmdocir_bge_m3_page.yaml"
    & uv run lp retrieve --config configs/experiments/mmdocir_bge_m3_page.yaml
    if ($LASTEXITCODE -ne 0) { throw "bge-m3 retrieve failed" }
  }
  "mmdocir-hybrid-full" {
    Assert-MmdocirFullData
    Assert-BgeM3Cached
    Show-ExpHeader -ExpId "EXP-004" -Config "configs/experiments/mmdocir_hybrid_page.yaml" `
      -Dataset "MMDocIR evaluation full (1658 queries)" -Output "runs/retrieval/mmdocir_hybrid_page/"
    Write-Host "RUN: uv run lp retrieve --config configs/experiments/mmdocir_hybrid_page.yaml"
    & uv run lp retrieve --config configs/experiments/mmdocir_hybrid_page.yaml
    if ($LASTEXITCODE -ne 0) { throw "hybrid retrieve failed" }
  }
  "phase1b-stratify" {
    Assert-MmdocirFullData
    Show-ExpHeader -ExpId "EXP-005" -Config "scripts/run_phase1b_stratify.py --k 5 --iou 0.5" `
      -Dataset "MMDocIR evaluation full (1658 queries)" -Output "artifacts/diagnosis/mmdocir_evaluation/"
    Write-Host "RUN: uv run python scripts/run_phase1b_stratify.py --k 5 --iou 0.5"
    & uv run python scripts/run_phase1b_stratify.py --k 5 --iou 0.5
    if ($LASTEXITCODE -ne 0) { throw "phase1b stratify failed" }
  }
  "phase1c-smoke" {
    Assert-UvColpaliCuda
    Assert-MmdocirFullData
    Show-ExpHeader -ExpId "EXP-006-smoke" -Config "scripts/run_phase1c.py --limit-docs 2 --k 5 --iou 0.5" `
      -Dataset "MMDocIR evaluation smoke (2 docs)" -Output "artifacts/baselines/mmdocir_1c/"
    Write-Host "RUN: uv run --extra colpali python scripts/run_phase1c.py --limit-docs 2 --k 5 --iou 0.5"
    & uv run --extra colpali python scripts/run_phase1c.py --limit-docs 2 --k 5 --iou 0.5
    if ($LASTEXITCODE -ne 0) { throw "phase1c smoke failed" }
  }
  "phase1c-baselines" {
    Assert-UvColpaliCuda
    Assert-MmdocirFullData
    Show-ExpHeader -ExpId "EXP-006" -Config "scripts/run_phase1c.py --k 5 --iou 0.5" `
      -Dataset "MMDocIR evaluation full (1343A/45B)" -Output "artifacts/baselines/mmdocir_1c/"
    Write-Host "RUN: uv run --extra colpali python scripts/run_phase1c.py --k 5 --iou 0.5"
    & uv run --extra colpali python scripts/run_phase1c.py --k 5 --iou 0.5
    if ($LASTEXITCODE -ne 0) { throw "phase1c baselines failed" }
  }
  "phase2r-arxivqa" {
    Assert-UvColpaliCuda
    Write-Host "RUN: uv run --extra colpali python scripts/train_phase2r.py"
    & uv run --extra colpali python scripts/train_phase2r.py
    if ($LASTEXITCODE -ne 0) { throw "phase2r arxivqa failed" }
  }
  "phase2r-dude" {
    Assert-UvColpaliCuda
    Write-Host "RUN: uv run --extra colpali python scripts/train_phase2r_dude.py"
    & uv run --extra colpali python scripts/train_phase2r_dude.py
    if ($LASTEXITCODE -ne 0) { throw "phase2r dude failed" }
  }
  "phase2r-arxivqa-dude" {
    Assert-UvColpaliCuda
    Write-Host "RUN: uv run --extra colpali python scripts/train_phase2r_arxivqa_dude.py"
    & uv run --extra colpali python scripts/train_phase2r_arxivqa_dude.py
    if ($LASTEXITCODE -ne 0) { throw "phase2r arxivqa dude failed" }
  }
  "phase2r-arxivqa-notext" {
    Assert-UvColpaliCuda
    Write-Host "RUN: uv run --extra colpali python scripts/train_phase2r_arxivqa_notext.py"
    & uv run --extra colpali python scripts/train_phase2r_arxivqa_notext.py
    if ($LASTEXITCODE -ne 0) { throw "phase2r arxivqa notext failed" }
  }
  "fusion-arxivqa" {
    Assert-UvColpaliCuda
    Show-ExpHeader -ExpId "FUSION-ARXIVQA" -Config "scripts/train_fusion_arxivqa.py" `
      -Dataset "MMDocIR train ArxivQA + dev_eval" -Output "runs/retrieval/mmdocir_fusion_arxivqa/"
    Write-Host "RUN: uv run python scripts/train_fusion_arxivqa.py"
    & uv run python scripts/train_fusion_arxivqa.py
    if ($LASTEXITCODE -ne 0) { throw "fusion arxivqa failed" }
  }
  "region-ann-pilot" {
    Show-ExpHeader -ExpId "REGION-ANN-PILOT" -Config "scripts/region_ann_pilot.py" `
      -Dataset "ArxivQA train_fit 40-question annotation materials" -Output "experiments/region_annotation/pilot_materials/workbook.html"
    Write-Host "RUN: uv run python scripts/region_ann_pilot.py prepare"
    & uv run python scripts/region_ann_pilot.py prepare
    if ($LASTEXITCODE -ne 0) { throw "region-ann-pilot prepare failed" }
    Write-Host "RUN: uv run python scripts/region_ann_pilot.py check --annotator A"
    & uv run python scripts/region_ann_pilot.py check --annotator A
    if ($LASTEXITCODE -ne 0) { throw "region-ann-pilot check failed" }
  }
  "route-v2-identity" {
    Show-ExpHeader -ExpId "ROUTE-V2-IDENTITY" -Config "docs/ROUTE_V2_PROTOCOL.md section 2" `
      -Dataset "MMDocIR evaluation 313 docs + SciEGQA-Bench rev 9bdca77" -Output "artifacts/route_v2_data/"
    Invoke-RouteV2Step "scripts/acquire_route_v2_external.py" "data/raw/sciegqa_bench/9bdca77be633cc3259d7e3739d35b38ab00bf5d9/acquisition.json"
    Invoke-RouteV2Step "scripts/audit_route_v2_identity.py" "artifacts/route_v2_data/identity_v1/overlap_report.json"
    Invoke-RouteV2Step "scripts/verify_route_v2_candidates.py" "artifacts/route_v2_data/verification_v1/verification_report.json"
    Invoke-RouteV2Step "scripts/audit_route_v2_internal_duplicates.py" "artifacts/route_v2_data/internal_identity_v1.json"
  }
  "route-v2-data" {
    Show-ExpHeader -ExpId "ROUTE-V2-DATA" -Config "docs/ROUTE_V2_PROTOCOL.md sections 2-4" `
      -Dataset "MMDocIR evaluation (re-purposed source pool)" -Output "experiments/route_v2_splits/data-roles-v1/ + artifacts/route_v2_data/"
    if (-not (Test-Path "artifacts/route_v2_data/verification_v1/verification_report.json")) {
      throw "Identity evidence missing. Run ./tasks.ps1 route-v2-identity first."
    }
    Invoke-RouteV2Step "scripts/build_route_v2_split.py" "experiments/route_v2_splits/data-roles-v1"
    Invoke-RouteV2Step "scripts/audit_route_v2_coordinates.py" "artifacts/route_v2_data/coordinate_audit_v1.json"
    Invoke-RouteV2Step "scripts/build_route_v2_regions.py" "artifacts/route_v2_data/regions_v1"
    Invoke-RouteV2Step "scripts/render_route_v2_supervision.py" "artifacts/route_v2_data/regions_v1/supervision_viz"
  }
  "route-v2-queries" {
    Show-ExpHeader -ExpId "ROUTE-V2-QUERY-CACHE" -Config "scripts/cache_route_v2_queries.py" `
      -Dataset "data-roles-v1 source_train/source_val/source_dev; encoding only" -Output "artifacts/route_v2_data/query_cache_v1/source_queries.pt"
    & uv run --offline --no-sync python scripts/cache_route_v2_queries.py
    if ($LASTEXITCODE -ne 0) { throw "route-v2-queries stopped (see query_cache_v1/runs/)" }
  }
  "route-v2-external-tests" {
    & uv run --offline --no-sync ruff check src/layoutpatch/datasets/sciegqa.py tests/datasets/test_sciegqa.py scripts/prepare_route_v2_external.py scripts/prepare_route_v2_external_pages.py scripts/prepare_route_v2_external_full.py scripts/acquire_route_v2_external_images.py scripts/review_route_v2_external_pages.py tests/datasets/test_external_image_review.py scripts/route_v2_mineru_worker.py src/layoutpatch/datasets/mineru.py tests/datasets/test_mineru.py
    if ($LASTEXITCODE -ne 0) { throw "external metadata lint failed" }
    & uv run --offline --no-sync pytest tests/datasets/test_mineru.py tests/datasets/test_external_image_review.py
    if ($LASTEXITCODE -ne 0) { throw "external metadata tests failed" }
  }
  "route-v2-external-audit" {
    Show-ExpHeader -ExpId "EXTERNAL-PREP" -Config "configs/experiments/route_v2_external_v1.yaml" `
      -Dataset "pinned SciEGQA 1623 questions; metadata only" -Output "artifacts/route_v2_external/preparation_v1/<timestamp>/"
    & uv run --offline --no-sync python scripts/prepare_route_v2_external.py
    if ($LASTEXITCODE -ne 0) { throw "external preparation identity hard stop; no automatic retry" }
  }
  "route-v2-external-status" {
    & uv run --offline --no-sync python scripts/prepare_route_v2_external_pages.py --inspect-only
    if ($LASTEXITCODE -ne 0) { throw "external fixed-page access/status check failed" }
  }
  "route-v2-external-tool-status" {
    & uv run --offline --no-sync python scripts/prepare_route_v2_external_pages.py --inspect-tool
    if ($LASTEXITCODE -ne 0) { throw "external parser state check failed" }
  }
  "route-v2-external-contract" {
    & uv run --offline --no-sync python scripts/prepare_route_v2_external_pages.py --inspect-contract
    if ($LASTEXITCODE -ne 0) { throw "external parser output contract check failed" }
  }
  "route-v2-external-pages" {
    Show-ExpHeader -ExpId "EXTERNAL-PREP-PAGES" -Config "scripts/prepare_route_v2_external_pages.py" `
      -Dataset "fixed manifest eight pages only; no questions/gold/scoring" -Output "artifacts/route_v2_external/preparation_v1/<timestamp>/"
    & uv run --offline --no-sync python scripts/prepare_route_v2_external_pages.py
    if ($LASTEXITCODE -ne 0) { throw "external eight-page engineering audit failed; preserve output and error" }
  }
  "route-v2-external-images" {
    Show-ExpHeader -ExpId "EXTERNAL-PREP-IMAGES" -Config "configs/tools/sciegqa_images_v1.yaml" `
      -Dataset "pinned SciEGQA official Images.tar; fixed eight pages only; mapping audit" -Output "artifacts/route_v2_external/preparation_v1/<timestamp>/"
    & uv run --offline --no-sync python scripts/acquire_route_v2_external_images.py
    if ($LASTEXITCODE -ne 0) { throw "external fixed-image mapping audit failed; preserve partial/error evidence" }
  }
  "route-v2-external-full-prep" {
    Show-ExpHeader -ExpId "EXTERNAL-FULL-PREP" -Config "configs/tools/route_v2_external_full_prep_v1.yaml" `
      -Dataset "pinned SciEGQA 837 evidence pages; candidates only" -Output "artifacts/route_v2_external/full_prep_v1/<timestamp>/"
    & uv run --offline --no-sync python scripts/prepare_route_v2_external_full.py
    if ($LASTEXITCODE -ne 0) { throw "external full preparation failed; retain evidence" }
  }
  "route-v2-external-final-review" {
    Show-ExpHeader -ExpId "EXTERNAL-FINAL-REVIEW" -Config "scripts/review_route_v2_external_pages.py" `
      -Dataset "fixed eight-page identity/coordinate/text contract only" -Output "artifacts/route_v2_external/preparation_v1/<timestamp>_final_review/"
    & uv run --offline --no-sync python scripts/review_route_v2_external_pages.py
    if ($LASTEXITCODE -ne 0) { throw "external final review failed; retain evidence" }
  }
  "route-v2-external-encoding" {
    Assert-UvColpaliCuda
    Show-ExpHeader -ExpId "EXTERNAL-ENCODING" -Config "configs/tools/route_v2_external_encoding_v1.yaml" `
      -Dataset "pinned SciEGQA 1623 questions / 837 pages / 9746 candidates; encoding only" -Output "artifacts/route_v2_external/encoding_v1/<timestamp>/"
    & uv run --offline --no-sync python scripts/cache_route_v2_external.py
    if ($LASTEXITCODE -ne 0) { throw "external encoding failed; cache is not ready" }
  }
  "route-v2-external-encoding-tests" {
    & uv run --offline --no-sync ruff check scripts/cache_route_v2_external.py src/layoutpatch/retrieval/colpali_layout.py src/layoutpatch/retrieval/route_v2_layout.py src/layoutpatch/retrieval/route_v2_query_cache.py tests/retrieval/test_route_v2_layout.py tests/retrieval/test_route_v2_query_cache.py tests/datasets/test_external_image_review.py
    if ($LASTEXITCODE -ne 0) { throw "external encoding lint failed" }
    & uv run --offline --no-sync pytest tests/retrieval/test_route_v2_layout.py tests/retrieval/test_route_v2_query_cache.py tests/datasets/test_external_image_review.py
    if ($LASTEXITCODE -ne 0) { throw "external encoding tests failed" }
  }
  "route-v2-external-eval-tests" {
    & uv run --offline --no-sync ruff check scripts/run_route_v2_external.py src/layoutpatch/evaluation/external_localization.py tests/retrieval/test_route_v2_external.py
    if ($LASTEXITCODE -ne 0) { throw "external evaluation lint failed" }
    & uv run --offline --no-sync pytest tests/retrieval/test_route_v2_external.py
    if ($LASTEXITCODE -ne 0) { throw "external evaluation synthetic tests failed" }
  }
  "route-v2-external-eval-preflight" {
    Show-ExpHeader -ExpId "EXP-017-PREFLIGHT" -Config "configs/experiments/route_v2_external_eval_v1.yaml" `
      -Dataset "pinned SciEGQA 1623 questions / 837 correct pages / 1941 units" -Output "stdout only; read-only"
    & uv run --offline --no-sync python scripts/run_route_v2_external.py preflight
    if ($LASTEXITCODE -ne 0) { throw "external evaluation preflight failed; do not score" }
  }
  "route-v2-external-eval" {
    Assert-UvColpaliCuda
    Show-ExpHeader -ExpId "EXP-017" -Config "configs/experiments/route_v2_external_eval_v1.yaml" `
      -Dataset "pinned SciEGQA given-correct-page localization; 1623 questions / 1941 units" -Output "runs/retrieval/route_v2_external_eval_v1/<timestamp>/"
    & uv run --offline --no-sync python scripts/run_route_v2_external.py run
    if ($LASTEXITCODE -ne 0) { throw "EXP-017 failed; preserve failure and do not retry automatically" }
  }
  "route-v2-external-eval-verify" {
    Show-ExpHeader -ExpId "EXP-017-VERIFY" -Config "configs/experiments/route_v2_external_eval_v1.yaml" `
      -Dataset "saved EXP-017 predictions and frozen gold/candidates only" -Output "stdout only; read-only"
    & uv run --offline --no-sync python scripts/run_route_v2_external.py verify
    if ($LASTEXITCODE -ne 0) { throw "EXP-017 saved result verification failed" }
  }
  "route-v2-e-tests" {
    & uv run --offline --no-sync ruff check src/layoutpatch/retrieval/route_v2_candidate.py scripts/run_route_v2_E_supplement.py tests/retrieval/test_route_v2_candidate.py
    if ($LASTEXITCODE -ne 0) { throw "EXP-018 E targeted lint failed" }
    & uv run --offline --no-sync pytest tests/retrieval/test_route_v2_candidate.py tests/retrieval/test_route_v2_exp1.py tests/retrieval/test_route_v2_external.py
    if ($LASTEXITCODE -ne 0) { throw "EXP-018 E targeted tests failed" }
  }
  "route-v2-e-check" {
    Show-ExpHeader -ExpId "EXP-018-CHECK" -Config "configs/experiments/route_v2_E_supplement_v1.yaml" `
      -Dataset "synthetic candidates only; implementation check, not tuning" -Output "artifacts/route_v2_E_supplement_check/<timestamp>/"
    & uv run --offline --no-sync python scripts/run_route_v2_E_supplement.py check
    if ($LASTEXITCODE -ne 0) { throw "EXP-018 E training-side check failed; do not train" }
  }
  "route-v2-e-train" {
    Assert-UvColpaliCuda
    Show-ExpHeader -ExpId "EXP-018-TRAIN" -Config "configs/experiments/route_v2_E_supplement_v1.yaml" `
      -Dataset "original D source_train start set; source_val checkpoint selection only" -Output "runs/retrieval/route_v2_E_supplement_v1/<timestamp>/"
    & uv run --offline --no-sync python scripts/run_route_v2_E_supplement.py train
    if ($LASTEXITCODE -ne 0) { throw "EXP-018 E training hard stop; no automatic retry" }
  }
  "route-v2-e-external" {
    Assert-UvColpaliCuda
    Show-ExpHeader -ExpId "EXP-018-EXTERNAL" -Config "configs/experiments/route_v2_E_supplement_v1.yaml" `
      -Dataset "fixed SciEGQA 1623 questions / 1941 units; reuse old predictions" -Output "runs/retrieval/route_v2_E_external_supplement_v1/<timestamp>/"
    & uv run --offline --no-sync python scripts/run_route_v2_E_supplement.py external
    if ($LASTEXITCODE -ne 0) { throw "EXP-018 external supplement hard stop; no retry or tuning" }
  }
  "route-v2-e-verify" {
    Show-ExpHeader -ExpId "EXP-018-VERIFY" -Config "configs/experiments/route_v2_E_supplement_v1.yaml" `
      -Dataset "saved old plus E predictions and fixed gold/candidates" -Output "stdout only; read-only"
    & uv run --offline --no-sync python scripts/run_route_v2_E_supplement.py verify
    if ($LASTEXITCODE -ne 0) { throw "EXP-018 saved supplement verification failed" }
  }
  "route-v2-exp3-tests" {
    & uv run --offline --no-sync ruff check src/layoutpatch/retrieval/route_v2_attribution.py scripts/run_route_v2_exp3.py tests/retrieval/test_route_v2_attribution.py
    if ($LASTEXITCODE -ne 0) { throw "EXP-016 related lint failed" }
    & uv run --offline --no-sync pytest tests/retrieval/test_route_v2_attribution.py tests/retrieval/test_route_v2_layout.py tests/retrieval/test_route_v2_exp2.py tests/retrieval/test_route_v2_exp1.py
    if ($LASTEXITCODE -ne 0) { throw "EXP-016 related tests failed" }
  }
  "route-v2-exp3" {
    Show-ExpHeader -ExpId "EXP-016" -Config "configs/experiments/route_v2_exp3_attribution.yaml" `
      -Dataset "data-roles-v1 source_train/val; dev after all nine checkpoints" -Output "runs/retrieval/route_v2_exp3_attribution/<timestamp>/"
    & uv run --offline --no-sync python scripts/run_route_v2_exp3.py
    if ($LASTEXITCODE -ne 0) { throw "EXP-016 hard stop; preserve failure; no automatic retry" }
  }
  "route-v2-exp2-result-check" {
    & uv run --offline --no-sync ruff check scripts/verify_route_v2_exp2_result.py
    if ($LASTEXITCODE -ne 0) { throw "EXP-015 result verifier lint failed" }
    & uv run --offline --no-sync python scripts/verify_route_v2_exp2_result.py
    if ($LASTEXITCODE -ne 0) { throw "EXP-015 saved result verification failed" }
  }
  "route-v2-exp2-verify" {
    & uv run --offline --no-sync python scripts/verify_route_v2_exp2.py
    if ($LASTEXITCODE -ne 0) { throw "EXP-015 protocol/input hard stop" }
  }
  "route-v2-d-dev-nodes" {
    Show-ExpHeader -ExpId "EXP-015-DEV-CACHE" -Config "fixed d_nodes_v1 encoding" `
      -Dataset "source_dev candidates; encoding only" -Output "artifacts/route_v2_data/d_nodes_dev_v1/"
    & uv run --offline --no-sync python scripts/cache_route_v2_nodes.py --dev-only
    if ($LASTEXITCODE -ne 0) { throw "dev node cache hard stop" }
  }
  "route-v2-d-verify" {
    & uv run --offline --no-sync python scripts/verify_route_v2_d_prep.py
    if ($LASTEXITCODE -ne 0) { throw "D preparation verification failed" }
  }
  "route-v2-exp2" {
    Show-ExpHeader -ExpId "EXP-015" -Config "configs/experiments/route_v2_exp2_D.yaml" `
      -Dataset "source_train/val; dev only after all D checkpoints" -Output "runs/retrieval/route_v2_exp2_D/<timestamp>/"
    & uv run --offline --no-sync python scripts/run_route_v2_exp2.py
    if ($LASTEXITCODE -ne 0) { throw "EXP-015 stopped; preserve failure" }
  }
  "route-v2-d-tests" {
    & uv run --offline --no-sync ruff check src/layoutpatch/retrieval/route_v2_layout.py scripts/cache_route_v2_nodes.py scripts/route_v2_d_smoke.py scripts/run_route_v2_exp2.py scripts/verify_route_v2_exp2.py tests/retrieval/test_route_v2_exp2.py scripts/verify_route_v2_d_prep.py scripts/run_route_v2_exp1.py src/layoutpatch/retrieval/route_v2_exp1.py tests/retrieval/test_route_v2_layout.py
    if ($LASTEXITCODE -ne 0) { throw "D lint failed" }
    & uv run --offline --no-sync pytest tests/retrieval/test_route_v2_exp2.py tests/retrieval/test_route_v2_layout.py tests/retrieval/test_route_v2_exp1.py tests/retrieval/test_fusion_v2.py tests/retrieval/test_route_v2_scoring.py
    if ($LASTEXITCODE -ne 0) { throw "D tests failed" }
  }
  "route-v2-d-nodes" {
    Show-ExpHeader -ExpId "EXP-015-PREP" -Config "scripts/cache_route_v2_nodes.py" `
      -Dataset "source_train/source_val candidates only" -Output "artifacts/route_v2_data/d_nodes_v1/"
    & uv run --offline --no-sync python scripts/cache_route_v2_nodes.py
    if ($LASTEXITCODE -ne 0) { throw "D nodes hard stop" }
  }
  "route-v2-d-smoke" {
    Show-ExpHeader -ExpId "EXP-015-SMOKE" -Config "scripts/route_v2_d_smoke.py; seed42/16 questions/200 steps" `
      -Dataset "fixed source_train only" -Output "artifacts/route_v2_d_smoke/<timestamp>/"
    & uv run --offline --no-sync python scripts/route_v2_d_smoke.py
    if ($LASTEXITCODE -ne 0) { throw "D smoke failed; preserve run" }
  }
  "route-v2-exp1-verify" {
    Show-ExpHeader -ExpId "EXP-014-VERIFY" -Config "scripts/verify_route_v2_exp1.py" `
      -Dataset "data-roles-v1; signatures only; no scoring" -Output "artifacts/route_v2_data/exp1_verification/<timestamp>/"
    & uv run --offline --no-sync python scripts/verify_route_v2_exp1.py
    if ($LASTEXITCODE -ne 0) { throw "EXP-014 hard stop: verification failed" }
  }
  "route-v2-exp1-result-check" {
    & uv run --offline --no-sync ruff check scripts/verify_route_v2_exp1_result.py
    if ($LASTEXITCODE -ne 0) { throw "result verifier lint failed" }
    & uv run --offline --no-sync python scripts/verify_route_v2_exp1_result.py
    if ($LASTEXITCODE -ne 0) { throw "saved EXP-014 result verification failed" }
  }
  "route-v2-exp1-tests" {
    & uv run --offline --no-sync ruff check scripts/verify_route_v2_exp1.py scripts/run_route_v2_exp1.py src/layoutpatch/retrieval/route_v2_exp1.py tests/retrieval/test_route_v2_exp1.py
    if ($LASTEXITCODE -ne 0) { throw "EXP-014 lint failed" }
    & uv run --offline --no-sync pytest tests/retrieval/test_route_v2_exp1.py tests/retrieval/test_route_v2_scoring.py tests/retrieval/test_route_v2_query_cache.py tests/evaluation/test_localization.py tests/datasets/test_route_v2_regions.py tests/datasets/test_route_v2_split.py
    if ($LASTEXITCODE -ne 0) { throw "EXP-014 tests failed" }
  }
  "route-v2-exp1" {
    Show-ExpHeader -ExpId "EXP-014" -Config "configs/experiments/route_v2_exp1.yaml (frozen)" `
      -Dataset "data-roles-v1 source_train/source_val; source_dev once after all selections" -Output "runs/retrieval/route_v2_exp1/<timestamp>/"
    & uv run --offline --no-sync python scripts/run_route_v2_exp1.py
    if ($LASTEXITCODE -ne 0) { throw "EXP-014 hard stop; preserve failed run" }
  }
  "route-v2-cache-tests" {
    & uv run --offline --no-sync ruff check scripts/cache_route_v2_queries.py scripts/route_v2_smoke.py src/layoutpatch/retrieval/route_v2_query_cache.py src/layoutpatch/retrieval/route_v2_scoring.py tests/retrieval/test_route_v2_query_cache.py tests/retrieval/test_route_v2_scoring.py
    if ($LASTEXITCODE -ne 0) { throw "route-v2 lint failed" }
    & uv run --offline --no-sync pytest tests/retrieval/test_route_v2_query_cache.py tests/retrieval/test_route_v2_scoring.py tests/datasets/test_route_v2_split.py tests/datasets/test_route_v2_regions.py tests/evaluation/test_localization.py
    if ($LASTEXITCODE -ne 0) { throw "route-v2 tests failed" }
  }
  "route-v2-smoke" {
    Show-ExpHeader -ExpId "ROUTE-V2-SMOKE" -Config "scripts/route_v2_smoke.py (route-v2-smoke-v1)" `
      -Dataset "data-roles-v1 source_train, 16 fixed questions" -Output "artifacts/route_v2_smoke/<timestamp>/"
    Write-Host "RUN: uv run --offline --no-sync python scripts/route_v2_smoke.py"
    & uv run --offline --no-sync python scripts/route_v2_smoke.py
    if ($LASTEXITCODE -eq 2) { throw "route-v2-smoke stopped: precondition failed (see preconditions.json)" }
    if ($LASTEXITCODE -ne 0) { throw "route-v2-smoke failed" }
  }
}
