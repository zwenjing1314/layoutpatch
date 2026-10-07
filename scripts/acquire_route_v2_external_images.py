"""下载固定SciEGQA图像包，只核验既定八页，不评分。"""
from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
IMAGE_CONFIG = ROOT / "configs/tools/sciegqa_images_v1.yaml"
COMPARISON_CONFIG = ROOT / "configs/experiments/route_v2_external_v1.yaml"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_fixed_pages(cfg: dict, image_cfg: dict) -> tuple[dict, list[dict]]:
    manifest_path = ROOT / image_cfg["manifest_path"]
    if sha256(manifest_path) != image_cfg["manifest_sha256"] or image_cfg["manifest_sha256"] != cfg["input"]["manifest_sha256"]:
        raise ValueError("fixed manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text("utf-8"))
    ids = manifest["sample_page_ids"]
    if len(ids) != image_cfg["max_pages"] or len(set(ids)) != image_cfg["max_pages"]:
        raise ValueError("manifest does not contain exactly eight unique fixed page IDs")
    lookup = {page["page_id"]: page for page in manifest["pages"]}
    pages = [lookup[page_id] for page_id in ids]
    if any(page["page_number"] != page["pdf_page_index"] + 1 for page in pages):
        raise ValueError("fixed page number/index mismatch")
    if any(not page.get("official_image_relative_path") for page in pages):
        raise ValueError("fixed page lacks official image path")
    return manifest, pages


def download_archive(path: Path, url: str, expected_sha: str) -> dict:
    if path.is_file():
        actual = sha256(path)
        if actual != expected_sha:
            raise ValueError(f"existing Images.tar hash mismatch: {path}")
        return {"status": "reused", "path": rel(path), "bytes": path.stat().st_size, "sha256": actual}
    partial = path.with_suffix(path.suffix + ".part")
    if partial.exists():
        raise RuntimeError(f"partial archive exists; refusing overwrite: {partial}")
    path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": "LayoutPatch-SciEGQA-fixed-page-audit"})
    total = 0
    last_report = started
    try:
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as stream:
            while block := response.read(4 * 1024 * 1024):
                stream.write(block)
                total += len(block)
                now = time.monotonic()
                if now - last_report >= 30:
                    print(f"downloaded_bytes={total}; elapsed_seconds={now - started:.1f}", flush=True)
                    last_report = now
        actual = sha256(partial)
        if actual != expected_sha:
            raise ValueError(f"downloaded Images.tar hash mismatch: {partial}")
        partial.replace(path)
    except Exception:
        print(f"download_failed_partial={rel(partial)}; bytes={total}", flush=True)
        raise
    return {"status": "downloaded", "path": rel(path), "bytes": path.stat().st_size,
            "sha256": actual, "seconds": time.monotonic() - started}


def normalize_member(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def find_member(members: list[tarfile.TarInfo], relative_path: str) -> tarfile.TarInfo:
    expected = normalize_member(relative_path)
    names = [(member, normalize_member(member.name)) for member in members if member.isfile()]
    exact = [member for member, name in names if name == expected]
    if len(exact) == 1:
        return exact[0]
    suffix = [member for member, name in names if name.endswith("/" + expected)]
    if len(suffix) == 1:
        return suffix[0]
    raise ValueError(f"official image path does not resolve uniquely: {relative_path}")


def foreground_bbox(image: Image.Image) -> list[float] | None:
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    mask = gray < 245
    ys, xs = np.where(mask)
    if not len(xs):
        return None
    width, height = image.size
    return [float(xs.min() / width), float(ys.min() / height),
            float((xs.max() + 1) / width), float((ys.max() + 1) / height)]


def resize_mask(image: Image.Image, size: tuple[int, int]) -> np.ndarray:
    small = image.convert("L").resize(size, Image.Resampling.BILINEAR)
    return np.asarray(small, dtype=np.uint8) < 245


def best_mask_alignment(source: np.ndarray, target: np.ndarray) -> tuple[float, tuple[int, int]]:
    best_iou, best_shift = 0.0, (0, 0)
    height, width = target.shape
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            shifted = np.zeros_like(source)
            source_y0, source_y1 = max(0, -dy), min(height, height - dy)
            source_x0, source_x1 = max(0, -dx), min(width, width - dx)
            target_y0, target_y1 = source_y0 + dy, source_y1 + dy
            target_x0, target_x1 = source_x0 + dx, source_x1 + dx
            shifted[target_y0:target_y1, target_x0:target_x1] = source[source_y0:source_y1, source_x0:source_x1]
            intersection = np.logical_and(shifted, target).sum()
            union = np.logical_or(shifted, target).sum()
            iou = float(intersection / union) if union else 1.0
            if iou > best_iou:
                best_iou, best_shift = iou, (dx, dy)
    return best_iou, best_shift


def compare_image(source_path: Path, render_path: Path, thresholds: dict) -> dict:
    with Image.open(source_path) as source_raw, Image.open(render_path) as render_raw:
        source_orientation = int(source_raw.getexif().get(274, 1))
        source = ImageOps.exif_transpose(source_raw).convert("RGB")
        render = render_raw.convert("RGB")
        source_size, render_size = source.size, render.size
        source_ratio = source_size[0] / source_size[1]
        render_ratio = render_size[0] / render_size[1]
        aspect_delta = abs(source_ratio - render_ratio) / render_ratio
        source_bbox = foreground_bbox(source)
        render_bbox = foreground_bbox(render)
        if source_bbox is None or render_bbox is None:
            raise ValueError(f"empty foreground in image comparison: {source_path}")
        bbox_delta = max(abs(a - b) for a, b in zip(source_bbox, render_bbox, strict=True))
        source_small = resize_mask(source, (128, 166))
        render_small = resize_mask(render, (128, 166))
        best_iou, best_shift = best_mask_alignment(source_small, render_small)
        source_gray = np.asarray(source.resize((128, 166), Image.Resampling.BILINEAR).convert("L"), dtype=float)
        render_gray = np.asarray(render.resize((128, 166), Image.Resampling.BILINEAR).convert("L"), dtype=float)
        correlation = float(np.corrcoef(source_gray.ravel(), render_gray.ravel())[0, 1])
        checks = {
            "aspect_ratio": aspect_delta <= thresholds["aspect_ratio_delta_max"],
            "foreground_bbox": bbox_delta <= thresholds["foreground_bbox_edge_delta_max"],
            "foreground_content_iou": best_iou >= thresholds["foreground_iou_min"],
            "grayscale_correlation": correlation >= thresholds["grayscale_correlation_min"],
            "lowres_shift": max(abs(best_shift[0]), abs(best_shift[1])) <= thresholds["max_shift_lowres_pixels"],
        }
        return {
            "status": "passed" if all(checks.values()) else "failed",
            "source_image_size": list(source_size),
            "source_exif_orientation": source_orientation,
            "render_image_size": list(render_size),
            "aspect_ratio_delta": aspect_delta,
            "source_foreground_bbox_normalized": source_bbox,
            "render_foreground_bbox_normalized": render_bbox,
            "foreground_bbox_edge_delta": bbox_delta,
            "foreground_content_iou_best_shift": best_iou,
            "best_shift_lowres_pixels": list(best_shift),
            "grayscale_correlation": correlation,
            "checks": checks,
            "mapping_basis": "foreground geometry plus low-resolution content alignment; not dimension-only",
        }


def main() -> None:
    image_cfg = yaml.safe_load(IMAGE_CONFIG.read_text("utf-8"))
    comparison_cfg = yaml.safe_load(COMPARISON_CONFIG.read_text("utf-8"))
    manifest, pages = load_fixed_pages(comparison_cfg, image_cfg)
    archive = ROOT / image_cfg["archive_path"]
    fixed_images = ROOT / image_cfg["fixed_image_output"]
    review_root = ROOT / image_cfg["review_output"] / datetime.now().strftime("%Y%m%d_%H%M%S")
    review_root.mkdir(parents=True)
    report = {
        "status": "started", "dataset": image_cfg["dataset"], "revision": image_cfg["revision"],
        "manifest_sha256": image_cfg["manifest_sha256"], "sample_page_ids": [page["page_id"] for page in pages],
        "questions_read": False, "gold_used_for_candidates": False, "scoring": False,
        "oracle": False, "training": False, "full_processing": False,
        "coordinate_contract": image_cfg["coordinate_contract"], "pages": [],
    }
    try:
        archive_receipt = download_archive(archive, image_cfg["archive_url"], image_cfg["archive_sha256"])
        report["archive"] = archive_receipt
        render_manifest_path = ROOT / image_cfg["render_manifest_path"]
        render_manifest = json.loads(render_manifest_path.read_text("utf-8"))
        if fixed_images.exists():
            raise RuntimeError(f"fixed image output already exists; refusing overwrite: {fixed_images}")
        fixed_images.mkdir(parents=True)
        with tarfile.open(archive, "r") as stream:
            members = stream.getmembers()
            for page in pages:
                page_id = page["page_id"]
                member = find_member(members, page["official_image_relative_path"])
                suffix = Path(member.name).suffix.lower() or ".img"
                output = fixed_images / f"{page_id}{suffix}"
                source = stream.extractfile(member)
                if source is None:
                    raise ValueError(f"cannot read archive member: {member.name}")
                with source, output.open("xb") as target:
                    shutil.copyfileobj(source, target)
                render_info = render_manifest["pages"].get(page_id)
                if render_info is None:
                    raise ValueError(f"missing render manifest page: {page_id}")
                render_path = ROOT / render_info["render_path"]
                if not render_path.is_file():
                    raise FileNotFoundError(render_path)
                mapping = compare_image(output, render_path, image_cfg["mapping_checks"])
                result = {
                    "page_id": page_id, "doc_id": page["doc_id"], "source_page_number": page["page_number"],
                    "pdf_page_index": page["pdf_page_index"],
                    "official_image_relative_path": page["official_image_relative_path"],
                    "archive_member": member.name, "extracted_path": rel(output),
                    "render_path": rel(render_path), "pdf_rotation": render_info["rotation"],
                    "cropbox": render_info["cropbox"], "mediabox": render_info["mediabox"],
                    "mapping": mapping,
                }
                report["pages"].append(result)
                print(f"page={page_id}; original={mapping['source_image_size']}; render={mapping['render_image_size']}; mapping={mapping['status']}", flush=True)
                if mapping["status"] != "passed":
                    raise ValueError(f"unresolved image content mapping: {page_id}")
        report.update({
            "status": "eight_pages_original_mapping_passed" if all(page["mapping"]["status"] == "passed" for page in report["pages"]) else "mapping_failed_stop",
            "successful_mapping_pages": sum(page["mapping"]["status"] == "passed" for page in report["pages"]),
            "original_annotation_mapping_verified": all(page["mapping"]["status"] == "passed" for page in report["pages"]),
            "candidate_coordinate_contract_unchanged": True,
            "gold_rel_bbox_not_converted_or_used_for_candidates": True,
        })
    except Exception as exc:
        report.update({"status": "failed", "error_type": type(exc).__name__, "error": str(exc)})
        raise
    finally:
        write_json(review_root / "image_mapping_audit.json", report)
        write_json(review_root / "page_receipts.json", {"pages": report["pages"], "count": len(report["pages"])})
        print(f"output={rel(review_root)}; status={report['status']}; mapped={report.get('successful_mapping_pages', 0)}/8", flush=True)


if __name__ == "__main__":
    main()
