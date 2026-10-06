"""Versioned layout inputs for new adapters; historical caches are unchanged."""

from __future__ import annotations

from collections.abc import Mapping

TYPE_SCHEMA = "layout-types-v1"
# IDs preserve the table/image order used by the original fusion training script.
TYPE_TO_ID = {"UNK": 0, "text": 1, "title": 2, "table": 3, "image": 4, "equation": 5}
_TYPE_ALIASES = {
    "paragraph": "text",
    "table_block": "table",
    "figure": "image",
    "interline_equation": "equation",
}


def canonical_layout_type(raw_type: object) -> str:
    """Return a canonical type; missing or unfamiliar labels retain an UNK node."""
    if not isinstance(raw_type, str):
        return "UNK"
    name = raw_type.strip().lower()
    name = _TYPE_ALIASES.get(name, name)
    return name if name in TYPE_TO_ID else "UNK"


def layout_type_id(raw_type: object) -> int:
    """Use the same ID vocabulary for raw labels and prepared node aliases."""
    return TYPE_TO_ID[canonical_layout_type(raw_type)]


def ocr_text_with_source(row: Mapping[str, object]) -> tuple[str, str]:
    """Select explicit OCR only; generic text and VLM descriptions have unknown provenance."""
    value = row.get("ocr_text")
    if value is None or (isinstance(value, str) and not value.strip()):
        return "", "missing"
    if not isinstance(value, str):
        raise ValueError("ocr_text must be a string or null; text/VLM fallback is forbidden")
    return value, "ocr_text"
