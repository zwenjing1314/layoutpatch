"""仅用合成页检查当前MinerU输出适配；不运行模型或外部评分。"""
from copy import deepcopy

import pytest

from layoutpatch.datasets.mineru import check_scoring_structure, export_page


def fixture():
    identity = {"doc_id": "synthetic", "page_id": "synthetic_p1", "page_number": 2, "pdf_page_index": 1}
    render = {"pdf_size_points": [612, 792], "page_size": [1224, 1584], "rotation": 0,
              "cropbox": [0, 0, 612, 792], "mediabox": [0, 0, 612, 792]}
    payload = {"schema": "docvortex.middle", "schema_version": "2.0",
               "extensions": {"docvortex_layout": {"version": 1, "pages": [{"page_idx": 1, "width_pt": 612, "height_pt": 792}]}},
               "pages": [{"page_idx": 1, "blocks": [{"type": "paragraph_title", "index": 0,
                          "bbox": [.1, .2, .5, .4], "content": [{"type": "text", "content": "synthetic"}]}]}]}
    return payload, identity, render


def test_unit_frame_export_and_existing_interface():
    payload, identity, render = fixture()
    before = deepcopy(payload)
    candidates, audit = export_page(payload, identity, render)
    row = candidates[0]
    assert row["bbox"] == pytest.approx([122.4, 316.8, 612, 633.6])
    assert row["type"] == "title" and row["layout_id"] == 0
    assert row["text"] == "synthetic" and row["ocr_text"] is None
    assert audit["invalid_boxes"] == audit["out_of_bounds_boxes"] == 0
    assert payload == before
    assert check_scoring_structure(candidates, render)["scores_computed"] is False


@pytest.mark.parametrize("box", [[0, 0, 1000, 1000], [0, 0, 0, 1], [0, 0, float("nan"), 1]])
def test_invalid_or_wrong_coordinate_scale_stops_without_clipping(box):
    payload, identity, render = fixture()
    payload["pages"][0]["blocks"][0]["bbox"] = box
    with pytest.raises(ValueError, match="no clipping"):
        export_page(payload, identity, render)


def test_identity_rotation_and_geometry_guard():
    payload, identity, render = fixture()
    payload["pages"][0]["page_idx"] = 0
    with pytest.raises(ValueError, match="source page"):
        export_page(payload, identity, render)
    payload, identity, render = fixture()
    render["rotation"] = 90
    with pytest.raises(ValueError, match="rotation"):
        export_page(payload, identity, render)
    payload, identity, render = fixture()
    render["pdf_size_points"] = [792, 612]
    with pytest.raises(ValueError, match="frame mismatch"):
        export_page(payload, identity, render)


def test_duplicates_and_empty_pages_are_reported_not_silently_removed():
    payload, identity, render = fixture()
    other = deepcopy(payload["pages"][0]["blocks"][0])
    other["index"] = 1
    payload["pages"][0]["blocks"].append(other)
    candidates, audit = export_page(payload, identity, render)
    assert len(candidates) == 2 and audit["duplicate_boxes"] == 1
    payload["pages"][0]["blocks"] = []
    candidates, audit = export_page(payload, identity, render)
    assert candidates == [] and audit["no_candidates"]
