"""外部准备的只读身份/字段/工具核验；不渲染、解析或计算效果。"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import time
from collections import Counter, defaultdict
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import yaml

from layoutpatch.datasets.sciegqa import metadata_manifest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/experiments/route_v2_external_v1.yaml"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def resolve_weights(cfg):
    with (ROOT / cfg["weights"]["registry"]).open(encoding="utf-8-sig", newline="") as stream:
        registry = list(csv.DictReader(stream))
    result = {}
    for method, definition in cfg["methods"].items():
        if definition.get("trained") is False:
            continue
        entries = [r for r in registry if r["exp_id"] == definition["experiment"]]
        if len(entries) != 1 or entries[0]["config"] != definition["config"]:
            raise ValueError("training run registry identity mismatch")
        source = ROOT / definition["config"]
        training = yaml.safe_load(source.read_text("utf-8"))
        run = ROOT / entries[0]["run_dir"]
        if run.parent != ROOT / training["output"] or "smoke" in run.as_posix():
            raise ValueError("unexpected training run directory")
        info = json.loads((run / "run_info.json").read_text("utf-8"))
        snapshot = json.loads((run / "config.json").read_text("utf-8"))
        if info["status"] != "completed" or snapshot["seeds"] != [0, 1, 2]:
            raise ValueError("training run incomplete or seed mismatch")
        if any(snapshot.get(k) != v for k, v in training.items()):
            raise ValueError("training config differs from saved snapshot")
        if snapshot["early_stopping"]["role"] != "source_val":
            raise ValueError("checkpoint selection was not source_val")
        selection_path = run / cfg["weights"]["selection_file"]
        choices = json.loads(selection_path.read_text("utf-8"))
        key = definition["selection_key"]
        if key is not None:
            choices = choices[key]
        if set(choices) != {"0", "1", "2"}:
            raise ValueError("all three training seeds required")
        weights = []
        for seed in cfg["weights"]["seeds"]:
            choice = choices[str(seed)]
            base = run / key if key is not None else run
            checkpoint = (base / choice["checkpoint"]).resolve()
            if not checkpoint.is_relative_to(base.resolve()) or choice["seed"] != seed:
                raise ValueError("checkpoint identity/path mismatch")
            digest = sha256(checkpoint)
            if digest != choice["checkpoint_sha256"]:
                raise ValueError("checkpoint file hash mismatch")
            weights.append({"seed": seed, "selected_epoch": choice["best_epoch"], "selection_role": "source_val",
                            "checkpoint": checkpoint.relative_to(ROOT).as_posix(), "sha256": digest})
        result[method] = {"experiment": definition["experiment"], "run": run.relative_to(ROOT).as_posix(),
                          "config": definition["config"], "config_sha256": sha256(source),
                          "selection_sha256": sha256(selection_path), "weights": weights}
    if len(result) != 4:
        raise ValueError("expected four trained methods")
    return result


def field_schema(records):
    types, lengths = defaultdict(Counter), defaultdict(Counter)

    def visit(value, path, depth=0):
        types[path][type(value).__name__] += 1
        if depth > 5:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, f"{path}.{key}", depth + 1)
        elif isinstance(value, list):
            lengths[path][len(value)] += 1
            for child in value:
                visit(child, path + "[]", depth + 1)
    for record in records:
        visit(record, "row")
    return {"field_types": {k: dict(v) for k, v in sorted(types.items())},
            "list_lengths": {k: dict(v) for k, v in sorted(lengths.items())}}


def parser_inventory():
    packages = {}
    for name in ("mineru", "magic-pdf", "pymupdf"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    exact = [ROOT / ".venv/Scripts/mineru.exe", ROOT / ".venv/Scripts/magic-pdf.exe",
             Path.home() / "mineru.json", Path.home() / "magic-pdf.json"]
    configured = os.environ.get("MINERU_TOOLS_CONFIG_JSON")
    if configured:
        exact.append(Path(configured))
    paths = {str(p): p.is_file() for p in exact}
    available = bool(packages["mineru"] or packages["magic-pdf"])
    return {"packages": packages, "exact_paths": paths, "recursive_disk_search": False,
            "backend_package_available": available,
            "executable_model_pipeline_verified": False,
            "status": "requires_model_and_execution_check" if available else "blocked_missing_MinerU_in_project_venv"}


def main():
    cfg = yaml.safe_load(CONFIG.read_text("utf-8"))
    out = ROOT / cfg["preparation"]["output"] / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    report = {"status": "started", "effect_metrics_computed": False, "rendered_pages": 0, "parsed_pages": 0}
    try:
        identities = resolve_weights(cfg)
        binding = cfg["weights"].get("identity_manifest")
        if binding:
            if sha256(ROOT / binding) != cfg["weights"]["identity_sha256"]:
                raise ValueError("frozen weights manifest hash mismatch")
            if json.loads((ROOT / binding).read_text("utf-8")) != identities:
                raise ValueError("frozen weights manifest content mismatch")
        write_json(out / "weights.json", identities)
        report["weights"] = {"trained_methods": len(identities), "checkpoints": 12,
                             "manifest": (out / "weights.json").relative_to(ROOT).as_posix(), "sha256": sha256(out / "weights.json")}
        source = ROOT / cfg["input"]["root"]
        hashes = {}
        for name, hash_key in ((cfg["input"]["annotations"], "annotations_sha256"), (cfg["input"]["pdf_archive"], "pdf_archive_sha256")):
            digest = sha256(source / name)
            if digest != cfg["input"][hash_key]:
                raise ValueError("fixed external source identity mismatch")
            hashes[name] = digest
        with (source / cfg["input"]["annotations"]).open(encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream if line.strip()]
        if len(records) != cfg["input"]["questions"]:
            raise ValueError("external question denominator mismatch")
        schema = field_schema(records)
        write_json(out / "field_schema.json", schema)
        manifest = metadata_manifest(records)
        manifest.update({"dataset": cfg["input"]["dataset"], "revision": cfg["input"]["revision"],
                         "input_sha256": hashes, "sample_rule": cfg["preparation"]["sample_rule"],
                         "coordinate_schema": cfg["input"]["coordinate_schema"]})
        write_json(out / "manifest.json", manifest)
        report.update({"questions": len(records), "input_sha256": hashes, "parser": parser_inventory(),
                       "manifest": (out / "manifest.json").relative_to(ROOT).as_posix(),
                       "manifest_sha256": sha256(out / "manifest.json"), "counts": manifest["counts"],
                       "format_errors": manifest["validation_errors"],
                       "sample_status": "not_run_missing_parser", "sample_pages": len(manifest["sample_page_ids"]),
                       "candidate_count": None, "parse_seconds": None, "peak_vram_bytes": None,
                       "full_preparation_estimate": "not_measurable_without_eight_page_pipeline",
                       "coordinate_mapping": "normalized_boxes_declared_but_original_image_frame_and_render_transform_unverified"})
        report["status"] = "blocked_parser" if not report["parser"]["backend_package_available"] else "audited_no_scoring"
        print(f"questions={len(records)}; trained_methods=4; checkpoints=12; weights_sha256={report['weights']['sha256']}", flush=True)
        print("counts=" + json.dumps(manifest["counts"], ensure_ascii=False), flush=True)
        print("format_errors=" + json.dumps(manifest["validation_errors"], ensure_ascii=False), flush=True)
        print(f"manifest={report['manifest']}; sha256={report['manifest_sha256']}", flush=True)
        print(f"parser_status={report['parser']['status']}; rendered=0; parsed=0; scored=0", flush=True)
        print(f"weights_manifest={report['weights']['manifest']}", flush=True)
    except Exception as exc:
        report.update({"status": "failed", "error_type": type(exc).__name__, "error": str(exc)})
        raise
    finally:
        report["seconds"] = time.perf_counter() - started
        write_json(out / "audit.json", report)
        print(f"audit_dir={out}; status={report['status']}; seconds={report['seconds']:.3f}", flush=True)


if __name__ == "__main__":
    main()
