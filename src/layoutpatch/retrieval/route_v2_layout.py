"""D 的文档侧输入与组合接口；不接收问题或gold。"""
from __future__ import annotations

import json
from pathlib import Path

import torch
from torch import nn

from layoutpatch.layout.correspondence import clamp_bbox, correspondence_row, scale_bbox_to_model
from layoutpatch.layout.nodes import TextLayoutEncoder
from layoutpatch.layout.schema import TYPE_TO_ID, canonical_layout_type
from layoutpatch.retrieval.colpali_layout import split_page_embedding
from layoutpatch.retrieval.fusion.sparse_fusion import SparseLocalFusionV2
from layoutpatch.retrieval.route_v2_query_cache import file_sha256

TEXT_DIM = 1024
TEXT_RULE = "mmdocir-official-ocr-by-type-v1"
EXTERNAL_TEXT_RULE = "external-parser-text-by-type-v1"


def node_text(row: dict) -> tuple[str, str]:
    kind = canonical_layout_type(row["type"])
    if kind in {"text", "title", "equation"}:
        field = "text"
    elif kind in {"image", "table"}:
        field = "ocr_text"
    else:
        raise ValueError(f"unresolved text provenance for type: {row['type']}")
    value = row.get(field)
    if value is None:
        return "", field
    if not isinstance(value, str):
        raise ValueError(f"non-string {field}")
    return value.strip(), field


def external_node_text(row: dict) -> tuple[str, str]:
    """读取外部解析器的真实文本；不回退到VLM描述，也不伪称OCR。"""
    kind = canonical_layout_type(row["type"])
    if kind not in {"text", "title", "equation", "image", "table"}:
        raise ValueError(f"unresolved external text provenance for type: {row['type']}")
    value = row.get("text")
    if value is None:
        return "", row.get("text_source", "unknown")
    if not isinstance(value, str):
        raise ValueError("non-string external text")
    source = row.get("text_source", "unknown")
    if source not in {"unknown", "mixed", "native_PDF", "OCR"}:
        source = "unknown"
    return value.strip(), source


def page_layout(rows: list[dict], text: torch.Tensor) -> dict[str, torch.Tensor]:
    """调用者先按layout_id排序；每页完整候选，不按query/gold挑节点。"""
    if [r["layout_id"] for r in rows] != sorted(r["layout_id"] for r in rows):
        raise ValueError("nodes must be sorted by layout_id")
    if text.shape != (len(rows), TEXT_DIM):
        raise ValueError("text must be [M,1024]")
    coords, weights, types = [], [], []
    for r in rows:
        b = clamp_bbox(scale_bbox_to_model(r["bbox"], r["page_size"]))
        x1, y1, x2, y2 = [v / 448 for v in b]
        coords.append([x1, y1, x2, y2, x2 - x1, y2 - y1])
        weights.append(correspondence_row(r["bbox"], r["page_size"]))
        types.append(TYPE_TO_ID[canonical_layout_type(r["type"])])
    raw = torch.tensor(weights, dtype=torch.float32).reshape(len(rows), 1024).T.contiguous()
    mass = raw.sum(-1, keepdim=True)
    attn = torch.where(mass > 0, raw / mass.clamp_min(1e-12), raw)
    return {"text": text.float(), "coords": torch.tensor(coords, dtype=torch.float32).reshape(-1, 6),
            "types": torch.tensor(types, dtype=torch.long), "mask": torch.ones(len(rows), dtype=torch.bool),
            "W_raw": raw, "W_attn": attn, "cover_mass": mass}


class LayoutInputs:
    """为既有Inputs追加页面节点；缓存命中由页面而不是query决定。"""
    def __init__(self, base, cache: Path, expected_manifest_sha256: str):
        self.base = base
        self.units = base.units
        self.cache = cache
        manifest_path = cache / "manifest.json"
        if file_sha256(manifest_path) != expected_manifest_sha256:
            raise ValueError("node manifest identity mismatch")
        manifest = json.loads(manifest_path.read_text("utf-8"))
        self.pages = {(r["doc_id"], r["page"]): r for r in manifest["pages"]}
        if len(self.pages) != len(manifest["pages"]):
            raise ValueError("duplicate node page ID")
        self.loaded = {}

    def item(self, unit):
        key = unit["doc_id"], unit["page"]
        record = self.pages[key]
        if record["role"] != unit["role"]:
            raise ValueError("node role mismatch")
        if key not in self.loaded:
            path = self.cache / record["file"]
            if file_sha256(path) != record["sha256"]:
                raise ValueError("node file hash mismatch")
            payload = torch.load(path, weights_only=True, map_location="cpu")
            if (payload["doc_id"], payload["page"]) != key:
                raise ValueError("node page identity mismatch")
            _, ids = self.base.boxes(unit)
            if set(ids) != {n["layout_id"] for n in payload["nodes"]}:
                raise ValueError("node/candidate ID mismatch")
            self.loaded[key] = payload["layout"]
        return {**self.base.item(unit), "layout": self.loaded[key]}

    def boxes(self, unit):
        return self.base.boxes(unit)

    def iou(self, unit):
        return self.base.iou(unit)


class LayoutPatchD(nn.Module):
    """组合已有两模块；参数学习范围只有节点编码器与融合器。"""
    def __init__(self):
        super().__init__()
        self.nodes = TextLayoutEncoder(TEXT_DIM, len(TYPE_TO_ID))
        self.fusion = SparseLocalFusionV2(top_k=4)

    def forward(self, patches: torch.Tensor, layout: dict[str, torch.Tensor]) -> torch.Tensor:
        nodes = self.nodes(layout["text"][None], layout["coords"][None], layout["types"][None], layout["mask"][None])
        return self.fusion(patches[None], layout["W_attn"][None], nodes, layout["cover_mass"][None],
                           node_mask=layout["mask"][None])[0]

    def forward_page(self, page: torch.Tensor, layout: dict[str, torch.Tensor]) -> torch.Tensor:
        patches, prompt = split_page_embedding(page)
        return torch.cat((self(patches, layout), prompt), dim=0)
