"""Render route-v2 patch-label overlays for a fixed sample of source_train units.

Each PNG shows the page at the 448 model canvas: green = positive patch (centre inside
gold), yellow = ignored boundary patch, untinted = negative; red = gold box; blue = parsed
candidate boxes. Sample is fixed by rule (seed 42) before rendering, never by appearance.
Output: artifacts/route_v2_data/regions_v1/supervision_viz/ (never replaced).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import polars as pl
from PIL import Image, ImageDraw

from layoutpatch.layout.correspondence import clamp_bbox, patch_bbox, scale_bbox_to_model

REPO = Path(__file__).resolve().parents[1]
REGIONS = REPO / "artifacts/route_v2_data/regions_v1"
PAGES = REPO / "data/processed/mmdocir_evaluation/pages.parquet"
OUT = REGIONS / "supervision_viz"
SEED = 42


def pick(units: list[dict]) -> list[tuple[str, dict]]:
    ready = sorted((u for u in units if u["role"] == "source_train" and u["eval_ready"]),
                   key=lambda u: u["unit_id"])
    by_area = sorted(ready, key=lambda u: (min(u["gold_area_frac"]), u["unit_id"]))
    chosen = [("smallest_gold", by_area[0]), ("largest_gold", by_area[-1])]
    multi = [u for u in ready if len(u["gold_boxes"]) > 1]
    nopos = [u for u in ready if u["patch_pos"] == 0]
    unmatched = [u for u in ready if None in u["gold_exact_layout_id"]]
    rng = random.Random(SEED)
    for tag, pool in (("multi_box", multi), ("no_positive", nopos), ("unmatched_gold", unmatched)):
        if pool:
            chosen.append((tag, rng.choice(pool)))
    taken = {u["unit_id"] for _, u in chosen}
    rest = [u for u in ready if u["unit_id"] not in taken]
    chosen += [("random", u) for u in rng.sample(rest, 8 - len(chosen))]
    return chosen


def render(unit: dict, cands: list[dict], image_path: str, target: Path) -> None:
    size = unit["page_size"]
    with Image.open(image_path) as im:
        base = im.convert("RGBA").resize((448, 448), Image.BICUBIC)
    tint = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(tint)
    for idx in unit["patch_pos_idx"]:
        draw.rectangle(patch_bbox(idx), fill=(0, 200, 0, 90))
    for idx in unit["patch_ignore_idx"]:
        draw.rectangle(patch_bbox(idx), fill=(255, 210, 0, 110))
    canvas = Image.alpha_composite(base, tint)
    draw = ImageDraw.Draw(canvas)
    for c in cands:
        draw.rectangle(clamp_bbox(scale_bbox_to_model(c["bbox"], size)), outline=(40, 90, 255, 255), width=1)
    for g in unit["gold_boxes"]:
        draw.rectangle(clamp_bbox(scale_bbox_to_model(g, size)), outline=(230, 0, 0, 255), width=2)
    canvas.convert("RGB").save(target)


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"Refusing to overwrite {OUT}")
    units = pl.read_parquet(REGIONS / "units.parquet").to_dicts()
    cands = pl.read_parquet(REGIONS / "candidates.parquet").to_dicts()
    by_page: dict[tuple[str, int], list[dict]] = {}
    for c in cands:
        by_page.setdefault((c["doc_id"], c["page"]), []).append(c)
    pages = {(r["doc_id"], int(r["page_index"]) - 1): r["page_image_path"]
             for r in pl.read_parquet(PAGES, columns=["doc_id", "page_index", "page_image_path"]).to_dicts()}
    staging = OUT.with_name(OUT.name + ".partial")  # renamed to OUT only when complete
    staging.mkdir()
    index = []
    for n, (tag, u) in enumerate(pick(units)):
        name = f"{n:02d}_{tag}_{u['unit_id'].replace('#', '_')}.png"
        render(u, by_page.get((u["doc_id"], u["page"]), []), pages[(u["doc_id"], u["page"])],
               staging / name)
        index.append({"file": name, "tag": tag, "unit_id": u["unit_id"], "doc_id": u["doc_id"],
                      "page": u["page"], "gold_boxes": len(u["gold_boxes"]), "patch_pos": u["patch_pos"],
                      "patch_ignore": u["patch_ignore"], "candidates": u["candidate_count"],
                      "min_gold_area_frac": min(u["gold_area_frac"])})
    (staging / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    staging.rename(OUT)
    print(json.dumps(index, indent=1))


if __name__ == "__main__":
    main()
