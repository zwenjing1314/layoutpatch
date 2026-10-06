"""Synthetic checks for the new, explicitly versioned layout input schema."""

from __future__ import annotations

import pytest

from layoutpatch.layout.schema import (
    canonical_layout_type,
    layout_type_id,
    ocr_text_with_source,
)


@pytest.mark.parametrize(
    ("raw", "canonical", "type_id"),
    [
        ("text", "text", 1),
        ("paragraph", "text", 1),
        ("title", "title", 2),
        ("table", "table", 3),
        ("table_block", "table", 3),
        ("image", "image", 4),
        ("figure", "image", 4),
        ("equation", "equation", 5),
        ("interline_equation", "equation", 5),
        (" IMAGE ", "image", 4),
        ("UNK", "UNK", 0),
        ("unrecognized", "UNK", 0),
        (None, "UNK", 0),
        ("", "UNK", 0),
        (4, "UNK", 0),
    ],
)
def test_type_aliases_preserve_historical_embedding_ids(raw, canonical, type_id) -> None:
    assert canonical_layout_type(raw) == canonical
    assert layout_type_id(raw) == type_id


def test_only_explicit_ocr_has_verified_text_provenance() -> None:
    row = {"text": "unverified generic", "ocr_text": "read from page", "vlm_text": "generated"}
    assert ocr_text_with_source(row) == ("read from page", "ocr_text")
    assert row["text"] == "unverified generic"


@pytest.mark.parametrize("ocr", [None, "", " \n "])
def test_missing_ocr_never_falls_back_to_generic_or_vlm(ocr) -> None:
    assert ocr_text_with_source({"ocr_text": ocr, "text": "generic", "vlm_text": "generated"}) == (
        "", "missing"
    )
    assert ocr_text_with_source({"text": "generic", "vlm_text": "generated"}) == ("", "missing")


def test_nontext_ocr_is_rejected_instead_of_silently_stringified() -> None:
    with pytest.raises(ValueError, match="ocr_text must be a string"):
        ocr_text_with_source({"ocr_text": ["not", "a string"]})
