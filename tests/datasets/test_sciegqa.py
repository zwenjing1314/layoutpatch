"""SciEGQA元数据适配的合成测试；不读取真实外部题目或gold。"""
from layoutpatch.datasets.sciegqa import FIELDS, metadata_manifest


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
