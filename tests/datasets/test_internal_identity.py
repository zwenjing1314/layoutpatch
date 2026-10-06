"""Synthetic identity audit tests; no benchmark files or gold labels are read."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_route_v2_internal_duplicates.py"
SPEC = importlib.util.spec_from_file_location("internal_identity_audit", SCRIPT)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def synthetic_pages(docs, texts, phashes=None, thumbnails=None):
    pages = {}
    records = []
    for index, doc in enumerate(docs):
        pages[doc] = pages.get(doc, 0) + 1
        records.append({"doc_id": doc, "page": pages[doc], "image_std": 70.0,
                        "phash": index if phashes is None else phashes[index],
                        "image_bytes_sha256": f"synthetic-{index}"})
    if thumbnails is None:
        image = np.indices((32, 32)).sum(axis=0) % 2 * 255
        thumbnails = np.stack([image.astype(np.uint8) for _ in records])
    return records, thumbnails, texts


def long_text(prefix, count=120):
    return " ".join(f"{prefix}{index}" for index in range(count))


def test_reformatted_duplicate_pages_form_doc_group_and_preserve_inputs():
    text1, text2 = long_text("alpha"), long_text("beta")
    inputs = synthetic_pages(["A", "A", "B", "B"], [text1, text2, text1.upper(), text2])
    before = copy.deepcopy(inputs[0])
    result = audit.audit_records(*inputs, {"A": "dev_eval", "B": "test_eval"})
    assert result["confirmed_doc_groups"] == [["A", "B"]]
    assert result["confirmed_doc_pairs"][0]["distinct_matching_pages"] == {"A": 2, "B": 2}
    assert inputs[0] == before
    assert text1 not in json.dumps(result)
    assert result["training_performed"] is False


def test_same_template_different_body_rejected_even_identical_phash():
    result = audit.audit_records(*synthetic_pages(
        ["A", "B"], [long_text("red"), long_text("blue")], phashes=[123, 123]
    ))
    assert not result["confirmed_doc_groups"]
    assert not result["unknown_doc_groups"]
    assert result["page_pair_evidence"][0]["status"] == "rejected"
    assert result["page_pair_evidence"][0]["text_jaccard"] == 0


def test_image_without_text_remains_unknown():
    result = audit.audit_records(*synthetic_pages(["A", "B"], ["", ""], phashes=[55, 55]))
    assert result["unknown_doc_groups"] == [["A", "B"]]
    assert not result["confirmed_doc_groups"]
    assert result["page_pair_evidence"][0]["reason"] == "image_match_without_sufficient_ocr_body"


def test_blank_and_header_only_pages_do_not_link_documents():
    images = np.full((3, 32, 32), 255, dtype=np.uint8)
    images[1:, :3, :] = 0
    result = audit.audit_records(*synthetic_pages(
        ["A", "B", "C"], ["", "UNIVERSITY HEADER", "UNIVERSITY HEADER"],
        phashes=[0, 0, 0], thumbnails=images
    ))
    assert result["counts"]["candidate_page_pairs"] == 0
    assert not result["unknown_doc_groups"]


def test_repetitive_header_text_cannot_satisfy_eighty_token_rule():
    text = "university copyright " * 80
    result = audit.audit_records(*synthetic_pages(["A", "B"], [text, text], phashes=[2, 2]))
    assert result["counts"]["repetitive_text_pages_suppressed"] == 2
    assert not result["page_pair_evidence"]


def test_single_shared_frontmatter_page_not_whole_document_equivalence():
    common = long_text("copyright")
    result = audit.audit_records(*synthetic_pages(
        ["A", "A", "B", "B"], [common, long_text("red"), common, long_text("blue")]
    ))
    assert not result["confirmed_doc_groups"]
    assert result["unknown_doc_groups"] == [["A", "B"]]
    assert result["singleton_page_overlap_pairs"][0]["matching_page_pairs"] == 1


def test_two_single_page_documents_can_be_confirmed():
    text = long_text("content")
    result = audit.audit_records(*synthetic_pages(["A", "B"], [text, text]))
    assert result["confirmed_doc_groups"] == [["A", "B"]]


def test_same_document_pairs_ignored():
    text = long_text("content")
    result = audit.audit_records(*synthetic_pages(["A", "A"], [text, text]))
    assert not result["page_pair_evidence"]


def test_source_alignment_and_duplicate_keys_rejected():
    rows, images, text = synthetic_pages(["A", "B"], ["", ""])
    with pytest.raises(ValueError, match="align exactly"):
        audit.audit_records(rows, images[:1], text)
    rows[1] = dict(rows[0])
    with pytest.raises(ValueError, match="Duplicate"):
        audit.audit_records(rows, images, text)


def test_no_text_phash_distance_above_four_does_not_generate_pair():
    result = audit.audit_records(*synthetic_pages(["A", "B"], ["", ""], phashes=[0, 31]))
    assert not result["page_pair_evidence"]


def test_exact_long_text_survives_frequent_shingles_without_image_candidates():
    # Sixty-six copies exceed the posting-frequency filter of 64. Blank
    # thumbnails prevent image matching, so only the exact-text channel can win.
    docs = [doc for doc in ("A", "B", "C") for _ in range(22)]
    text = long_text("shared")
    texts = [text if index % 2 else text.upper().replace(" ", "\n  ") for index in range(66)]
    thumbnails = np.full((66, 32, 32), 255, dtype=np.uint8)
    result = audit.audit_records(*synthetic_pages(docs, texts, thumbnails=thumbnails))
    assert result["confirmed_doc_groups"] == [["A", "B", "C"]]
    assert result["counts"]["pages_image_eligible"] == 0
    assert all(row["candidate_kinds"] == ["exact_normalized_long_text"]
               for row in result["page_pair_evidence"])
