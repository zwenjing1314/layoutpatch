"""SciEGQA元数据适配及冻结配置检查；不读取真实外部题目或gold。"""
from pathlib import Path

import yaml

from layoutpatch.datasets.sciegqa import FIELDS, metadata_manifest


def test_external_preparation_config_keeps_fixed_inputs_and_execution_limits():
    root = Path(__file__).resolve().parents[2]
    cfg = yaml.safe_load((root / "configs/experiments/route_v2_external_v1.yaml").read_text("utf-8"))
    assert cfg["status"] == "frozen"
    assert cfg["primary_candidate"] == "D-no-text"
    assert set(cfg["methods"]) == {"A", "B", "C", "C-wide", "D", "D-no-text"}
    assert cfg["weights"]["seeds"] == [0, 1, 2]
    assert cfg["weights"]["selection"] == "existing_source_val_best_all_seeds"
    assert cfg["input"]["revision"] == "9bdca77be633cc3259d7e3739d35b38ab00bf5d9"
    assert cfg["input"]["questions"] == 1623
    assert cfg["input"]["coordinate_schema"]["normalization_scale"] == 1000
    assert cfg["preparation"]["sample_unique_pages"] == 8
    assert all(cfg["preparation"][key] is False for key in (
        "full_parsing_allowed", "full_visual_encoding_allowed", "scoring_allowed",
        "oracle_allowed", "metrics_allowed", "training_allowed", "download_or_install_allowed",
    ))
    plan = cfg["external_evaluation_plan"]
    assert plan["execution_authorized_this_round"] is False
    assert plan["primary_metric"] == "hit1@0.5"
    assert plan["comparisons"] == ["D-no-text-A", "D-no-text-B", "D-no-text-C-wide"]
    assert plan["multiple_comparisons"]["family_size"] == 3
    assert plan["multiple_comparisons"]["method"] == "Bonferroni_percentile_document_bootstrap_intervals"
    assert cfg["auto_followup"] is False


def test_metadata_manifest_retains_failed_question_and_sorts_pages():
    records = [{"query": "q", "answer": "a", "doc_name": "paper.pdf", "category": "cs",
                "evidence_page": [2, 1], "bbox": [[[1, 2, 10, 20]], [[3, 4, 5, 6]]],
                "rel_bbox": [[[100, 200, 500, 800]], [[200, 300, 400, 500]]], "subimg_type": [["figure"], ["table"]]},
               {key: [] for key in FIELDS}]
    result = metadata_manifest(records)
    assert result["counts"]["questions"] == 2
    assert result["counts"]["unique_evidence_pages"] == 2
    assert result["sample_page_ids"] == ["paper_p0", "paper_p1"]
    assert result["failed_questions_retained"]
    assert result["questions"][0]["errors"] == []
    assert result["questions"][1]["errors"]
    assert not result["gold_coordinates_exported"]


def test_metadata_manifest_rejects_coordinate_and_identity_errors():
    row = {"query": "q", "answer": "a", "doc_name": "..\\evil.pdf", "category": "cs",
           "evidence_page": [1], "bbox": [[[-1, 0, 1, 1]]], "rel_bbox": [[[0, 0, 1001, 1]]],
           "subimg_type": [[1]]}
    result = metadata_manifest([row])
    assert result["counts"]["failed_questions"] == 1
    assert {"invalid_document_identity", "invalid_absolute_box",
            "invalid_relative_box", "invalid_region_type"} <= set(result["questions"][0]["errors"])


def test_one_based_pages_and_nested_arrays_are_required():
    row = {"query": "synthetic", "answer": "synthetic", "doc_name": "paper", "category": "cs",
           "evidence_page": [0], "bbox": [[[1, 2, 10, 20]]], "rel_bbox": [[[100, 200, 500, 800]]],
           "subimg_type": [["text"]]}
    result = metadata_manifest([row])
    assert result["counts"]["failed_questions"] == 1
    assert result["pages"] == []
    assert "invalid_evidence_pages" in result["questions"][0]["errors"]
    row["evidence_page"] = [1, 2]
    result = metadata_manifest([row])
    assert result["counts"]["questions"] == 1
    assert "page_annotation_alignment" in result["questions"][0]["errors"]


def test_first_eight_selection_does_not_depend_on_boxes_or_answers():
    row = {"query": "synthetic", "answer": "synthetic", "doc_name": "paper", "category": "cs",
           "evidence_page": list(range(10, 0, -1)), "bbox": [[[1, 2, 10, 20]]] * 10,
           "rel_bbox": [[[100, 200, 500, 800]]] * 10, "subimg_type": [["text"]] * 10}
    before = metadata_manifest([row])
    row["answer"] = "changed"
    row["rel_bbox"] = [[[0, 0, 1001, 1]]] * 10
    after = metadata_manifest([row])
    assert before["sample_page_ids"] == after["sample_page_ids"] == [f"paper_p{i}" for i in range(8)]
    assert after["counts"]["failed_questions"] == 1
    assert len(after["questions"]) == 1
    assert all(p["render_transform"] is None and p["original_image_size"] is None for p in after["pages"])
