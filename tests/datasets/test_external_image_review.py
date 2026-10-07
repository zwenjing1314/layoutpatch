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
        assert not probe[kind]["preserves_parsed_text"]


def test_empty_text_is_not_padding_and_empty_page_has_zero_nodes():
    row = {"layout_id": 0, "type": "text", "text": "", "bbox": [0, 0, 50, 50], "page_size": [100, 100]}
    assert review.node_text(row)[0] == ""
    layout = review.page_layout([row], torch.zeros((1, review.TEXT_DIM)))
    assert layout["mask"].dtype == torch.bool and layout["mask"].tolist() == [True]
    assert torch.count_nonzero(layout["text"]) == 0
    empty = review.page_layout([], torch.zeros((0, review.TEXT_DIM)))
    assert empty["mask"].shape == (0,) and empty["W_raw"].shape == (1024, 0)
