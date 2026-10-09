"""一次性运行冻结的 SciEGQA 给定正确页外部定位评测。"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import polars as pl  # noqa: E402
import torch  # noqa: E402
import yaml  # noqa: E402

from layoutpatch.evaluation.external_localization import (  # noqa: E402
    METADATA_KEYS,
    compute_analytical_results,
    gold_boxes_from_relative,
    validate_prediction_metrics,
)
from layoutpatch.evaluation.localization import (  # noqa: E402
    question_macro,
    rank_candidates,
    unit_metrics,
)
from layoutpatch.retrieval.colpali_layout import split_page_embedding  # noqa: E402
from layoutpatch.retrieval.route_v2_attribution import InputAblatedD  # noqa: E402
from layoutpatch.retrieval.route_v2_exp1 import finite, memory_guard  # noqa: E402
from layoutpatch.retrieval.route_v2_layout import LayoutPatchD, external_node_text  # noqa: E402
from layoutpatch.retrieval.route_v2_query_cache import file_sha256  # noqa: E402
from layoutpatch.retrieval.route_v2_scoring import (  # noqa: E402
    PatchAdapter,
    area_scores,
    patch_iou_matrix,
    patch_scores,
    region_scores,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/experiments/route_v2_external_eval_v1.yaml"
EXPECTED_ENCODING_MANIFEST_SHA256 = "87386a31e2300093d59f0f0c5bd81ecac7161292ab9df49736581ecf2217aa4f"


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def write_json(path: Path, value: object, *, exclusive: bool = True) -> None:
    mode = "x" if exclusive else "w"
    with path.open(mode, encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def sha256(path: Path) -> str:
    return file_sha256(path)


def safe_repo_path(value: str, *, label: str) -> Path:
    """Resolve a manifest/config path only when it is relative and stays in the repository."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty repository-relative path")
    raw = Path(value)
    if raw.is_absolute() or raw.anchor or ".." in raw.parts:
        raise ValueError(f"{label} must not be absolute or contain traversal")
    resolved = (ROOT / raw).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes repository root") from exc
    return resolved


def safe_run_path(run_root: Path, value: str, *, label: str) -> Path:
    """Resolve a cache member only when it is relative and stays in its immutable run."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty run-relative path")
    raw = Path(value)
    if raw.is_absolute() or raw.anchor or ".." in raw.parts:
        raise ValueError(f"{label} must not be absolute or contain traversal")
    base = run_root.resolve()
    resolved = (base / raw).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"{label} escapes encoding run") from exc
    return resolved


def load_encoding_manifest(cfg: dict) -> tuple[Path, dict]:
    manifest_path = safe_repo_path(cfg["encoding_manifest"], label="encoding_manifest")
    if cfg["encoding_manifest_sha256"] != EXPECTED_ENCODING_MANIFEST_SHA256:
        raise ValueError("frozen encoding manifest hash binding changed")
    manifest_hash = sha256(manifest_path)
    if manifest_hash != EXPECTED_ENCODING_MANIFEST_SHA256:
        raise ValueError("frozen encoding manifest hash mismatch")
    return manifest_path, json.loads(manifest_path.read_text(encoding="utf-8"))


def checked_result_run(cfg: dict, run: Path) -> Path:
    output_root = safe_repo_path(cfg["output"], label="output")
    resolved = (ROOT / run).resolve() if not run.is_absolute() else run.resolve()
    try:
        resolved.relative_to(output_root.resolve())
    except ValueError as exc:
        raise ValueError("result run escapes configured output") from exc
    if resolved == output_root.resolve():
        raise ValueError("result run must be a timestamp directory")
    return resolved


def load_config() -> dict:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if cfg.get("status") != "frozen" or cfg.get("experiment_id") != "EXP-017":
        raise ValueError("external evaluation config is not frozen EXP-017")
    if cfg["methods"] != ["A", "B", "C", "C-wide", "D", "D-no-text"]:
        raise ValueError("six-method comparison changed")
    if cfg["trained_methods"] != ["C", "C-wide", "D", "D-no-text"] or cfg["seeds"] != [0, 1, 2]:
        raise ValueError("trained methods or seeds changed")
    stats = cfg["statistics"]
    if stats["primary_comparisons"] != ["D-no-text-A", "D-no-text-B", "D-no-text-C-wide"]:
        raise ValueError("primary comparisons changed")
    if stats["secondary_comparisons"] != ["D-no-text-D", "D-no-text-C"]:
        raise ValueError("secondary comparisons changed")
    if stats["bootstrap"] != {"iterations": 2000, "seed": 0, "unit": "document", "confidence": 0.95}:
        raise ValueError("bootstrap changed")
    multiple = stats["multiple_comparisons"]
    if multiple["method"] != "Bonferroni_percentile_document_bootstrap_intervals" or multiple["family_size"] != 3 or multiple["family_alpha"] != 0.05:
        raise ValueError("multiple-comparison correction changed")
    comparison_path = safe_repo_path(cfg["comparison_config"], label="comparison_config")
    comparison = yaml.safe_load(comparison_path.read_text(encoding="utf-8"))
    plan = comparison["external_evaluation_plan"]
    if plan["primary_metric"] != "hit1@0.5" or plan["comparisons"] != stats["primary_comparisons"]:
        raise ValueError("frozen comparison plan mismatch")
    if plan["secondary_comparisons"] != stats["secondary_comparisons"]:
        raise ValueError("frozen secondary plan mismatch")
    if plan["bootstrap"] != stats["bootstrap"]:
        raise ValueError("frozen bootstrap plan mismatch")
    if comparison["weights"]["identity_sha256"] != cfg["weights_manifest_sha256"]:
        raise ValueError("weights identity binding mismatch")
    return cfg


def load_candidates(cfg: dict) -> tuple[dict[str, list[dict]], dict[str, list[float]]]:
    path = safe_repo_path(cfg["candidates"], label="candidates")
    if sha256(path) != cfg["candidates_sha256"]:
        raise ValueError("external candidates hash mismatch")
    grouped: dict[str, list[dict]] = defaultdict(list)
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                row = json.loads(line)
                grouped[row["page_id"]].append(row)
    page_sizes = {}
    for page_id, rows in grouped.items():
        rows.sort(key=lambda row: row["layout_id"])
        if [row["layout_id"] for row in rows] != sorted({row["layout_id"] for row in rows}):
            raise ValueError(f"candidate order/uniqueness mismatch: {page_id}")
        sizes = {tuple(map(float, row["page_size"])) for row in rows}
        if len(sizes) != 1:
            raise ValueError(f"candidate page size mismatch: {page_id}")
        page_sizes[page_id] = list(next(iter(sizes)))
    if len(grouped) != cfg["denominators"]["unique_pages"] or sum(map(len, grouped.values())) != cfg["denominators"]["candidates"]:
        raise ValueError("candidate denominator mismatch")
    return dict(grouped), page_sizes


def build_units(cfg: dict, page_sizes: dict[str, list[float]]) -> list[dict]:
    path = safe_repo_path(cfg["annotations"], label="annotations")
    if sha256(path) != cfg["annotations_sha256"]:
        raise ValueError("external annotations hash mismatch")
    units = []
    with path.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            row = json.loads(line)
            query_id = f"sciegqa_{index:05d}"
            doc_id = row["doc_name"].removesuffix(".pdf")
            fields = (row["evidence_page"], row["bbox"], row["rel_bbox"], row["subimg_type"])
            if len({len(value) for value in fields}) != 1:
                raise ValueError(f"annotation page alignment mismatch: {query_id}")
            for page_number, absolute, relative, kinds in zip(*fields, strict=True):
                page_id = f"{doc_id}_p{page_number - 1}"
                if page_id not in page_sizes or not absolute or len(absolute) != len(relative) or len(relative) != len(kinds):
                    raise ValueError(f"annotation unit coverage mismatch: {query_id} {page_id}")
                units.append({
                    "query_id": query_id,
                    "doc_id": doc_id,
                    "page_id": page_id,
                    "page_number": page_number,
                    "unit_id": f"{query_id}:{page_id}",
                    "role": "external_test",
                    "page_size": page_sizes[page_id],
                    "gold_boxes": gold_boxes_from_relative(relative, page_sizes[page_id]),
                    "candidate_count": None,
                    "page_overlap_excluded": False,
                })
    counts = cfg["denominators"]
    if len(units) != counts["question_page_units"] or len({unit["query_id"] for unit in units}) != counts["questions"]:
        raise ValueError("question/unit denominator mismatch")
    if len({unit["unit_id"] for unit in units}) != len(units):
        raise ValueError("duplicate external unit")
    return units


def module_for(method: str) -> torch.nn.Module:
    if method == "C":
        return PatchAdapter(hidden=256)
    if method == "C-wide":
        return PatchAdapter(hidden=1062)
    if method == "D":
        return LayoutPatchD()
    if method == "D-no-text":
        return InputAblatedD("text")
    raise ValueError(f"unregistered trained method: {method}")


def load_weights(cfg: dict, *, strict_modules: bool) -> tuple[dict, dict[tuple[str, int], dict]]:
    manifest_path = safe_repo_path(cfg["weights_manifest"], label="weights_manifest")
    if sha256(manifest_path) != cfg["weights_manifest_sha256"]:
        raise ValueError("frozen weights manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if set(manifest) != set(cfg["trained_methods"]):
        raise ValueError("weight method set mismatch")
    entries = {}
    for method in cfg["trained_methods"]:
        record = manifest[method]
        source_config = safe_repo_path(record["config"], label=f"weights.{method}.config")
        run_root = safe_repo_path(record["run"], label=f"weights.{method}.run")
        selection = safe_run_path(run_root, "checkpoint_selection.json", label=f"weights.{method}.selection")
        if sha256(source_config) != record["config_sha256"] or sha256(selection) != record["selection_sha256"]:
            raise ValueError(f"training identity mismatch: {method}")
        weights = record["weights"]
        if [row["seed"] for row in weights] != cfg["seeds"]:
            raise ValueError(f"weight seed mismatch: {method}")
        for row in weights:
            checkpoint_path = safe_repo_path(
                row["checkpoint"], label=f"weights.{method}.seed_{row['seed']}.checkpoint"
            )
            if sha256(checkpoint_path) != row["sha256"] or row["selection_role"] != "source_val":
                raise ValueError(f"checkpoint identity mismatch: {method} seed {row['seed']}")
            payload = torch.load(checkpoint_path, weights_only=True, map_location="cpu")
            required = {"seed", "epoch", "val_score", "state_dict"}
            if set(payload) != required or payload["seed"] != row["seed"] or payload["epoch"] != row["selected_epoch"]:
                raise ValueError(f"checkpoint payload mismatch: {method} seed {row['seed']}")
            if not math.isfinite(float(payload["val_score"])):
                raise ValueError("checkpoint validation score is nonfinite")
            if strict_modules:
                module = module_for(method)
                module.load_state_dict(payload["state_dict"], strict=True)
            entries[(method, row["seed"])] = {**row, "payload": payload}
    if len(entries) != 12:
        raise ValueError("expected twelve checkpoints")
    return manifest, entries


def validate_cache(cfg: dict, candidates: dict[str, list[dict]], units: list[dict]) -> tuple[dict, dict]:
    manifest_path, manifest = load_encoding_manifest(cfg)
    encoding_cfg_path = safe_repo_path(cfg["encoding_config"], label="encoding_config")
    encoding_cfg = yaml.safe_load(encoding_cfg_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "route-v2-external-encoding-v1" or manifest.get("config") != encoding_cfg:
        raise ValueError("encoding manifest/config mismatch")
    run_info_path = safe_repo_path(manifest["run_info"], label="manifest.run_info")
    run_info = json.loads(run_info_path.read_text(encoding="utf-8"))
    manifest_hash = sha256(manifest_path)
    if run_info.get("status") != "ready" or run_info.get("manifest_sha256") != manifest_hash:
        raise ValueError("encoding cache is not ready or manifest hash differs")
    if run_info.get("model_identities") != manifest.get("model_identities"):
        raise ValueError("encoding model identity mismatch")
    expected_pages = {unit["page_id"] for unit in units}
    page_records = {row["page_id"]: row for row in manifest["pages"]}
    node_records = {row["page_id"]: row for row in manifest["nodes"]}
    if set(page_records) != expected_pages or set(node_records) != expected_pages or set(candidates) != expected_pages:
        raise ValueError("page/node/candidate coverage mismatch")
    run_root = manifest_path.parent
    for page_id in sorted(expected_pages):
        page_record = page_records[page_id]
        page_path = safe_run_path(run_root, page_record["file"], label=f"pages.{page_id}.file")
        if sha256(page_path) != page_record["sha256"] or page_record["shape"] != [1031, 128]:
            raise ValueError(f"page cache hash/shape mismatch: {page_id}")
        page_payload = torch.load(page_path, weights_only=True, map_location="cpu")
        if page_payload["page_id"] != page_id or tuple(page_payload["embedding"].shape) != (1031, 128):
            raise ValueError(f"page cache payload mismatch: {page_id}")
        patches, prompt = split_page_embedding(page_payload["embedding"])
        finite(patches, "external page patches")
        finite(prompt, "external page prompt")
        node_record = node_records[page_id]
        node_path = safe_run_path(run_root, node_record["file"], label=f"nodes.{page_id}.file")
        if sha256(node_path) != node_record["sha256"] or node_record["nodes"] != len(candidates[page_id]):
            raise ValueError(f"node cache hash/count mismatch: {page_id}")
        node_payload = torch.load(node_path, weights_only=True, map_location="cpu")
        expected_ids = [row["layout_id"] for row in candidates[page_id]]
        if node_payload.get("page_id") != page_id or node_payload.get("layout_id_order") != expected_ids:
            raise ValueError(f"node cache identity/order mismatch: {page_id}")
        count = len(expected_ids)
        layout = node_payload["layout"]
        shapes = {"text": (count, 1024), "coords": (count, 6), "types": (count,), "mask": (count,), "W_raw": (1024, count), "W_attn": (1024, count), "cover_mass": (1024, 1)}
        if any(tuple(layout[key].shape) != shape for key, shape in shapes.items()) or layout["mask"].dtype != torch.bool or not bool(layout["mask"].all()):
            raise ValueError(f"node layout shape/mask mismatch: {page_id}")
        if not all(bool(torch.isfinite(value).all()) for value in layout.values() if value.is_floating_point()):
            raise ValueError(f"nonfinite node layout: {page_id}")
        for index, (candidate, metadata) in enumerate(zip(candidates[page_id], node_payload["nodes"], strict=True)):
            text, source = external_node_text(candidate)
            missing = not bool(text)
            if metadata != {"page_id": page_id, "layout_id": candidate["layout_id"], "text_source": source, "text_missing": missing, "token_length_before_truncation": metadata["token_length_before_truncation"]}:
                raise ValueError(f"node text metadata mismatch: {page_id}")
            vector = layout["text"][index]
            if missing != bool(torch.count_nonzero(vector) == 0):
                raise ValueError(f"only truly missing text may be zero: {page_id}")
            if not missing and not math.isclose(float(vector.norm()), 1.0, abs_tol=1e-4, rel_tol=0):
                raise ValueError(f"nonempty external text embedding is not normalized: {page_id}")
    query_record = manifest["queries"]
    query_path = safe_run_path(run_root, query_record["file"], label="queries.file")
    if sha256(query_path) != query_record["sha256"]:
        raise ValueError("query cache hash mismatch")
    query_payload = torch.load(query_path, weights_only=True, map_location="cpu")
    expected_queries = {unit["query_id"] for unit in units}
    if set(query_payload.get("embeddings", {})) != expected_queries or set(query_payload.get("tokens", {})) != expected_queries or set(query_record["ids"]) != expected_queries:
        raise ValueError("query cache coverage mismatch")
    pad_id = manifest["model_identities"]["colpali"]["resolved"]["pad_token_id"]
    for query_id, embedding in query_payload["embeddings"].items():
        token = query_payload["tokens"][query_id]
        if token["shape"] != list(embedding.shape) or token["attention_mask"] != [1] * len(embedding):
            raise ValueError(f"query padding/alignment mismatch: {query_id}")
        if token["input_ids"][-10:] != [pad_id] * 10 or not bool(torch.isfinite(embedding).all()):
            raise ValueError(f"query augmentation/value mismatch: {query_id}")
    return manifest, {"manifest_sha256": manifest_hash, "run_info_sha256": sha256(run_info_path), "run_info": run_info}


def preflight(cfg: dict, *, strict_modules: bool = True) -> tuple[dict, dict[tuple[str, int], dict]]:
    started = time.perf_counter()
    candidates, page_sizes = load_candidates(cfg)
    units = build_units(cfg, page_sizes)
    for unit in units:
        unit["candidate_count"] = len(candidates[unit["page_id"]])
    cache_manifest, cache = validate_cache(cfg, candidates, units)
    weights_manifest, weights = load_weights(cfg, strict_modules=strict_modules)
    report = {
        "passed": True,
        "status": "ready",
        "counts": {
            "questions": len({unit["query_id"] for unit in units}),
            "unique_pages": len(candidates),
            "question_page_units": len(units),
            "candidates": sum(map(len, candidates.values())),
            "trained_methods": len(weights_manifest),
            "checkpoints": len(weights),
        },
        "input_sha256": {
            cfg["comparison_config"]: sha256(
                safe_repo_path(cfg["comparison_config"], label="comparison_config")
            ),
            cfg["encoding_config"]: sha256(
                safe_repo_path(cfg["encoding_config"], label="encoding_config")
            ),
            cfg["encoding_manifest"]: cache["manifest_sha256"],
            cfg["weights_manifest"]: cfg["weights_manifest_sha256"],
            cfg["annotations"]: cfg["annotations_sha256"],
            cfg["candidates"]: cfg["candidates_sha256"],
        },
        "model_identities": cache_manifest["model_identities"],
        "checks": [
            "encoding_ready_and_self_hashed",
            "837_page_and_node_files_hashed_loaded_finite",
            "1941_question_page_units_and_all_node_pages_covered",
            "image_1024_plus_prompt_7_token_contract",
            "query_attention_padding_removed_and_augmentation_preserved",
            "external_nonempty_text_encoded_and_true_missing_text_zero_only",
            "twelve_source_val_checkpoints_hashed_and_strictly_loaded_with_training_classes",
        ],
        "seconds": time.perf_counter() - started,
    }
    return report, weights


class SavedInputs:
    """Only candidates and gold needed to verify immutable saved predictions."""

    def __init__(self, cfg: dict):
        self.candidates, page_sizes = load_candidates(cfg)
        self.units = build_units(cfg, page_sizes)
        for unit in self.units:
            unit["candidate_count"] = len(self.candidates[unit["page_id"]])

    def boxes(self, unit: dict) -> tuple[list[list[float]], list[int]]:
        rows = self.candidates[unit["page_id"]]
        return [row["bbox"] for row in rows], [row["layout_id"] for row in rows]


class ExternalInputs:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.candidates, page_sizes = load_candidates(cfg)
        self.units = build_units(cfg, page_sizes)
        for unit in self.units:
            unit["candidate_count"] = len(self.candidates[unit["page_id"]])
        self.manifest_path, manifest = load_encoding_manifest(cfg)
        self.run_root = self.manifest_path.parent
        self.page_records = {row["page_id"]: row for row in manifest["pages"]}
        self.node_records = {row["page_id"]: row for row in manifest["nodes"]}
        query_path = safe_run_path(self.run_root, manifest["queries"]["file"], label="queries.file")
        self.queries = torch.load(query_path, weights_only=True, map_location="cpu")["embeddings"]
        self.pages: dict[str, torch.Tensor] = {}
        self.layouts: dict[str, dict[str, torch.Tensor]] = {}
        self.geometry: dict[str, torch.Tensor] = {}

    def boxes(self, unit: dict) -> tuple[list[list[float]], list[int]]:
        rows = self.candidates[unit["page_id"]]
        return [row["bbox"] for row in rows], [row["layout_id"] for row in rows]

    def iou(self, unit: dict) -> torch.Tensor:
        page_id = unit["page_id"]
        if page_id not in self.geometry:
            self.geometry[page_id] = patch_iou_matrix(self.boxes(unit)[0], unit["page_size"])
        return self.geometry[page_id]

    def item(self, unit: dict, *, layout: bool) -> dict:
        page_id = unit["page_id"]
        if page_id not in self.pages:
            record = self.page_records[page_id]
            path = safe_run_path(self.run_root, record["file"], label=f"pages.{page_id}.file")
            if sha256(path) != record["sha256"]:
                raise ValueError(f"page changed after preflight: {page_id}")
            payload = torch.load(path, weights_only=True, map_location="cpu")
            patches, prompt = split_page_embedding(payload["embedding"])
            finite(patches, "cached external patches")
            finite(prompt, "cached external prompt")
            self.pages[page_id] = patches.float()
        result = {"query": self.queries[unit["query_id"]].float(), "patches": self.pages[page_id]}
        if layout:
            if page_id not in self.layouts:
                record = self.node_records[page_id]
                path = safe_run_path(self.run_root, record["file"], label=f"nodes.{page_id}.file")
                if sha256(path) != record["sha256"]:
                    raise ValueError(f"node cache changed after preflight: {page_id}")
                payload = torch.load(path, weights_only=True, map_location="cpu")
                if payload["layout_id_order"] != self.boxes(unit)[1]:
                    raise ValueError(f"node/candidate order changed: {page_id}")
                self.layouts[page_id] = payload["layout"]
            result["layout"] = self.layouts[page_id]
        return result


def score_method(data: ExternalInputs, method: str, module: torch.nn.Module | None, device: str) -> list[dict]:
    rows = []
    if module is not None:
        module.eval()
    needs_layout = method.startswith(("D_seed_", "D-no-text_seed_"))
    with torch.no_grad():
        for unit in data.units:
            boxes, ids = data.boxes(unit)
            if method == "A":
                scores = torch.tensor(area_scores(boxes), dtype=torch.float32)
            else:
                item = data.item(unit, layout=needs_layout)
                patches = item["patches"].to(device)
                if module is not None:
                    if needs_layout:
                        layout = {key: value.to(device) for key, value in item["layout"].items()}
                        patches = module(patches, layout)
                    else:
                        patches = module(patches)
                patch = patch_scores(item["query"].to(device), patches)
                finite(patch, "external evaluation patch scores")
                scores = region_scores(patch, data.iou(unit).to(device)).cpu()
            allowed = data.iou(unit).sum(-1) == 0
            if bool(torch.isnan(scores).any()) or bool(torch.isposinf(scores).any()) or bool((torch.isneginf(scores) & ~allowed).any()):
                raise FloatingPointError(f"invalid external candidate scores: {unit['unit_id']}")
            order = rank_candidates(scores.tolist(), ids)
            ranked_boxes = [boxes[index] for index in order]
            metrics = unit_metrics(ranked_boxes, unit["gold_boxes"], unit["page_size"])
            if not all(math.isfinite(value) for value in metrics.values()):
                raise FloatingPointError(f"nonfinite external metric: {unit['unit_id']}")
            rows.append({
                "query_id": unit["query_id"],
                "doc_id": unit["doc_id"],
                "page_id": unit["page_id"],
                "unit_id": unit["unit_id"],
                "role": unit["role"],
                "method": method,
                "candidate_count": len(boxes),
                "page_overlap_excluded": False,
                "ranked_layout_ids": [ids[index] for index in order],
                "ranked_scores": [float(scores[index]) if torch.isfinite(scores[index]) else None for index in order],
                **metrics,
            })
            memory_guard(device, 12)
    return rows


def question_rows(methods: dict[str, list[dict]]) -> list[dict]:
    result = []
    for method in sorted(methods):
        keys = [key for key in methods[method][0] if key not in METADATA_KEYS]
        macros = {key: question_macro(methods[method], key) for key in keys}
        for query_id in sorted(macros[keys[0]]):
            result.append({"method": method, "query_id": query_id, **{key: macros[key][query_id] for key in keys}})
    return result


def analytical_equal(actual: object, expected: object, path: str = "metrics") -> None:
    if isinstance(actual, dict) and isinstance(expected, dict):
        if set(actual) != set(expected):
            raise ValueError(f"{path} keys differ")
        for key in actual:
            analytical_equal(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(f"{path} list length differs")
        for index, (left, right) in enumerate(zip(actual, expected, strict=True)):
            analytical_equal(left, right, f"{path}[{index}]")
    elif isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        if not math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=1e-12):
            raise ValueError(f"{path} differs")
    elif actual != expected:
        raise ValueError(f"{path} differs")


def verify_saved(run: Path, cfg: dict) -> dict:
    started = time.perf_counter()
    data = SavedInputs(cfg)
    rows = pl.read_parquet(run / "predictions.parquet").to_dicts()
    methods: dict[str, list[dict]] = defaultdict(list)
    units = {unit["unit_id"]: unit for unit in data.units}
    for row in rows:
        unit = units.get(row["unit_id"])
        if unit is None or row["query_id"] != unit["query_id"] or row["page_id"] != unit["page_id"]:
            raise ValueError("saved prediction unit identity mismatch")
        boxes, ids = data.boxes(unit)
        ranked_ids = row["ranked_layout_ids"]
        if len(ranked_ids) != len(ids) or set(ranked_ids) != set(ids) or row["candidate_count"] != len(ids):
            raise ValueError(f"saved candidate permutation mismatch: {row['unit_id']}")
        lookup = {layout_id: box for layout_id, box in zip(ids, boxes, strict=True)}
        validate_prediction_metrics(row, [lookup[layout_id] for layout_id in ranked_ids], unit["gold_boxes"], unit["page_size"])
        methods[row["method"]].append(row)
    analytical = compute_analytical_results(methods, data.units, cfg)
    saved_metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    analytical_equal(analytical, saved_metrics["analytical"])
    expected_questions = question_rows(dict(methods))
    actual_questions = pl.read_parquet(run / "question_scores.parquet").to_dicts()
    analytical_equal(actual_questions, expected_questions, "question_scores")
    return {
        "passed": True,
        "predictions": len(rows),
        "question_rows": len(actual_questions),
        "methods": len(methods),
        "units_per_method": len(data.units),
        "unit_metrics_recomputed": True,
        "question_macro_recomputed": True,
        "joint_document_bootstrap_recomputed": True,
        "model_scoring_reexecuted": False,
        "seconds": time.perf_counter() - started,
    }


def capture_identity(out: Path, cfg: dict, preflight_report: dict) -> dict:
    names = [
        "scripts/run_route_v2_external.py",
        "src/layoutpatch/evaluation/external_localization.py",
        "src/layoutpatch/evaluation/localization.py",
        "src/layoutpatch/retrieval/route_v2_scoring.py",
        "src/layoutpatch/retrieval/route_v2_exp1.py",
        "src/layoutpatch/retrieval/route_v2_attribution.py",
        "src/layoutpatch/retrieval/route_v2_layout.py",
        "src/layoutpatch/retrieval/colpali_layout.py",
        "configs/experiments/route_v2_external_eval_v1.yaml",
        cfg["comparison_config"],
        cfg["encoding_config"],
    ]
    hashes = {}
    for name in names:
        source = safe_repo_path(name, label=f"identity source {name}")
        target = out / "code" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        hashes[name] = sha256(source)
    write_json(out / "code_identity.json", hashes)
    write_json(out / "input_identity.json", preflight_report)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip() or "unknown"
    diff = subprocess.run(["git", "diff", "--binary", "HEAD", "--", *names], cwd=ROOT, capture_output=True, check=False).stdout
    (out / "workspace.patch").write_bytes(diff)
    return {"git_commit": commit, "code_sha256": hashes, "workspace_patch_sha256": sha256(out / "workspace.patch")}


def find_completed(cfg: dict) -> Path | None:
    root = safe_repo_path(cfg["output"], label="output")
    if not root.is_dir():
        return None
    matches = []
    for run in sorted((path for path in root.iterdir() if path.is_dir()), reverse=True):
        try:
            saved_cfg = json.loads((run / "config.json").read_text(encoding="utf-8"))
            info = json.loads((run / "run_info.json").read_text(encoding="utf-8"))
            verification = json.loads((run / "result_verification.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if saved_cfg == cfg and info.get("status") == "completed" and verification.get("passed") is True:
            matches.append(run)
    if len(matches) > 1:
        raise ValueError("multiple completed runs exist for the same frozen config")
    return matches[0] if matches else None


def summary_lines(metrics: dict, run: Path) -> list[str]:
    analytical = metrics["analytical"]
    lines = [
        "# EXP-017 SciEGQA frozen external localization",
        "",
        "给定正确页面的候选区域定位；不是端到端页面检索。B 是冻结传播基线，不是 Snappy 原论文完整复现。",
        "",
        f"结果目录：`{rel(run)}`",
        "",
        "|方法|hit1@0.5|seed std|top1_iou|cov@5|gold_recall@5@0.5|",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in ("A", "B"):
        values = analytical["methods"][name]["all"]["metrics"]
        lines.append(f"|{name}|{values['hit1@0.5']:.10f}|—|{values['top1_iou']:.10f}|{values['cov@5']:.10f}|{values['gold_recall@5@0.5']:.10f}|")
    for name in ("C", "C-wide", "D", "D-no-text"):
        values = analytical["seed_aggregates"][name]["all"]
        lines.append(f"|{name}|{values['metrics']['hit1@0.5']:.10f}|{values['std']['hit1@0.5']:.10f}|{values['metrics']['top1_iou']:.10f}|{values['metrics']['cov@5']:.10f}|{values['metrics']['gold_recall@5@0.5']:.10f}|")
    lines += ["", "## 配对统计", ""]
    for name, value in analytical["paired"].items():
        text = f"- {name}: delta={value['mean_diff']:.10f}; 95% CI=[{value['ci95_low']:.10f}, {value['ci95_high']:.10f}]"
        if value["comparison_role"] == "primary":
            text += f"; Bonferroni CI=[{value['bonferroni_ci_low']:.10f}, {value['bonferroni_ci_high']:.10f}]"
        lines.append(text)
    lines += ["", "外部计划未冻结最小有意义差值；只区分区间是否高于零，不事后设阈值。", "完整辅助指标、seed、M>=2、随机期望、Oracle、面积分位数、分母、耗时和显存见 `metrics.json`。"]
    return lines


def run_evaluation(cfg: dict) -> Path:
    completed = find_completed(cfg)
    if completed is not None:
        verification = verify_saved(completed, cfg)
        print(
            json.dumps(
                {"status": "reused", "run_dir": str(completed), "verification": verification},
                ensure_ascii=False,
            ),
            flush=True,
        )
        return completed
    preflight_report, weights = preflight(cfg, strict_modules=True)
    out = safe_repo_path(cfg["output"], label="output") / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    info = {"status": "started", "scoring_started": False, "training": False, "page_retrieval": False}
    try:
        write_json(out / "config.json", cfg)
        write_json(out / "preflight.json", preflight_report)
        info.update(capture_identity(out, cfg, preflight_report))
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable for frozen external scoring")
        torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
        info.update({"python": sys.version, "torch": str(torch.__version__), "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(), "deterministic_algorithms": True, "tf32": False})
        data = ExternalInputs(cfg)
        info["scoring_started"] = True
        methods = {}
        efficiency = {}
        peak = 0
        for method in ("A", "B"):
            torch.cuda.reset_peak_memory_stats()
            method_started = time.perf_counter()
            methods[method] = score_method(data, method, None, cfg["device"])
            efficiency[method] = {"scoring_seconds": time.perf_counter() - method_started, "peak_allocated_bytes": torch.cuda.max_memory_allocated(), "peak_reserved_bytes": torch.cuda.max_memory_reserved(), "model_passes": 0 if method == "A" else 1}
            peak = max(peak, efficiency[method]["peak_allocated_bytes"], efficiency[method]["peak_reserved_bytes"])
            print(json.dumps({"method": method, "seconds": efficiency[method]["scoring_seconds"]}), flush=True)
        for method in cfg["trained_methods"]:
            for seed in cfg["seeds"]:
                label = f"{method}_seed_{seed}"
                payload = weights[(method, seed)]["payload"]
                module = module_for(method).to(cfg["device"])
                module.load_state_dict(payload["state_dict"], strict=True)
                torch.cuda.reset_peak_memory_stats()
                method_started = time.perf_counter()
                methods[label] = score_method(data, label, module, cfg["device"])
                efficiency[label] = {"scoring_seconds": time.perf_counter() - method_started, "peak_allocated_bytes": torch.cuda.max_memory_allocated(), "peak_reserved_bytes": torch.cuda.max_memory_reserved(), "trainable_parameters": sum(parameter.numel() for parameter in module.parameters()), "model_passes": 1, "checkpoint": weights[(method, seed)]["checkpoint"], "checkpoint_sha256": weights[(method, seed)]["sha256"]}
                peak = max(peak, efficiency[label]["peak_allocated_bytes"], efficiency[label]["peak_reserved_bytes"])
                print(json.dumps({"method": label, "seconds": efficiency[label]["scoring_seconds"], "peak_reserved_bytes": efficiency[label]["peak_reserved_bytes"]}), flush=True)
                del module
                torch.cuda.empty_cache()
        predictions = [row for method in sorted(methods) for row in methods[method]]
        pl.DataFrame(predictions).write_parquet(out / "predictions.parquet")
        questions = question_rows(methods)
        pl.DataFrame(questions).write_parquet(out / "question_scores.parquet")
        analytical = compute_analytical_results(methods, data.units, cfg)
        metrics = {
            "analytical": analytical,
            "denominators": cfg["denominators"],
            "efficiency": efficiency,
            "total_model_scoring_passes": 13,
            "A_computed_once": True,
            "B_computed_once": True,
            "peak_vram_bytes": peak,
            "vram_budget_bytes": 12 * 1024**3,
            "weights_manifest": cfg["weights_manifest"],
            "weights_manifest_sha256": cfg["weights_manifest_sha256"],
            "input_manifest": cfg["encoding_manifest"],
            "input_manifest_sha256": preflight_report["input_sha256"][cfg["encoding_manifest"]],
        }
        write_json(out / "metrics.json", metrics)
        verification = verify_saved(out, cfg)
        write_json(out / "result_verification.json", verification)
        lines = summary_lines(metrics, out)
        (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        for name, digest in info["code_sha256"].items():
            if sha256(safe_repo_path(name, label=f"identity source {name}")) != digest:
                raise ValueError(f"code/config changed during external run: {name}")
        for name, digest in preflight_report["input_sha256"].items():
            if sha256(safe_repo_path(name, label=f"input {name}")) != digest:
                raise ValueError(f"input changed during external run: {name}")
        info.update({"status": "completed", "predictions": len(predictions), "question_rows": len(questions), "peak_vram_bytes": peak, "result_verification": verification})
        print("\n".join(lines[6:14]), flush=True)
        for name, value in analytical["paired"].items():
            print(json.dumps({"comparison": name, **value}, ensure_ascii=False), flush=True)
        return out
    except Exception as exc:
        info.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        write_json(out / "failure.json", info)
        raise
    finally:
        info["elapsed_seconds"] = time.perf_counter() - started
        write_json(out / "run_info.json", info, exclusive=False)
        print(json.dumps({"status": info["status"], "elapsed_seconds": info["elapsed_seconds"], "run_dir": str(out)}, ensure_ascii=False), flush=True)


def preflight_entry(cfg: dict) -> None:
    report, _ = preflight(cfg, strict_modules=True)
    print(
        json.dumps(
            {
                "status": report["status"],
                "counts": report["counts"],
                "manifest_sha256": report["input_sha256"][cfg["encoding_manifest"]],
                "weights_sha256": report["input_sha256"][cfg["weights_manifest"]],
                "seconds": report["seconds"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "run", "verify"))
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    cfg = load_config()
    if args.mode == "preflight":
        preflight_entry(cfg)
    elif args.mode == "run":
        run_evaluation(cfg)
    else:
        run = args.run_dir or find_completed(cfg)
        if run is None:
            raise FileNotFoundError("no completed frozen external run")
        run = checked_result_run(cfg, run)
        verification = verify_saved(run, cfg)
        print(json.dumps({"run_dir": str(run), **verification}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
