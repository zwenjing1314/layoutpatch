"""续接固定八页MinerU工程验收；不读取问答/gold，不评分，不改旧产物。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path

import pymupdf
import yaml
from PIL import Image, ImageDraw

from layoutpatch.datasets.mineru import check_scoring_structure, export_page

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/experiments/route_v2_external_v1.yaml"
TOOL_CONFIG = ROOT / "configs/tools/mineru_external_pages_v1.yaml"
OUTPUT = ROOT / "artifacts/route_v2_external/preparation_v1"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def rel(path):
    return path.relative_to(ROOT).as_posix()


def load_fixed_pages(cfg):
    path = ROOT / cfg["input"]["manifest"]
    if sha256(path) != cfg["input"]["manifest_sha256"]:
        raise ValueError("fixed manifest hash mismatch")
    manifest = json.loads(path.read_text("utf-8"))
    ids = manifest["sample_page_ids"]
    if len(ids) != 8 or len(set(ids)) != 8:
        raise ValueError("exactly eight unique frozen page IDs required")
    lookup = {p["page_id"]: p for p in manifest["pages"]}
    fixed = [lookup[key] for key in ids]
    if any(p["page_number"] != p["pdf_page_index"] + 1 for p in fixed):
        raise ValueError("source page identity mismatch")
    audit = json.loads(path.with_name("audit.json").read_text("utf-8"))
    return manifest, fixed, audit


def tool_env(tool_root):
    env = os.environ.copy()
    env.update({"MINERU_HOME": str(tool_root / "mineru_home"), "MINERU_MODEL_SOURCE": "local",
                "MINERU_MODEL_SMALL_BACKEND": "onnx", "MINERU_TABLE_DEVICE": "cpu",
                "CUDA_VISIBLE_DEVICES": "", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                "PYTHONIOENCODING": "utf-8", "DO_NOT_TRACK": "1"})
    env.pop("VIRTUAL_ENV", None)
    return env


def installed_identity(tool_root):
    python = tool_root / ".venv/Scripts/python.exe"
    code = (
        "import sys,json,importlib.metadata as m; "
        "ds=list(m.distributions()); d=m.metadata('mineru'); "
        "print(json.dumps({'python':sys.version,'base_prefix':sys.base_prefix,"
        "'packages':{p.metadata['Name'].lower():p.version for p in ds},"
        "'license':d.get('License-Expression'),'requires_python':d.get('Requires-Python')}))"
    )
    result = subprocess.run([str(python), "-c", code], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def log_text(path):
    raw = path.read_bytes()
    return raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8", errors="replace")


def tool_identity(tool_root, tool_cfg):
    identity = installed_identity(tool_root)
    for package, key in (("mineru", "package_version"), ("onnxruntime", "onnxruntime_version"), ("docvortex", "docvortex_version")):
        if identity["packages"].get(package) != tool_cfg[key]:
            raise ValueError(f"unexpected {package} version")
    if "anaconda" in identity["base_prefix"].lower():
        raise ValueError("Anaconda interpreter is not authorized")
    models = tool_root / "mineru_home/models/MinerU-4_models_onnx"
    files = []
    for path in sorted(models.rglob("*")):
        if not path.is_file() or ".cache" in path.relative_to(models).parts:
            continue
        name = path.relative_to(models).as_posix()
        metadata = models / ".cache/huggingface/download" / (name + ".metadata")
        revision, etag, *_ = metadata.read_text("utf-8").splitlines()
        digest = sha256(path)
        if revision != tool_cfg["model_revision"]:
            raise ValueError("mixed model revisions")
        if len(etag) == 64 and digest != etag:
            raise ValueError("model hash differs from downloaded LFS identity")
        if len(etag) == 40:
            data = path.read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if blob != etag:
                raise ValueError("model config hash differs from Git blob identity")
        if len(etag) not in (40, 64):
            raise ValueError("unrecognized download identity")
        files.append({"path": name, "bytes": path.stat().st_size, "sha256": digest, "etag": etag,
                      "source": f"https://huggingface.co/{tool_cfg['model_repository']}/resolve/{revision}/{name}"})
    if len(files) != 13:
        raise ValueError("expected exactly 13 previously downloaded model assets")
    library = tool_root / ".venv/Lib/site-packages"
    sources = ["mineru-4.0.10.dist-info/licenses/LICENSE.md", "mineru-4.0.10.dist-info/METADATA",
               "mineru-4.0.10.dist-info/RECORD", "docvortex/schema.py", "docvortex/foundation/_coordinates.py",
               "mineru/parser/mineru_parser.py", "mineru/parser/page_range.py"]
    logs = {name: {"path": rel(tool_root / name), "sha256": sha256(tool_root / name)} for name in (
        "venv_create.log", "mineru_install.log", "basic_onnx_model_download.log", "basic_onnx_model_verify.log")}
    install = log_text(tool_root / "mineru_install.log")
    stage_seconds = re.findall(r"(?:Resolved|Prepared|Installed) .*? in ([\d.]+)s", install)
    return {**identity, "python_source": tool_cfg["python_source"], "tool_root": rel(tool_root),
            "package_source": "https://pypi.org/project/mineru/4.0.10/", "model_revision": tool_cfg["model_revision"],
            "model_repository": tool_cfg["model_repository"], "model_files": files,
            "materialized_model_bytes": sum(f["bytes"] for f in files), "network_transfer_bytes": None,
            "network_transfer_note": "中断前未计量网络协议/重试字节；上项是本机实际落盘模型文件字节，不是流量测量",
            "install_stage_seconds": [float(s) for s in stage_seconds], "install_wall_seconds": None,
            "download_progress_seconds": 287, "download_time_source": "既有下载进度13/13 [04:47]，秒级显示精度",
            "downloaded_this_resume_bytes": 0, "installation_logs": logs,
            "package_license": "Apache-2.0 with MinerU additional commercial thresholds and service attribution obligations",
            "model_license": "Official fixed-revision card retains original component licenses; not a blanket dataset license",
            "model_card": f"https://huggingface.co/{tool_cfg['model_repository']}/blob/{tool_cfg['model_revision']}/README.md",
            "source_identity": {s: sha256(library / s) for s in sources}}


def prepare_render_info(pdf, pages, previous):
    results = {}
    with pymupdf.open(pdf) as document:
        for item in pages:
            page = document[item["pdf_page_index"]]
            if page.rotation != 0 or page.cropbox != page.mediabox or page.rect.x0 != 0 or page.rect.y0 != 0:
                raise ValueError("unverified PDF rotation/crop transform")
            path = previous / "rendered_pages" / (item["page_id"] + ".png")
            with Image.open(path) as image:
                size = list(image.size)
            expected = [round(page.rect.width * 2), round(page.rect.height * 2)]
            if size != expected:
                raise ValueError("previous render dimensions differ from fixed 2x transform")
            results[item["page_id"]] = {"render_path": rel(path), "render_sha256": sha256(path),
                "render_reused": True, "original_render_seconds": None,
                "page_size": size, "pdf_size_points": [page.rect.width, page.rect.height],
                "rotation": page.rotation, "cropbox": list(page.cropbox), "mediabox": list(page.mediabox),
                "pdf_point_to_render_pixel": [2, 0, 0, 2, 0, 0], "origin": "top_left_x_right_y_down",
                "unit_to_render": [size[0], 0, 0, size[1], 0, 0], "render_dpi": 144,
                "original_annotation_image_size": None, "original_annotation_transform_verified": False}
    return results


def overlay(render, candidates, target):
    with Image.open(ROOT / render["render_path"]) as image:
        canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    for c in candidates:
        color = {"text": "blue", "title": "purple", "table": "red", "image": "green", "equation": "orange"}[c["type"]]
        draw.rectangle(c["bbox"], outline=color, width=2)
        draw.text((c["bbox"][0], max(0, c["bbox"][1] - 12)), str(c["layout_id"]), fill=color)
    canvas.save(target)


def read_middle(directory, page_index):
    files = sorted(directory.glob("*.json"))
    if len(files) != 1:
        raise ValueError("expected one raw MiddleJson output")
    value = json.loads(files[0].read_text("utf-8"))
    if [p["page_idx"] for p in value.get("pages", [])] != [page_index]:
        raise ValueError("raw output page mismatch")
    return files[0], value


def run_page(tool_root, pdf, item, out):
    directory = out / "mineru_output" / item["page_id"]
    directory.mkdir(parents=True)
    receipt = out / "logs" / (item["page_id"] + "_resources.json")
    command = [str(tool_root / ".venv/Scripts/python.exe"), str(ROOT / "scripts/route_v2_mineru_worker.py"),
               str(receipt), "parse", str(pdf), "--output", str(directory), "--pages", str(item["page_number"]),
               "--format", "middle_json", "--tier", "basic", "--ocr-mode", "auto"]
    started = time.perf_counter()
    with (out / "logs" / (item["page_id"] + ".log")).open("x", encoding="utf-8") as log:
        log.write("command=" + " ".join(command) + "\n")
        log.flush()
        completed = subprocess.run(command, cwd=ROOT, env=tool_env(tool_root), stdout=log, stderr=subprocess.STDOUT)
    resources = json.loads(receipt.read_text("utf-8")) if receipt.is_file() else {}
    resources["parse_seconds"] = time.perf_counter() - started
    if completed.returncode or resources.get("status") != "completed":
        raise RuntimeError(f"parser exit={completed.returncode}; exact log={rel(out / 'logs' / (item['page_id'] + '.log'))}")
    if not resources["sessions"] or resources["gpu_used"]:
        raise ValueError("CPU model execution was not verified")
    return directory, resources


def inspect(cfg, tool_cfg, mode):
    if mode == "access":
        manifest, pages, audit = load_fixed_pages(cfg)
        print(f"access=ok; sha256={cfg['input']['manifest_sha256']}; audit={audit['status']}; unique_pages={manifest['counts']['unique_evidence_pages']}")
        print(f"pdf_archive={cfg['input']['root']}/{cfg['input']['pdf_archive']}")
        for p in pages:
            print(f"page={p['page_id']}; doc={p['doc_id']}; source_page={p['page_number']}; pdf_index={p['pdf_page_index']}; image={p['official_image_relative_path']}")
    else:
        identity = installed_identity(ROOT / tool_cfg["tool_root"])
        print("versions=" + str({k: identity["packages"][k] for k in ("mineru", "onnxruntime", "docvortex")}))
        print(f"base_prefix={identity['base_prefix']}; license={identity['license']}")
        print("output_contract=docvortex.middle 2.0; bbox=unit 0..1; layout page sizes=PDF points; official source hashes saved by pages task")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect-only", action="store_true")
    parser.add_argument("--inspect-tool", action="store_true")
    parser.add_argument("--inspect-contract", action="store_true")
    args = parser.parse_args()
    cfg = yaml.safe_load(CONFIG.read_text("utf-8"))
    tool_cfg = yaml.safe_load(TOOL_CONFIG.read_text("utf-8"))
    if args.inspect_only or args.inspect_tool or args.inspect_contract:
        inspect(cfg, tool_cfg, "access" if args.inspect_only else "tool")
        return
    out = OUTPUT / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir()
    (out / "logs").mkdir()
    (out / "overlays").mkdir()
    started = time.perf_counter()
    protected = [CONFIG, ROOT / "pyproject.toml", ROOT / "uv.lock", ROOT / cfg["weights"]["identity_manifest"]]
    before = {rel(p): sha256(p) for p in protected}
    report = {"status": "started", "page_results": [], "questions_read": False, "gold_read": False,
              "effect_metrics_computed": False, "full_processing": False, "protected_input_sha256": before}
    try:
        manifest, fixed, previous_audit = load_fixed_pages(cfg)
        previous = ROOT / tool_cfg["resume_run"]
        tool_root = ROOT / tool_cfg["tool_root"]
        identity = tool_identity(tool_root, tool_cfg)
        write_json(out / "tool_manifest.json", identity)
        write_json(out / "parser_config.json", {**tool_cfg, "yaml_sha256": sha256(TOOL_CONFIG)})
        previous_receipt = json.loads((previous / "audit.json").read_text("utf-8"))
        pdfs = list((previous / "input").glob("*.pdf"))
        if len(pdfs) != 1 or any(p["doc_id"] != fixed[0]["doc_id"] for p in fixed):
            raise ValueError("unexpected resume PDF identity")
        pdf = pdfs[0]
        # 核对已提取PDF确实来自固定源包；不再提取/渲染已存在的八页。
        archive = ROOT / cfg["input"]["root"] / cfg["input"]["pdf_archive"]
        with tarfile.open(archive) as stream:
            matches = [m for m in stream.getmembers() if m.isfile() and Path(m.name).name == pdf.name]
            if len(matches) != 1:
                raise ValueError("resume PDF does not map to a unique source archive member")
            with stream.extractfile(matches[0]) as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            if digest != sha256(pdf):
                raise ValueError("resume PDF/source archive identity mismatch")
        renders = prepare_render_info(pdf, fixed, previous)
        write_json(out / "render_manifest.json", {"pages": renders, "pdf_sha256": digest, "archive_member": matches[0].name})
        write_json(out / "input_identity.json", {"manifest_sha256": cfg["input"]["manifest_sha256"],
                   "sample_page_ids": [p["page_id"] for p in fixed], "source_pdf": rel(pdf),
                   "prior_audit_sha256": sha256((ROOT / cfg["input"]["manifest"]).with_name("audit.json")),
                   "prior_audit_status": previous_audit["status"], "resume_audit_sha256": sha256(previous / "audit.json")})
        with (out / "candidates.jsonl").open("x", encoding="utf-8") as stream:
            for item in fixed:
                page_id = item["page_id"]
                result = {"page_id": page_id, "page_number": item["page_number"], "status": "started"}
                report["page_results"].append(result)
                if page_id in tool_cfg["reuse_raw_page_ids"]:
                    directory = previous / "mineru_output" / page_id
                    resources = {"parse_seconds": None, "peak_working_set_bytes": None, "reused": True,
                                 "prior_run_total_seconds_not_page_time": previous_receipt["seconds"],
                                 "resource_measurement_status": "not_saved_by_interrupted_runner"}
                else:
                    directory, resources = run_page(tool_root, pdf, item, out)
                result.update(resources)
                raw_path, payload = read_middle(directory, item["pdf_page_index"])
                candidates, coordinate = export_page(payload, item, renders[page_id])
                interface = check_scoring_structure(candidates, renders[page_id])
                for c in candidates:
                    c["raw_output"] = rel(raw_path)
                    stream.write(json.dumps(c, ensure_ascii=False) + "\n")
                stream.flush()
                overlay(renders[page_id], candidates, out / "overlays" / f"{page_id}.png")
                result.update({"status": "passed", **coordinate, "interface": interface,
                               "raw_output": rel(raw_path), "raw_sha256": sha256(raw_path),
                               "producer": payload.get("metadata", {}).get("producer"),
                               "parser_execution_metadata": payload.get("extensions", {}).get("mineru")})
                write_json(out / f"{page_id}_receipt.json", result)
                print(f"page={page_id}; candidates={len(candidates)}; seconds={resources.get('parse_seconds')}; peak_bytes={resources.get('peak_working_set_bytes')}; reused={resources.get('reused', False)}", flush=True)
        results = report["page_results"]
        measured = [p for p in results if p.get("parse_seconds") is not None]
        seconds = sum(p["parse_seconds"] for p in measured)
        count = sum(p["candidate_count"] for p in results)
        report.update({"status": "eight_pages_exported_visual_review_pending", "successful_pages": len(results),
                       "newly_parsed_pages": len(measured), "reused_parsed_pages": len(results) - len(measured),
                       "rendered_pages_reused": len(renders), "candidate_count": count,
                       "parse_seconds_measured_subset": seconds,
                       "peak_working_set_bytes": max(p["peak_working_set_bytes"] for p in measured),
                       "model_load_seconds_sum": sum(p["model_session_load_seconds"] for p in measured),
                       "tool_import_seconds_sum": sum(p["tool_import_seconds"] for p in measured),
                       "gpu_used": any(p.get("gpu_used", False) for p in results),
                       "rough_full_parse_seconds": seconds / len(measured) * manifest["counts"]["unique_evidence_pages"],
                       "estimate_basis": "seven measured per-page processes; first fixed page reused without timing; not a representative sample; excludes unmeasured rendering and encoding",
                       "original_annotation_mapping_verified": False, "full_preparation_ready": False,
                       "candidates_sha256": sha256(out / "candidates.jsonl"),
                       "invalid_boxes": sum(p["invalid_boxes"] for p in results),
                       "out_of_bounds_boxes": sum(p["out_of_bounds_boxes"] for p in results),
                       "duplicate_boxes": sum(p["duplicate_boxes"] for p in results),
                       "no_candidate_pages": sum(p["no_candidates"] for p in results)})
        write_json(out / "coordinate_audit.json", {"parser_to_render_machine": "passed", "visual_review": "pending",
                   "annotation_image_mapping": "unverified_original_images_not_available", "pages": renders,
                   "invalid_boxes": report["invalid_boxes"], "out_of_bounds_boxes": report["out_of_bounds_boxes"],
                   "duplicate_boxes": report["duplicate_boxes"], "no_candidate_pages": report["no_candidate_pages"]})
        write_json(out / "page_metrics.json", {"engineering_only": True, "pages": results})
        print(f"success={len(results)}/8; new={len(measured)}; candidates={count}; measured_seconds={seconds:.3f}; peak_MiB={report['peak_working_set_bytes']/2**20:.2f}; estimate_minutes={report['rough_full_parse_seconds']/60:.2f}", flush=True)
        print(f"model_bytes={identity['materialized_model_bytes']}; load_seconds={report['model_load_seconds_sum']:.3f}; import_seconds={report['tool_import_seconds_sum']:.3f}; invalid={report['invalid_boxes']}; outside={report['out_of_bounds_boxes']}; duplicates={report['duplicate_boxes']}; empty_pages={report['no_candidate_pages']}", flush=True)
    except Exception as exc:
        report.update({"status": "failed", "error_type": type(exc).__name__, "error": str(exc)})
        if report["page_results"] and report["page_results"][-1]["status"] == "started":
            report["page_results"][-1].update({"status": "failed", "error": str(exc)})
        print(f"status=failed; error={type(exc).__name__}: {exc}", flush=True)
        raise
    finally:
        after = {rel(p): sha256(p) for p in protected}
        report["protected_inputs_unchanged"] = before == after
        report["resume_seconds"] = time.perf_counter() - started
        write_json(out / "audit.json", report)
        print(f"output={rel(out)}; status={report['status']}; protected_unchanged={report['protected_inputs_unchanged']}", flush=True)


if __name__ == "__main__":
    main()
