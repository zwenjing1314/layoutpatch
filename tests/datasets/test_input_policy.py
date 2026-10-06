"""Adapter versioning tests use only small synthetic files under pytest tmp_path."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from layoutpatch.datasets import prepare_dataset, prepare_mmdocir
from layoutpatch.evaluation.region_labels import read_region_labels
from layoutpatch.io import read_processed_dataset


def _synthetic_raw(
    tmp_path: Path, monkeypatch, doc_name: str = "paper.pdf", *, with_mapping: bool = False
) -> Path:
    data_dir = tmp_path / "data"
    raw_dir = tmp_path / "synthetic-raw"
    raw_dir.mkdir()
    monkeypatch.setenv("LAYOUTPATCH_DATA_ROOT", str(data_dir))
    monkeypatch.setenv("LAYOUTPATCH_MMDOCIR_EVALUATION_ROOT", str(raw_dir))
    annotation = {
        "doc_name": doc_name,
        "questions": [{"Q": "synthetic question", "A": "synthetic answer", "page_id": [0]}],
    }
    if with_mapping:
        annotation["questions"][0]["layout_mapping"] = [
            {"page": 0, "bbox": [0.0, 0.0, 10.0, 1.0], "page_size": [20.0, 20.0]}
        ]
    (raw_dir / "MMDocIR_annotations.jsonl").write_text(json.dumps(annotation) + "\n", encoding="utf-8")
    pl.DataFrame([{
        "doc_name": doc_name, "passage_id": 0, "image_path": "page.png",
        "image_binary": b"synthetic bytes", "ocr_text": "", "vlm_text": "generated page",
    }]).write_parquet(raw_dir / "MMDocIR_pages.parquet")
    types = ["image", "equation", "table", "figure", "unknown"]
    pl.DataFrame([
        {
            "doc_name": doc_name, "page_id": 0, "layout_id": index, "type": kind,
            "bbox": [0.0, float(index), 10.0, float(index + 1)],
            "text": "generic text" if index == 0 else "",
            "ocr_text": "explicit OCR" if index == 0 else "",
            "vlm_text": "generated description",
        }
        for index, kind in enumerate(types)
    ]).write_parquet(raw_dir / "MMDocIR_layouts.parquet")
    return data_dir


def test_default_legacy_preserves_historical_node_mapping_and_fallback(tmp_path, monkeypatch) -> None:
    _synthetic_raw(tmp_path, monkeypatch)
    result = prepare_mmdocir()
    documents, pages, nodes, queries = read_processed_dataset(result.processed_dir)
    assert (result.documents, result.pages, result.nodes, result.queries) == (1, 1, 5, 1)
    assert [node.node_type for node in nodes] == ["paragraph", "paragraph", "table_block", "figure", "paragraph"]
    assert nodes[0].text == "generic text"
    assert nodes[1].text == "generated description"
    assert pages[0].page_text == "generated page"
    assert documents[0].metadata == {}
    assert nodes[0].metadata == {}
    assert queries[0].metadata == {"mmdocir_layout_count": 0}


def test_v2_writes_new_ocr_only_inputs_without_touching_legacy(tmp_path, monkeypatch) -> None:
    data_dir = _synthetic_raw(tmp_path, monkeypatch)
    legacy = prepare_mmdocir()
    old_files = {
        path: path.read_bytes()
        for directory in (legacy.processed_dir, data_dir / "interim" / "mmdocir_evaluation")
        for path in directory.rglob("*")
        if path.is_file()
    }
    result = prepare_dataset("mmdocir", output_dataset="mmdocir_v2_fixture", input_policy="v2_ocr_only")
    documents, pages, nodes, queries = read_processed_dataset(result.processed_dir)
    assert [node.node_type for node in nodes] == ["image", "equation", "table", "image", "UNK"]
    assert [node.metadata["layout_type_id"] for node in nodes] == [4, 5, 3, 4, 0]
    assert nodes[0].text == "explicit OCR"
    assert nodes[0].metadata["text_source"] == "ocr_text"
    assert nodes[0].metadata["raw_type"] == "image"
    assert all(node.text == "" and node.metadata["text_source"] == "missing" for node in nodes[1:])
    assert pages[0].page_text == ""
    assert pages[0].metadata["text_source"] == "missing"
    image_path = Path(pages[0].page_image_path)
    assert image_path.parent.parent == data_dir / "interim" / "mmdocir_v2_fixture" / "page_images"
    assert image_path.name == "p0.png"
    assert image_path.read_bytes() == b"synthetic bytes"
    for record in [*documents, *pages, *nodes, *queries]:
        assert record.metadata["input_policy"] == "v2_ocr_only"
        assert record.metadata["type_schema"] == "layout-types-v1"
    for path, content in old_files.items():
        assert path.read_bytes() == content


@pytest.mark.parametrize("doc_name", ["paper.v1.pdf", "paper.v1"])
def test_v2_keeps_dots_in_document_identity(tmp_path, monkeypatch, doc_name) -> None:
    _synthetic_raw(tmp_path, monkeypatch, doc_name=doc_name, with_mapping=True)
    result = prepare_mmdocir(
        output_dataset="mmdocir_v2_fixture", input_policy="v2_ocr_only", with_region_labels=True
    )
    documents, pages, nodes, queries = read_processed_dataset(result.processed_dir)
    assert result.pages == 1
    assert result.nodes == 5
    assert all(record.doc_id == "paper.v1" for record in [*documents, *pages, *nodes, *queries])
    assert queries[0].evidence_page_ids == [pages[0].page_id]
    labels = read_region_labels(result.processed_dir)
    assert len(labels) == 1
    assert labels[0].query_id == queries[0].query_id
    assert labels[0].doc_id == queries[0].doc_id == nodes[0].doc_id
    assert labels[0].page_id == pages[0].page_id == nodes[0].page_id
    assert labels[0].node_id == nodes[0].node_id == queries[0].evidence_node_ids[0]
    assert labels[0].source == "matched"


def test_v2_image_identity_includes_document_and_page(tmp_path, monkeypatch) -> None:
    _synthetic_raw(tmp_path, monkeypatch)
    raw_dir = tmp_path / "synthetic-raw"
    annotations_path = raw_dir / "MMDocIR_annotations.jsonl"
    first = json.loads(annotations_path.read_text(encoding="utf-8"))
    second = {**first, "doc_name": "another.pdf"}
    annotations_path.write_text(
        json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8"
    )
    page_rows = pl.read_parquet(raw_dir / "MMDocIR_pages.parquet").to_dicts()
    page_rows.extend([
        {**page_rows[0], "doc_name": "another.pdf", "image_binary": b"second document"},
        {**page_rows[0], "passage_id": 1, "image_binary": b"second page"},
    ])
    pl.DataFrame(page_rows).write_parquet(raw_dir / "MMDocIR_pages.parquet")
    result = prepare_mmdocir(output_dataset="mmdocir_v2_fixture", input_policy="v2_ocr_only")
    _, pages, _, _ = read_processed_dataset(result.processed_dir)
    paths = {page.page_id: Path(page.page_image_path) for page in pages}
    assert len(set(paths.values())) == 3
    assert paths["paper_p0"].read_bytes() == b"synthetic bytes"
    assert paths["another_p0"].read_bytes() == b"second document"
    assert paths["paper_p1"].read_bytes() == b"second page"


@pytest.mark.parametrize("output", [None, "", "mmdocir_evaluation", "MMDOCIR_EVALUATION", "mmdocir", "../escape", "nested/path", "nested\\path", "mmdocir_evaluation.", "C:\\absolute"])
def test_v2_rejects_legacy_or_unsafe_destination_before_reading_raw(tmp_path, monkeypatch, output) -> None:
    monkeypatch.setenv("LAYOUTPATCH_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("LAYOUTPATCH_MMDOCIR_EVALUATION_ROOT", str(tmp_path / "absent"))
    with pytest.raises(ValueError, match="new explicit output_dataset"):
        prepare_mmdocir(output_dataset=output, input_policy="v2_ocr_only")
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("stage", ["processed", "interim"])
def test_v2_rejects_existing_destinations_even_without_raw_data(tmp_path, monkeypatch, stage) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("LAYOUTPATCH_DATA_ROOT", str(data_dir))
    monkeypatch.setenv("LAYOUTPATCH_MMDOCIR_EVALUATION_ROOT", str(tmp_path / "absent"))
    existing = data_dir / stage / "mmdocir_v2_fixture"
    existing.mkdir(parents=True)
    sentinel = existing / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="will not overwrite"):
        prepare_mmdocir(output_dataset="mmdocir_v2_fixture", input_policy="v2_ocr_only")
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_unknown_policy_fails_without_creating_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAYOUTPATCH_DATA_ROOT", str(tmp_path / "data"))
    with pytest.raises(ValueError, match="Unknown input_policy"):
        prepare_mmdocir(input_policy="typo")
    assert not (tmp_path / "data").exists()
