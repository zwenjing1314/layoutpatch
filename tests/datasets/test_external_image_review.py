"""新增图像审计与冻结文本消费者的合成测试；不读真实问答，不运行模型。"""
import importlib.util
import sys
import tarfile
from pathlib import Path

import pytest
import torch
from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


images = load("acquire_route_v2_external_images")
review = load("review_route_v2_external_pages")
THRESHOLDS = {"aspect_ratio_delta_max": 0.005, "foreground_bbox_edge_delta_max": 0.03,
              "foreground_iou_min": 0.70, "grayscale_correlation_min": 0.80,
              "max_shift_lowres_pixels": 3}


def test_content_mapping_requires_content_not_only_dimensions(tmp_path):
    source = Image.new("RGB", (256, 332), "white")
    draw = ImageDraw.Draw(source)
    draw.rectangle([25, 30, 200, 45], fill="black")
    draw.rectangle([25, 110, 180, 180], fill="black")
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    source.save(a)
    source.resize((512, 664)).save(b)
    assert images.compare_image(a, b, THRESHOLDS)["status"] == "passed"
    source.transpose(Image.Transpose.ROTATE_180).save(b)
    assert images.compare_image(a, b, THRESHOLDS)["status"] == "failed"


def test_archive_member_requires_full_identity():
    good = tarfile.TarInfo("Images/cs/doc/doc_2.png")
    bad = tarfile.TarInfo("Images/other/doc/doc_2.png")
    assert images.find_member([good, bad], "cs/doc/doc_2.png") is good
    with pytest.raises(ValueError, match="uniquely"):
        images.find_member([bad], "cs/doc/doc_2.png")
    with pytest.raises(ValueError, match="uniquely"):
        images.find_member([good, good], "cs/doc/doc_2.png")


def test_gold_conversion_consistency_is_not_candidate_overlap():
    result = review.coordinate_consistency([100, 200, 300, 800], [100, 100, 300, 400], [1000, 2000])
    assert result["passed"] and result["max_error_0_1000_units"] == 0
    assert not review.coordinate_consistency([100, 200, 300, 800], [.1, .1, .3, .4], [1000, 2000])["passed"]


def test_image_table_text_is_explicitly_blocked_by_legacy_selector():
    probe = review.text_contract_probe()
    assert probe["text"]["preserves_parsed_text"]
    for kind in ("image", "table"):
        assert probe[kind]["selected_field"] == "ocr_text"
        assert not probe[kind]["legacy_preserves_parsed_text"]
        assert probe[kind]["preserves_parsed_text"]



def test_external_full_prep_reuses_only_identity_and_hash_verified_pages(tmp_path, monkeypatch):
    import importlib.util
    import json
    import sys

    script = Path(__file__).resolve().parents[2] / "scripts/prepare_route_v2_external_full.py"
    sys.path.insert(0, str(script.parent))
    spec = importlib.util.spec_from_file_location("prepare_route_v2_external_full_test", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    previous = tmp_path / "20261008_002104"
    (previous / "pdfs").mkdir(parents=True)
    raw = previous / "raw.json"
    render = previous / "render.png"
    image = previous / "image.png"
    pdf = previous / "pdfs" / "doc.pdf"
    raw.write_text(json.dumps({"pages": [{"page_idx": 0}]}), encoding="utf-8")
    for path, data in ((render, b"render"), (image, b"image"), (pdf, b"pdf")):
        path.write_bytes(data)
    page = {"page_id": "page", "doc_id": "doc", "page_number": 1, "pdf_page_index": 0,
            "official_image_relative_path": "cs/doc/doc_1.png"}
    pdf_member = tarfile.TarInfo("PDFs/doc_source.pdf")
    image_member = tarfile.TarInfo("Images/cs/doc/doc_1.png")
    pdf_archive, image_archive = tmp_path / "PDF.tar", tmp_path / "Images.tar"
    monkeypatch.setattr(module, "member_sha256s", lambda archive, members: {
        member.name: module.sha256(pdf if archive == pdf_archive else image) for member in members
    })
    receipt = {**page, "status": "passed", "candidate_count": 1, "raw_output": str(raw),
               "raw_sha256": module.sha256(raw), "pdf_member": pdf_member.name,
               "render": {"render_path": str(render), "render_sha256": module.sha256(render)},
               "image": {"path": str(image), "sha256": module.sha256(image),
                         "archive_member": "Images/cs/doc/doc_1.png", "mapping": {"status": "passed"}}}
    manifest_sha = "387b2f498ec4bb54abb7aab0a149ef46aa7856c284d2472541d61a7940d0347d"
    (previous / "audit.json").write_text(json.dumps({"status": "blocked_page_failures", "unique_pages": 837,
                                                        "manifest_sha256": manifest_sha}), encoding="utf-8")
    (previous / "page_receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    candidate = {"page_id": "page", "doc_id": "doc", "page_number": 1, "pdf_page_index": 0,
                 "layout_id": 1, "candidate_id": "page:block:1", "text": "left\u2028right"}
    (previous / "candidates.jsonl").write_text(json.dumps(candidate, ensure_ascii=False) + "\n", encoding="utf-8")
    reused, rows, diagnostics = module.load_reusable_pages(
        previous, {"manifest_sha256": manifest_sha}, [page],
        pdf_archive, [pdf_member], image_archive, [image_member],
    )
    assert set(reused) == {"page"} and rows["page"] == [candidate]
    assert diagnostics["malformed_candidate_lines"] == []
    raw.write_text('{"pages": [{"page_idx": 1}]}', encoding="utf-8")
    reused, rows, diagnostics = module.load_reusable_pages(
        previous, {"manifest_sha256": manifest_sha}, [page],
        pdf_archive, [pdf_member], image_archive, [image_member],
    )
    assert reused == {} and rows == {}
    assert diagnostics["invalid_candidate_pages"] == []
    raw.write_text(json.dumps({"pages": [{"page_idx": 0}]}), encoding="utf-8")
    receipt["raw_sha256"] = module.sha256(raw)
    (previous / "page_receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    (previous / "candidates.jsonl").write_text(json.dumps(candidate) + '\n{"broken":\n', encoding="utf-8")
    reused, rows, diagnostics = module.load_reusable_pages(
        previous, {"manifest_sha256": manifest_sha}, [page],
        pdf_archive, [pdf_member], image_archive, [image_member],
    )
    assert set(reused) == {"page"} and rows["page"] == [candidate]
    assert diagnostics["malformed_candidate_lines"] == [2]


def test_render_uses_pymupdf_pixel_bounds_for_fractional_page_size(tmp_path, monkeypatch):
    import importlib.util
    import sys

    import pymupdf

    script = Path(__file__).resolve().parents[2] / "scripts/prepare_route_v2_external_full.py"
    sys.path.insert(0, str(script.parent))
    spec = importlib.util.spec_from_file_location("prepare_route_v2_external_full_render_test", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    pdf = tmp_path / "fractional.pdf"
    document = pymupdf.open()
    document.new_page(width=595.2, height=841.92)
    document.save(pdf)
    document.close()
    result = module.render_page(pdf, {"page_number": 1, "pdf_page_index": 0}, tmp_path / "render.png", 2.0)
    assert result["page_size"] == [1191, 1684]
    assert result["pixel_bounds"] == [0, 0, 1191, 1684]
    assert result["pixel_origin"] == [0, 0]


def test_empty_text_is_not_padding_and_empty_page_has_zero_nodes():
    row = {"layout_id": 0, "type": "text", "text": "", "bbox": [0, 0, 50, 50], "page_size": [100, 100]}
    assert review.node_text(row)[0] == ""
    layout = review.page_layout([row], torch.zeros((1, review.TEXT_DIM)))
    assert layout["mask"].dtype == torch.bool and layout["mask"].tolist() == [True]
    assert torch.count_nonzero(layout["text"]) == 0
    empty = review.page_layout([], torch.zeros((0, review.TEXT_DIM)))
    assert empty["mask"].shape == (0,) and empty["W_raw"].shape == (1024, 0)
