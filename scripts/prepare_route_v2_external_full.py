"""Prepare all fixed SciEGQA evidence pages without scoring or encoding."""
from __future__ import annotations

import hashlib
import json
import tarfile
import time
from datetime import datetime
from pathlib import Path

import pymupdf
import yaml
from acquire_route_v2_external_images import compare_image, find_member, sha256
from PIL import Image
from prepare_route_v2_external_pages import read_middle, run_page

from layoutpatch.datasets.mineru import check_scoring_structure, export_page
from layoutpatch.retrieval.route_v2_layout import external_node_text

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/tools/route_v2_external_full_prep_v1.yaml"
IMAGE_CONFIG = ROOT / "configs/tools/sciegqa_images_v1.yaml"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_inputs(cfg: dict) -> tuple[dict, list[dict]]:
    manifest_path = ROOT / cfg["manifest"]
    if sha256(manifest_path) != cfg["manifest_sha256"]:
        raise ValueError("fixed manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pages = sorted(manifest["pages"], key=lambda p: (p["doc_id"], p["pdf_page_index"]))
    if len(pages) != manifest["counts"]["unique_evidence_pages"] or len(pages) != 837:
        raise ValueError("manifest page count mismatch")
    if len({p["page_id"] for p in pages}) != len(pages):
        raise ValueError("duplicate manifest page IDs")
    return manifest, pages


def find_resume_run(root: Path, current: Path) -> Path | None:
    runs = []
    for path in root.glob("*"):
        audit = path / "audit.json"
        if path == current or not audit.is_file():
            continue
        try:
            report = json.loads(audit.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if report.get("unique_pages") != 837 or report.get("manifest_sha256") != "387b2f498ec4bb54abb7aab0a149ef46aa7856c284d2472541d61a7940d0347d":
            continue
        status = report.get("status")
        if status in {"blocked_page_failures", "ready"}:
            runs.append(path)
            continue
        complete = len(report.get("page_results", [])) == 837
        resumable_final_failure = status == "failed" and report.get("failure_stage") == "final_merge_and_audit"
        if complete and (status == "started" or resumable_final_failure):
            runs.append(path)
    return max(runs, key=lambda path: path.name) if runs else None


def member_sha256s(archive: Path, members: list[tarfile.TarInfo]) -> dict[str, str]:
    digests = {}
    with tarfile.open(archive) as stream:
        for member in members:
            source = stream.extractfile(member)
            if source is None:
                raise ValueError(f"cannot hash archive member: {member.name}")
            with source:
                digests[member.name] = hashlib.file_digest(source, "sha256").hexdigest()
    return digests


def read_candidate_rows(path: Path, page_lookup: dict[str, dict]) -> tuple[dict[str, list[dict]], dict]:
    diagnostics = {"malformed_candidate_lines": [], "invalid_candidate_pages": [],
                   "candidate_pages_outside_manifest": 0}
    rows: dict[str, list[dict]] = {}
    candidate_keys = set()
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                diagnostics["malformed_candidate_lines"].append(line_number)
                continue
            page_id = candidate.get("page_id")
            item = page_lookup.get(page_id)
            if item is None:
                diagnostics["candidate_pages_outside_manifest"] += 1
                continue
            layout_id = candidate.get("layout_id")
            key = (page_id, layout_id)
            expected_identity = (item["doc_id"], item["page_number"], item["pdf_page_index"])
            actual_identity = (candidate.get("doc_id"), candidate.get("page_number"), candidate.get("pdf_page_index"))
            valid = (
                type(layout_id) is int
                and key not in candidate_keys
                and actual_identity == expected_identity
                and candidate.get("candidate_id") == f"{page_id}:block:{layout_id}"
            )
            if not valid:
                diagnostics["invalid_candidate_pages"].append(page_id)
                continue
            candidate_keys.add(key)
            rows.setdefault(page_id, []).append(candidate)
    diagnostics["invalid_candidate_pages"] = sorted(set(diagnostics["invalid_candidate_pages"]))
    for page_id in diagnostics["invalid_candidate_pages"]:
        rows.pop(page_id, None)
    return rows, diagnostics


def load_reusable_pages(
    previous: Path | None,
    cfg: dict,
    pages: list[dict],
    pdf_archive: Path,
    pdf_members: list[tarfile.TarInfo],
    image_archive: Path,
    image_members: list[tarfile.TarInfo],
) -> tuple[dict[str, dict], dict[str, list[dict]], dict]:
    diagnostics = {"malformed_candidate_lines": [], "invalid_candidate_pages": [],
                   "candidate_pages_outside_manifest": 0}
    if previous is None:
        return {}, {}, diagnostics
    report = json.loads((previous / "audit.json").read_text(encoding="utf-8"))
    status = report.get("status")
    complete_final_failure = (
        status == "failed"
        and report.get("failure_stage") == "final_merge_and_audit"
        and len(report.get("page_results", [])) == len(pages)
    )
    if status not in {"blocked_page_failures", "ready", "started"} and not complete_final_failure:
        return {}, {}, diagnostics
    if report.get("manifest_sha256") != cfg["manifest_sha256"]:
        raise ValueError("resume manifest identity mismatch")
    page_lookup = {item["page_id"]: item for item in pages}
    candidates_path = previous / "candidates.jsonl"
    if not candidates_path.is_file():
        return {}, {}, diagnostics
    rows, diagnostics = read_candidate_rows(candidates_path, page_lookup)
    diagnostics["reconstructed_candidate_pages"] = []
    source_cache: dict[Path, tuple[dict[str, list[dict]], dict]] = {previous: (rows, diagnostics)}
    receipts = {}
    needed_pdf_members = {item["doc_id"]: pdf_member(pdf_members, item["doc_id"]) for item in pages}
    needed_image_members = {item["page_id"]: find_member(image_members, item["official_image_relative_path"]) for item in pages}
    image_digests = member_sha256s(image_archive, list(needed_image_members.values()))
    for item in pages:
        page_id = item["page_id"]
        receipt_path = previous / f"{page_id}_receipt.json"
        if not receipt_path.is_file():
            continue
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt_identity = (receipt.get("page_id"), receipt.get("doc_id"), receipt.get("page_number"), receipt.get("pdf_page_index"))
        expected_identity = (page_id, item["doc_id"], item["page_number"], item["pdf_page_index"])
        if receipt.get("status") != "passed" or receipt_identity != expected_identity:
            continue
        raw_path = ROOT / receipt.get("raw_output", "")
        render_path = ROOT / receipt.get("render", {}).get("render_path", "")
        image_path = ROOT / receipt.get("image", {}).get("path", "")
        if not all(path.is_file() for path in (raw_path, render_path, image_path)):
            continue
        expected_pdf_member = needed_pdf_members[item["doc_id"]]
        expected_image_member = needed_image_members[page_id]
        hashes_match = (
            sha256(raw_path) == receipt.get("raw_sha256")
            and sha256(render_path) == receipt.get("render", {}).get("render_sha256")
            and sha256(image_path) == receipt.get("image", {}).get("sha256")
            and image_digests[expected_image_member.name] == receipt.get("image", {}).get("sha256")
        )
        members_match = (
            receipt.get("pdf_member") == expected_pdf_member.name
            and receipt.get("image", {}).get("archive_member") == expected_image_member.name
        )
        mapping_passed = receipt.get("image", {}).get("mapping", {}).get("status") == "passed"
        if not hashes_match or not members_match or not mapping_passed:
            continue
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        if [page.get("page_idx") for page in payload.get("pages", [])] != [item["pdf_page_index"]]:
            continue
        expected = receipt.get("candidate_count")
        page_rows = rows.get(page_id, [])
        source_value = receipt.get("resume_source")
        visited = {previous}
        while (expected is not None and len(page_rows) != expected and source_value):
            source = ROOT / source_value
            if source in visited:
                break
            visited.add(source)
            source_receipt_path = source / f"{page_id}_receipt.json"
            source_candidates_path = source / "candidates.jsonl"
            if not source_receipt_path.is_file() or not source_candidates_path.is_file():
                break
            source_receipt = json.loads(source_receipt_path.read_text(encoding="utf-8"))
            if source_receipt.get("status") != "passed":
                break
            if source not in source_cache:
                source_cache[source] = read_candidate_rows(source_candidates_path, page_lookup)
            source_rows, source_diagnostics = source_cache[source]
            page_rows = source_rows.get(page_id, [])
            diagnostics.setdefault("fallback_sources", {})[rel(source)] = {
                "malformed_candidate_lines": source_diagnostics["malformed_candidate_lines"],
                "invalid_candidate_pages": source_diagnostics["invalid_candidate_pages"],
                "candidate_pages_outside_manifest": source_diagnostics["candidate_pages_outside_manifest"],
            }
            source_value = source_receipt.get("resume_source")
        if expected is not None and len(page_rows) != expected:
            try:
                page_rows, rebuilt_audit = export_page(payload, item, receipt["render"])
                check_scoring_structure(page_rows, receipt["render"])
            except (KeyError, TypeError, ValueError):
                page_rows = []
            if len(page_rows) == expected:
                diagnostics["reconstructed_candidate_pages"].append(page_id)
                receipt = {**receipt, "candidate_rows_reconstructed_from_verified_raw": True,
                           "reconstructed_coordinate_audit": rebuilt_audit}
        if expected is None or len(page_rows) != expected:
            continue
        rows[page_id] = page_rows
        receipts[page_id] = receipt
    return receipts, {page_id: rows[page_id] for page_id in receipts}, diagnostics


def short_pdf_path(out: Path, doc_id: str) -> Path:
    return out / "pdfs" / f"{doc_id}.pdf"


def archive_members(path: Path, expected_sha: str) -> list[tarfile.TarInfo]:
    if sha256(path) != expected_sha:
        raise ValueError(f"archive hash mismatch: {path}")
    with tarfile.open(path) as stream:
        return [m for m in stream.getmembers() if m.isfile()]


def pdf_member(members: list[tarfile.TarInfo], doc_id: str) -> tarfile.TarInfo:
    matches = [m for m in members if Path(m.name).suffix.lower() == ".pdf" and Path(m.name).name.startswith(doc_id + "_")]
    if len(matches) != 1:
        raise ValueError(f"PDF member is not unique for {doc_id}")
    return matches[0]


def extract_member_from_stream(stream: tarfile.TarFile, member: tarfile.TarInfo, output: Path) -> None:
    if output.is_file():
        if output.stat().st_size != member.size:
            raise ValueError(f"existing extracted member size mismatch: {output}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    source = stream.extractfile(member)
    if source is None:
        raise ValueError(f"cannot read archive member: {member.name}")
    with source, output.open("xb") as target:
        target.write(source.read())


def extract_member(archive: Path, member: tarfile.TarInfo, output: Path) -> None:
    with tarfile.open(archive) as stream:
        extract_member_from_stream(stream, member, output)


def render_page(pdf: Path, item: dict, target: Path, scale: float) -> dict:
    with pymupdf.open(pdf) as document:
        page = document[item["pdf_page_index"]]
        if page_number(item) != item["pdf_page_index"] + 1:
            raise ValueError("PDF page identity mismatch")
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        actual_size = [pixmap.width, pixmap.height]
        pixel_origin = [pixmap.x, pixmap.y]
        if target.is_file():
            with Image.open(target) as image:
                size = list(image.size)
            if size != actual_size:
                raise ValueError("existing render size differs from PyMuPDF pixel bounds")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            pixmap.save(target)
            size = actual_size
        rotation_matrix = list(page.rotation_matrix)
        return {"render_path": rel(target), "render_sha256": sha256(target), "page_size": size,
                "pdf_size_points": [page.mediabox.width, page.mediabox.height], "rotation": page.rotation,
                "cropbox": list(page.cropbox), "mediabox": list(page.mediabox), "page_rect": list(page.rect),
                "render_dpi": 72 * scale, "pdf_to_render_matrix": rotation_matrix,
                "rotation_matrix": rotation_matrix, "derotation_matrix": list(page.derotation_matrix),
                "render_scale": scale, "pixel_origin": pixel_origin, "pixel_bounds": list(pixmap.irect),
                "pixel_size": actual_size, "pixel_bounds_source": "PyMuPDF Pixmap.irect/width/height",
                "coordinate_basis": "parser_top_left_media_points_via_PyMuPDF_rotation_to_pixmap_pixels"}


def page_number(item: dict) -> int:
    return item["page_number"]


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    image_cfg = yaml.safe_load(IMAGE_CONFIG.read_text(encoding="utf-8"))
    manifest, pages = load_inputs(cfg)
    page_lookup = {item["page_id"]: item for item in pages}
    pdf_archive = ROOT / cfg["pdf_archive"]
    image_archive = ROOT / cfg["image_archive"]
    out = ROOT / cfg["output_root"] / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    for name in ("pdfs", "images", "renders", "mineru_output", "logs"):
        (out / name).mkdir()
    candidates_path = out / "candidates.jsonl"
    started = time.perf_counter()
    report = {"status": "running", "manifest_sha256": cfg["manifest_sha256"], "questions": manifest["counts"]["questions"],
              "unique_pages": len(pages), "question_page_units": manifest["counts"]["question_page_units"],
              "candidate_count": 0, "page_results": [], "questions_read": False, "gold_used_for_candidates": False,
              "scoring": False, "oracle": False, "training": False, "encoding": False,
              "resume_run": None, "reused_pages": 0, "new_pages": 0,
              "disk_free_bytes_at_start": __import__("shutil").disk_usage(ROOT).free}
    pdf_cache: dict[str, tuple[Path, tarfile.TarInfo]] = {}
    stage = "preflight_archives"
    try:
        pdf_members = archive_members(pdf_archive, cfg["pdf_archive_sha256"])
        image_members = archive_members(image_archive, cfg["image_archive_sha256"])
        stage = "resume_validation"
        previous = find_resume_run(ROOT / cfg["output_root"], out)
        reusable, reusable_rows, reuse_diagnostics = load_reusable_pages(
            previous, cfg, pages, pdf_archive, pdf_members, image_archive, image_members
        )
        report["resume_run"] = rel(previous) if previous else None
        report["reuse_validation"] = {
            "status": "passed", "verified_pages": len(reusable),
            "checks": ["manifest_and_page_identity", "fixed_pdf_archive_hash_and_unique_member", "raw_render_image_sha256", "image_member_and_content_mapping", "candidate_identity_count_and_uniqueness"],
            **reuse_diagnostics,
        }
        with tarfile.open(pdf_archive) as pdf_stream, tarfile.open(image_archive) as image_stream, candidates_path.open("w", encoding="utf-8") as candidate_stream:
            for index, item in enumerate(pages, start=1):
                page_id = item["page_id"]
                result = {"page_id": page_id, "doc_id": item["doc_id"], "page_number": item["page_number"],
                          "pdf_page_index": item["pdf_page_index"], "status": "running"}
                try:
                    stage = f"page:{page_id}:resume_or_extract"
                    if page_id in reusable:
                        result.update(reusable[page_id])
                        result.update({"status": "passed", "reused": True, "resume_source": rel(previous)})
                        for candidate in reusable_rows[page_id]:
                            candidate_stream.write(json.dumps(candidate, ensure_ascii=False) + "\n")
                        report["candidate_count"] += len(reusable_rows[page_id])
                        report["reused_pages"] += 1
                        report["page_results"].append(result)
                        write_json(out / f"{page_id}_receipt.json", result)
                        continue
                    if item["doc_id"] not in pdf_cache:
                        member = pdf_member(pdf_members, item["doc_id"])
                        pdf_path = short_pdf_path(out, item["doc_id"])
                        extract_member_from_stream(pdf_stream, member, pdf_path)
                        pdf_cache[item["doc_id"]] = (pdf_path, member)
                    pdf, member = pdf_cache[item["doc_id"]]
                    result["pdf_member"] = member.name
                    result["pdf_sha256"] = sha256(pdf)
                    stage = f"page:{page_id}:render"
                    render_path = out / "renders" / f"{page_id}.png"
                    render = render_page(pdf, item, render_path, cfg["render_scale"])
                    result["render"] = render
                    stage = f"page:{page_id}:official_image_mapping"
                    image_member = find_member(image_members, item["official_image_relative_path"])
                    image_path = out / "images" / f"{page_id}{Path(image_member.name).suffix.lower()}"
                    extract_member_from_stream(image_stream, image_member, image_path)
                    mapping = compare_image(image_path, render_path, image_cfg["mapping_checks"])
                    result["image"] = {"archive_member": image_member.name, "path": rel(image_path), "sha256": sha256(image_path), "mapping": mapping}
                    if mapping["status"] != "passed":
                        raise ValueError("original image/PDF content mapping failed")
                    stage = f"page:{page_id}:parse"
                    directory, resources = run_page(ROOT / cfg["parser_tool_root"], pdf, item, out)
                    raw_path, payload = read_middle(directory, item["pdf_page_index"])
                    stage = f"page:{page_id}:candidate_export"
                    candidates, audit = export_page(payload, item, render)
                    interface = check_scoring_structure(candidates, render)
                    source_counts = {}
                    empty = 0
                    for candidate in candidates:
                        text, source = external_node_text(candidate)
                        source_counts[source] = source_counts.get(source, 0) + 1
                        empty += not text
                    for candidate in candidates:
                        candidate_stream.write(json.dumps(candidate, ensure_ascii=False) + "\n")
                    candidate_stream.flush()
                    result.update(resources)
                    result.update(audit)
                    result.update({"status": "passed", "candidate_count": len(candidates), "empty_text_count": empty,
                                   "text_sources": source_counts, "interface": interface, "raw_output": rel(raw_path),
                                   "raw_sha256": sha256(raw_path), "reused": False})
                    report["candidate_count"] += len(candidates)
                    report["new_pages"] += 1
                except Exception as exc:
                    result.update({"status": "failed", "stage": stage, "error_type": type(exc).__name__, "error": str(exc)})
                    report["page_results"].append(result)
                    write_json(out / f"{page_id}_receipt.json", result)
                    continue
                report["page_results"].append(result)
                write_json(out / f"{page_id}_receipt.json", result)
                if index == 1 or index % 25 == 0:
                    print(f"pages={index}/837; passed={sum(r['status'] == 'passed' for r in report['page_results'])}; failed={sum(r['status'] == 'failed' for r in report['page_results'])}; candidates={report['candidate_count']}", flush=True)
        stage = "final_merge_and_audit"
        failed = [row for row in report["page_results"] if row["status"] != "passed"]
        result_ids = [row["page_id"] for row in report["page_results"]]
        if len(result_ids) != len(set(result_ids)) or set(result_ids) != set(page_lookup):
            raise ValueError("page receipt identity/coverage mismatch")
        candidate_keys = set()
        candidate_page_counts = {}
        candidate_rows = 0
        with candidates_path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                candidate = json.loads(line)
                page_id, layout_id = candidate.get("page_id"), candidate.get("layout_id")
                key = (page_id, layout_id)
                if type(layout_id) is not int or key in candidate_keys:
                    raise ValueError(f"invalid or duplicate page_id/layout_id in merged candidates at line {line_number}")
                item = page_lookup.get(page_id)
                if item is None:
                    raise ValueError(f"candidate page identity outside fixed manifest: {page_id}")
                expected_identity = (item["doc_id"], item["page_number"], item["pdf_page_index"])
                actual_identity = (candidate.get("doc_id"), candidate.get("page_number"), candidate.get("pdf_page_index"))
                if actual_identity != expected_identity or candidate.get("candidate_id") != f"{page_id}:block:{layout_id}":
                    raise ValueError(f"candidate ownership mismatch at line {line_number}")
                candidate_keys.add(key)
                candidate_rows += 1
                candidate_page_counts[page_id] = candidate_page_counts.get(page_id, 0) + 1
        if candidate_rows != report["candidate_count"]:
            raise ValueError(f"candidate count mismatch: receipt={report['candidate_count']}; merged={candidate_rows}")
        for row in report["page_results"]:
            expected = row.get("candidate_count", 0) if row["status"] == "passed" else 0
            if candidate_page_counts.get(row["page_id"], 0) != expected:
                raise ValueError(f"candidate ownership/count mismatch for {row['page_id']}")
        report.update({"status": "ready" if not failed else "blocked_page_failures",
                       "failed_pages": len(failed), "ready_input_pages": len(pages) - len(failed),
                       "candidate_rows": candidate_rows, "candidate_key_count": len(candidate_keys),
                       "candidates_sha256": sha256(candidates_path), "disk_free_bytes_at_end": __import__("shutil").disk_usage(ROOT).free})
    except BaseException as exc:
        report.update({"status": "failed", "failure_stage": stage,
                       "error_type": type(exc).__name__, "error": str(exc) or type(exc).__name__})
        raise
    finally:
        report["seconds"] = time.perf_counter() - started
        report["protected_input_sha256"] = {cfg["manifest"]: sha256(ROOT / cfg["manifest"]), cfg["pdf_archive"]: sha256(pdf_archive), cfg["image_archive"]: sha256(image_archive)}
        write_json(out / "audit.json", report)
        print(f"output={rel(out)}; status={report['status']}; pages={len(report['page_results'])}; failed={sum(r['status'] == 'failed' for r in report['page_results'])}; seconds={report['seconds']:.1f}", flush=True)
    if report.get("status") != "ready":
        raise RuntimeError(f"external full preparation blocked; audit={rel(out / 'audit.json')}")


if __name__ == "__main__":
    main()
