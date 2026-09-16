"""Render coordinate-audit overlay figures (M4, one-shot script, not reused logic).

说明（新手向）：`docs/PAPER_SPEC.md` 第 6 节第二步——agent 自动生成 ≥20 页叠图，
人只回答"表格线/栏边界是否对齐"。本脚本从 region_labels 里按页抽样（优先框多、
框大的页，即疑似表格页/大图页），在页图上叠两层：32×32 patch 网格（红线）+
gold 框（黄框），存到 `runs/audit/overlays/`。几何换算复用
`layout/correspondence.py`，本脚本只做画图，不写可复用逻辑。
"""

from __future__ import annotations

from pathlib import Path

import typer
from PIL import Image, ImageDraw

from layoutpatch.evaluation.region_labels import read_region_labels
from layoutpatch.io import read_processed_dataset
from layoutpatch.layout.correspondence import GRID, MODEL_SIZE
from layoutpatch.paths import data_root

app = typer.Typer(help="Render coordinate-audit overlay figures.")


@app.command()
def main(
    processed: str = str(data_root() / "processed" / "mmdocir_evaluation"),
    out_dir: str = "runs/audit/overlays",
    num_pages: int = 24,
) -> None:
    processed_dir = Path(processed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _, pages, _, _ = read_processed_dataset(processed_dir)
    page_by_id = {page.page_id: page for page in pages}
    labels = read_region_labels(processed_dir)
    by_page: dict[str, list] = {}
    for label in labels:
        by_page.setdefault(label.page_id, []).append(label)
    ranked = sorted(
        by_page.items(),
        key=lambda item: (len(item[1]), sum(
            max(0.0, lab.bbox[2] - lab.bbox[0]) * max(0.0, lab.bbox[3] - lab.bbox[1])
            for lab in item[1]
        )),
        reverse=True,
    )[:num_pages]
    written = 0
    for page_id, page_labels in ranked:
        page = page_by_id.get(page_id)
        if page is None or not page.page_image_path:
            continue
        image_path = Path(page.page_image_path)
        if not image_path.exists():
            continue
        with Image.open(image_path).convert("RGB") as image:
            width, height = image.size
            canvas = image.resize((MODEL_SIZE, MODEL_SIZE))
            draw = ImageDraw.Draw(canvas)
            step = MODEL_SIZE // GRID
            for index in range(1, GRID):
                draw.line([(index * step, 0), (index * step, MODEL_SIZE)], fill=(255, 0, 0), width=1)
                draw.line([(0, index * step), (MODEL_SIZE, index * step)], fill=(255, 0, 0), width=1)
            for lab in page_labels:
                x1, y1, x2, y2 = lab.bbox
                draw.rectangle(
                    [
                        x1 * MODEL_SIZE / width,
                        y1 * MODEL_SIZE / height,
                        x2 * MODEL_SIZE / width,
                        y2 * MODEL_SIZE / height,
                    ],
                    outline=(255, 255, 0),
                    width=2,
                )
            canvas.save(out / f"{page_id}.png")
            written += 1
    typer.echo(f"wrote {written} overlays to {out}")


if __name__ == "__main__":
    app()
