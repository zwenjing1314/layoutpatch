"""仅用合成页检查当前MinerU输出适配；不运行模型或外部评分。"""
from copy import deepcopy

import pytest

from layoutpatch.datasets.mineru import check_scoring_structure, export_page
from layoutpatch.retrieval.route_v2_layout import external_node_text, node_text


def fixture():
    identity = {"doc_id": "synthetic", "page_id": "synthetic_p1", "page_number": 2, "pdf_page_index": 1}
    render = {"pdf_size_points": [612, 792], "page_size": [1224, 1584], "rotation": 0,
              "cropbox": [0, 0, 612, 792], "mediabox": [0, 0, 612, 792], "render_scale": 2.0,
              "pdf_to_render_matrix": [1, 0, 0, 1, 0, 0]}
    payload = {"schema": "docvortex.middle", "schema_version": "2.0",
               "extensions": {"docvortex_layout": {"version": 1, "pages": [{"page_idx": 1, "width_pt": 612, "height_pt": 792}]}},
               "pages": [{"page_idx": 1, "blocks": [{"type": "paragraph_title", "index": 0,
                          "bbox": [.1, .2, .5, .4], "content": [{"type": "text", "content": "synthetic"}]}]}]}
    return payload, identity, render


def test_external_chart_text_is_preserved_and_source_is_honest():
    row = {"type": "image", "text": "chart labels", "ocr_text": None,
           "vlm_text": "generated description", "text_source": "unknown"}
    assert external_node_text(row) == ("chart labels", "unknown")
    assert external_node_text({**row, "text_source": "mixed"}) == ("chart labels", "mixed")


def test_external_real_empty_text_is_retained_as_missing():
    row = {"type": "table", "text": "", "ocr_text": None, "vlm_text": "bad",
           "text_source": "unknown"}
    assert external_node_text(row) == ("", "unknown")


def test_legacy_text_rule_remains_unchanged():
    assert node_text({"type": "image", "text": "parsed", "ocr_text": None}) == ("", "ocr_text")


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
    render["page_size"] = [1584, 1224]
    render["page_rect"] = [0, 0, 792, 612]
    render["pdf_to_render_matrix"] = [0, 1, -1, 0, 792, 0]
    candidates, audit = export_page(payload, identity, render)
    assert audit["parser_coordinate_frame"] == "unrotated_media_points"
    assert candidates[0]["bbox"] == pytest.approx([950.4, 122.4, 1267.2, 612.0])
    payload, identity, render = fixture()
    render["rotation"] = 90
    render["page_size"] = [1584, 1224]
    render["page_rect"] = [0, 0, 792, 612]
    render["pdf_to_render_matrix"] = [0, 1, -1, 0, 792, 0]
    payload["extensions"]["docvortex_layout"]["pages"][0].update({"width_pt": 792, "height_pt": 612})
    candidates, audit = export_page(payload, identity, render)
    assert audit["parser_coordinate_frame"] == "rotated_page_points"
    assert audit["parser_to_render_matrix"] == [1, 0, 0, 1, 0, 0]
    assert candidates[0]["bbox"] == pytest.approx([158.4, 244.8, 792.0, 489.6])
    payload, identity, render = fixture()
    render["cropbox"] = [0, 0, 600, 792]
    with pytest.raises(ValueError, match="CropBox differs"):
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
