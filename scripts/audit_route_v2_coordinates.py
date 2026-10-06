"""Route-v2 coordinate gate: token layout of cached ColPali pages and bbox/page alignment.

Reads only page images, cached page tensors, layout boxes and the offline processor files.
Never reads questions, answers or gold boxes. Thresholds are fixed below before running.
Output: artifacts/route_v2_data/coordinate_audit_v1.json (never overwritten).
"""

from __future__ import annotations

import glob
import json
import os
import random
import time
from pathlib import Path

import numpy as np
import polars as pl
import torch
from PIL import Image

from layoutpatch.retrieval.colpali import _source_signature
from layoutpatch.retrieval.colpali_layout import NUM_PATCHES, PAGE_TOKENS

os.environ.setdefault("HF_HUB_OFFLINE", "1")
REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts/route_v2_data/coordinate_audit_v1.json"
PAGES = REPO / "data/processed/mmdocir_evaluation/pages.parquet"
LAYOUTS = REPO / "data/raw/mmdocir_evaluation/MMDocIR_layouts.parquet"
CACHE = REPO / "artifacts/colpali/mmdocir_evaluation/vidore_colpali"
MODEL = "vidore/colpali"
POLICY = {
    "probe_pages": 80, "probe_seed": 0, "ink_pages": 120, "ink_seed": 1, "signature_pages": 400,
    "prompt_row_cosine_min": 0.9, "patch_row_cosine_max": 0.6,
    "aspect_rel_tol": 0.01, "aspect_pass_fraction": 0.99,
    "ink_threshold": 0.35, "ink_recall_min": 0.6, "ink_gap_min": 0.05, "ink_win_fraction": 0.8,
}


def processor_layout() -> dict:
    from colpali_engine.models import ColPaliProcessor
    from transformers import GemmaTokenizerFast, SiglipImageProcessor

    pattern = os.path.expanduser("~/.cache/huggingface/hub/models--vidore--colpali/snapshots/*/")
    snap = sorted(glob.glob(pattern))[0]
    proc = ColPaliProcessor(
        image_processor=SiglipImageProcessor.from_pretrained(snap),
        tokenizer=GemmaTokenizerFast.from_pretrained(snap),
    )
    ids = proc.process_images([Image.new("RGB", (600, 800), "white")])["input_ids"][0].tolist()
    image = [i for i, t in enumerate(ids) if t == proc.image_token_id]
    tail = proc.tokenizer.convert_ids_to_tokens([t for t in ids if t != proc.image_token_id])
    return {
        "snapshot": Path(snap).name, "sequence_length": len(ids), "image_tokens": len(image),
        "image_first_index": image[0], "image_last_index": image[-1], "prompt_tokens": tail,
        "image_size": str(proc.image_processor.size),
        "passed": len(ids) == PAGE_TOKENS and image == list(range(NUM_PATCHES)),
    }


def ink_grid(path: str) -> np.ndarray:
    with Image.open(path) as im:
        gray = np.asarray(im.convert("L").resize((448, 448), Image.BICUBIC), dtype=np.float32)
    return (1.0 - gray / 255.0).reshape(32, 14, 32, 14).mean(axis=(1, 3)).reshape(-1)


def embedding_probe(pages: list[dict]) -> dict:
    rng = random.Random(POLICY["probe_seed"])
    sample = rng.sample(pages, POLICY["probe_pages"])
    embs, inks = [], []
    for row in sample:
        payload = torch.load(CACHE / f"{row['page_id']}.pt", map_location="cpu", weights_only=True)
        embs.append(payload["embedding"].float())
        inks.append(ink_grid(row["page_image_path"]))
    stack = torch.nn.functional.normalize(torch.stack(embs), dim=-1)

    def cross_page_cos(rows: range) -> list[float]:
        out = []
        for r in rows:
            v = stack[:, r]
            s = v @ v.T
            n = s.shape[0]
            out.append(float((s.sum() - n) / (n * n - n)))
        return out

    half = len(sample) // 2
    sweep = {}
    for order in ("row", "col"):
        for offset in range(PAGE_TOKENS - NUM_PATCHES + 1):
            xs = [e[offset : offset + NUM_PATCHES].numpy() for e in embs]
            ys = [y if order == "row" else y.reshape(32, 32).T.reshape(-1) for y in inks]
            xtr = np.concatenate([x - x.mean(0) for x in xs[:half]])
            ytr = np.concatenate([y - y.mean() for y in ys[:half]])
            w = np.linalg.solve(xtr.T @ xtr + np.eye(xtr.shape[1]), xtr.T @ ytr)
            rs = [
                float(np.corrcoef((x - x.mean(0)) @ w, y - y.mean())[0, 1])
                for x, y in zip(xs[half:], ys[half:], strict=True)
                if y.std() > 1e-6
            ]
            sweep[f"{order}:{offset}"] = sum(rs) / len(rs)
    best = max(sweep, key=sweep.get)
    head = cross_page_cos(range(0, 7))
    tail = cross_page_cos(range(NUM_PATCHES, PAGE_TOKENS))
    return {
        "pages": len(sample),
        "cross_page_cosine_rows_0_6": head,
        "cross_page_cosine_rows_1024_1030": tail,
        "within_page_ink_corr": sweep,
        "best_hypothesis": best,
        "passed": best == "row:0"
        and min(tail[:6]) >= POLICY["prompt_row_cosine_min"]
        and max(head) <= POLICY["patch_row_cosine_max"],
    }


def page_frames(pages: list[dict]) -> dict:
    sizes = (
        pl.read_parquet(LAYOUTS, columns=["doc_name", "page_id", "page_size"])
        .group_by(["doc_name", "page_id"])
        .agg(pl.col("page_size").first())
    )
    size = {(r["doc_name"], int(r["page_id"])): r["page_size"] for r in sizes.to_dicts()}
    rel, unknown, outliers = [], 0, []
    for row in pages:
        key = (row["doc_id"], int(row["page_index"]) - 1)
        if key not in size:
            unknown += 1
            continue
        w, h = size[key]
        with Image.open(row["page_image_path"]) as im:
            iw, ih = im.size
        diff = abs((iw / ih) / (w / h) - 1.0)
        rel.append(diff)
        if diff > POLICY["aspect_rel_tol"]:
            outliers.append({"page_id": row["page_id"], "image": [iw, ih], "page_size": [w, h]})
    ok = sum(d <= POLICY["aspect_rel_tol"] for d in rel)
    return {
        "pages_with_layout_size": len(rel), "pages_without_layout": unknown,
        "within_tolerance": ok, "max_rel_diff": max(rel), "outliers": outliers[:20],
        "outlier_count": len(outliers),
        "passed": ok / len(rel) >= POLICY["aspect_pass_fraction"],
    }


def ink_recall(pages: list[dict]) -> dict:
    lay = pl.read_parquet(LAYOUTS, columns=["doc_name", "page_id", "bbox", "page_size"])
    boxes: dict[tuple[str, int], list] = {}
    for r in lay.iter_rows(named=True):
        boxes.setdefault((r["doc_name"], int(r["page_id"])), []).append((r["bbox"], r["page_size"]))
    eligible = [p for p in pages if (p["doc_id"], int(p["page_index"]) - 1) in boxes]
    sample = random.Random(POLICY["ink_seed"]).sample(eligible, POLICY["ink_pages"])
    normal, flipped = [], []
    for row in sample:
        with Image.open(row["page_image_path"]) as im:
            gray = np.asarray(im.convert("L").resize((448, 448), Image.BICUBIC), dtype=np.float32)
        ink = (1.0 - gray / 255.0) > POLICY["ink_threshold"]
        if ink.sum() < 50:
            continue
        mask_n = np.zeros_like(ink)
        mask_f = np.zeros_like(ink)
        for bbox, (w, h) in boxes[(row["doc_id"], int(row["page_index"]) - 1)]:
            x1, y1, x2, y2 = (int(round(v)) for v in (bbox[0] * 448 / w, bbox[1] * 448 / h,
                                                      bbox[2] * 448 / w, bbox[3] * 448 / h))
            mask_n[max(0, y1) : min(448, y2), max(0, x1) : min(448, x2)] = True
            mask_f[max(0, 448 - y2) : min(448, 448 - y1), max(0, x1) : min(448, x2)] = True
        normal.append(float((ink & mask_n).sum() / ink.sum()))
        flipped.append(float((ink & mask_f).sum() / ink.sum()))
    wins = sum(a > b for a, b in zip(normal, flipped, strict=True)) / len(normal)
    mean_n, mean_f = float(np.mean(normal)), float(np.mean(flipped))
    return {
        "pages": len(normal), "mean_ink_recall": mean_n, "mean_ink_recall_vflip_control": mean_f,
        "normal_beats_flip_fraction": wins,
        "passed": mean_n >= POLICY["ink_recall_min"] and mean_n - mean_f >= POLICY["ink_gap_min"]
        and wins >= POLICY["ink_win_fraction"],
    }


def signatures(pages: list[dict]) -> dict:
    sample = random.Random(2).sample(pages, POLICY["signature_pages"])
    bad = []
    for row in sample:
        payload = torch.load(CACHE / f"{row['page_id']}.pt", map_location="cpu", weights_only=True)
        if payload.get("model_name") != MODEL or payload.get("source_signature") != _source_signature(
            Path(row["page_image_path"]), MODEL
        ) or tuple(payload["embedding"].shape) != (PAGE_TOKENS, 128):
            bad.append(row["page_id"])
    return {"pages": len(sample), "mismatched": bad, "passed": not bad}


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"Refusing to overwrite {OUT}")
    start = time.monotonic()
    pages = pl.read_parquet(PAGES, columns=["doc_id", "page_id", "page_index", "page_image_path"]).to_dicts()
    report = {"policy": POLICY, "processor": processor_layout(), "embedding_probe": embedding_probe(pages)}
    report["page_frames"] = page_frames(pages)
    report["bbox_ink_recall"] = ink_recall(pages)
    report["cache_signatures"] = signatures(pages)
    checks = ("processor", "embedding_probe", "page_frames", "bbox_ink_recall", "cache_signatures")
    report["passed"] = all(report[name]["passed"] for name in checks)
    report["conclusion"] = (
        "cached [1031,128] pages are image-first; legacy [7:] slicing misaligns patches by 7"
        if report["processor"]["passed"] and report["embedding_probe"]["passed"]
        else "token layout not confirmed"
    )
    report["questions_or_gold_read"] = False
    report["elapsed_seconds"] = round(time.monotonic() - start, 1)
    text = json.dumps(report, ensure_ascii=False, indent=2)  # serialize fully before creating OUT
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("x", encoding="utf-8") as handle:
        handle.write(text)
    summary = {k: report[k]["passed"] for k in checks}
    print(json.dumps({"passed": report["passed"], **summary, "best": report["embedding_probe"]["best_hypothesis"],
                      "elapsed_seconds": report["elapsed_seconds"]}))


if __name__ == "__main__":
    main()
