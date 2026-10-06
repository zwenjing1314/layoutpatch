"""Identity verification controls contain synthetic text and images only."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

_path = Path(__file__).parents[2] / "scripts" / "verify_route_v2_candidates.py"
_spec = importlib.util.spec_from_file_location("verify_route_v2_candidates", _path)
assert _spec is not None and _spec.loader is not None
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)


def test_long_text_normalization_confirms_reencoding() -> None:
    text = " ".join(f"word{index}" for index in range(100))
    metrics = audit.lexical_metrics(text, text.upper().replace(" ", "\n"))
    assert audit.classify_candidate(metrics, {"ink_dice": 0.0})[0] == "confirmed"


def test_short_text_match_remains_unresolved() -> None:
    metrics = audit.lexical_metrics("annual company report", "annual company report")
    assert audit.classify_candidate(metrics, {"ink_dice": 1.0})[0] == "unresolved"


def test_disagreeing_long_text_and_foreground_reject_template() -> None:
    left = " ".join(f"apple{index}" for index in range(100))
    right = " ".join(f"orange{index}" for index in range(100))
    metrics = audit.lexical_metrics(left, right)
    assert audit.classify_candidate(metrics, {"ink_dice": 0.1})[0] == "rejected_template"
    assert audit.classify_candidate(metrics, {"ink_dice": 0.9})[0] == "unresolved"


def test_missing_text_does_not_turn_similar_images_into_confirmed_identity() -> None:
    metrics = audit.lexical_metrics("", "")
    assert audit.classify_candidate(metrics, {"ink_dice": 1.0})[0] == "unresolved"


def test_ink_metric_survives_scale_but_rejects_shifted_content() -> None:
    first = Image.new("L", (240, 320), 255)
    ImageDraw.Draw(first).rectangle((20, 30, 80, 80), fill=0)
    second = Image.new("L", (240, 320), 255)
    ImageDraw.Draw(second).rectangle((140, 230, 200, 280), fill=0)
    a = audit.image_canvas(first)
    scaled = audit.image_canvas(first.resize((480, 640), Image.Resampling.LANCZOS))
    unrelated = audit.image_canvas(second)
    assert a.shape == (160, 160)
    assert audit.image_metrics(a, scaled)["ink_dice"] > 0.95
    assert audit.image_metrics(a, unrelated)["ink_dice"] < 0.1


def test_white_background_does_not_prove_identity() -> None:
    white = np.ones((160, 160), dtype=np.float32)
    assert audit.image_metrics(white, white)["ink_dice"] == 0


def test_title_phrase_requires_token_boundaries_and_nontrivial_length() -> None:
    assert audit.title_match("Novel mechanisms for memory retrieval", "NOVEL mechanisms for memory retrieval\nAuthor")['matched']
    assert not audit.title_match("Learning systems", "Learning systems")['matched']
    assert not audit.title_match("Novel mechanisms for memory retrieval", "Novelty mechanisms for memories retrieved")['matched']


def test_receipt_rejects_changed_source_or_policy(tmp_path: Path) -> None:
    audit.assert_receipt(tmp_path, {"source": "a", "policy": "v1"})
    audit.assert_receipt(tmp_path, {"source": "a", "policy": "v1"})
    with pytest.raises(RuntimeError, match="changed"):
        audit.assert_receipt(tmp_path, {"source": "b", "policy": "v1"})
