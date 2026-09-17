"""Phase 1B stratification + cases + gate support (PAPER_SPEC 7.3, batch 4, EXP-005).

What (beginner):
- One script recomputes everything from frozen inputs, so numbers match by construction.
- Inputs: EXP-001 Top-5 predictions + nodes + region_labels + queries question_type.
- Outputs (all under artifacts/diagnosis/mmdocir_evaluation/):
    stratification.json  18-row split table (qtype/area/density x A/B/C/D)
    cases.json           10 success + 10 failure + 10 middle overlays + freeze meta
    crosstab.json        matched/unmapped_only x A/B/C/D (per-query) + B split
    addressability.json  addressable-B shares vs 10% gate line (two denominators)
    oracle.json          region-hit ceiling given gold page (oracle best-IoU)
    strat_area_hist.png / strat_cov_hist.png (+ *_hist.json bin counts)
    overlays_cases/*.jpg        original 20 extreme overlays (A_/B_ prefix, gold=yellow thick)
    overlays_cases_mid/*.jpg    10 middle-state overlays (M_ prefix, same drawing code)

Frozen definitions (written into every JSON under "meta"):
- k=5 (Top-K), iou_threshold=0.5.
- area_ratio (binning key) = MEAN over query's gold rows of bbox_area/page_area.
  area_best_gold_ratio is stored per case for reference only, NOT used for binning.
- ocr_coverage (binning key) = MEAN over query's gold rows of
  sum(node bboxes on that gold page)/page_area.
- tertile cut points are computed on the 1658 per-query values and frozen in JSON.
- topk_best_iou = max IoU over candidates on gold pages INSIDE Top-K (region signal).
- oracle_best_iou = max IoU over candidates on ALL gold pages IGNORING Top-K (ceiling).
- class A/B/C/D uses Top-K: region_hit requires page_hit by construction, so C=0
  is definitional (no discovery claim allowed).
- matched = query has >=1 matched gold row (1598 queries, incl. 2 both-matched-and-unmapped).
  unmapped_only = query has ONLY unmapped gold rows (60 queries). 1598+60=1658.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path

import polars as pl

from layoutpatch.evaluation.audit_overlays import _page_image_for, draw_overlay
from layoutpatch.evaluation.region_metrics import bbox_iou
from layoutpatch.paths import artifacts_dir, data_root

GATE_LINE = 0.10


def parse_qtype(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    text = value.strip()
    if text.startswith("["):
        try:
            items = ast.literal_eval(text)
            if isinstance(items, list):
                return [str(x).strip() for x in items if str(x).strip()]
        except Exception:
            return []
        return []
    return [text] if text else []


def norm_qtype(tags: list[str]) -> str:
    if not tags:
        return "unknown"
    if len(tags) == 1:
        return tags[0]
    return "mixed"


def bbox_area(bbox: list[float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--iou", type=float, default=0.5)
    args = parser.parse_args()

    processed = data_root() / "processed" / "mmdocir_evaluation"
    run_dir = Path("runs/retrieval/mmdocir_colpali/20260916_134144")
    out_dir = artifacts_dir() / "diagnosis" / "mmdocir_evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)

    queries = {r["query_id"]: r for r in pl.read_parquet(processed / "queries.parquet").to_dicts()}
    labels = pl.read_parquet(processed / "region_labels.parquet").to_dicts()
    gold_by_query: dict[str, list[dict]] = {}
    for row in labels:
        gold_by_query.setdefault(row["query_id"], []).append(row)
    matched_q = {r["query_id"] for r in labels if r["source"] == "matched"}

    nodes_rows = pl.read_parquet(processed / "nodes.parquet").to_dicts()
    nodes_by_page: dict[str, list[dict]] = {}
    for row in nodes_rows:
        bbox = row["bbox"]
        if isinstance(bbox, str):
            try:
                bbox = json.loads(bbox)
            except json.JSONDecodeError:
                continue
        if isinstance(bbox, list) and len(bbox) == 4:
            nodes_by_page.setdefault(row["page_id"], []).append(
                {"node_id": row["node_id"], "node_type": row["node_type"], "bbox": [float(v) for v in bbox]}
            )

    hits = pl.read_parquet(run_dir / "predictions.parquet").to_dicts()
    top_pages: dict[str, set[str]] = {}
    for hit in hits:
        if hit["rank"] <= args.k:
            top_pages.setdefault(hit["query_id"], set()).add(hit["page_id"])

    per_query: dict[str, dict] = {}
    for query_id, golds in gold_by_query.items():
        pages = top_pages.get(query_id, set())
        gold_pages = {g["page_id"] for g in golds}
        page_hit = bool(pages & gold_pages)
        topk_best = 0.0
        oracle_best = 0.0
        best_gold = None
        n_cands_best_page = 0
        for gold in golds:
            gb = [float(v) for v in gold["bbox"]]
            cands = nodes_by_page.get(gold["page_id"], [])
            for cand in cands:
                iou = bbox_iou(cand["bbox"], gb)
                oracle_best = max(oracle_best, iou)
                if gold["page_id"] in pages and iou > topk_best:
                    topk_best = iou
                    best_gold = gold
                    n_cands_best_page = len(cands)
        region_hit = topk_best >= args.iou
        if page_hit and region_hit:
            cls = "A"
        elif page_hit and not region_hit:
            cls = "B"
        elif not page_hit and region_hit:
            cls = "C"
        else:
            cls = "D"

        qrow = queries.get(query_id, {})
        qtype = norm_qtype(parse_qtype(qrow.get("question_type", "")))
        areas = []
        for gold in golds:
            gb = [float(v) for v in gold["bbox"]]
            ps = gold.get("page_size") or [1.0, 1.0]
            areas.append(bbox_area(gb) / max(1.0, float(ps[0]) * float(ps[1])))
        area_mean = sum(areas) / max(1, len(areas))
        area_best = 0.0
        if best_gold is not None:
            gb = [float(v) for v in best_gold["bbox"]]
            ps = best_gold.get("page_size") or [1.0, 1.0]
            area_best = bbox_area(gb) / max(1.0, float(ps[0]) * float(ps[1]))

        cover_vals = []
        for gold in golds:
            cands = nodes_by_page.get(gold["page_id"], [])
            ps = gold.get("page_size") or [1.0, 1.0]
            page_area = max(1.0, float(ps[0]) * float(ps[1]))
            cover_vals.append(sum(bbox_area(c["bbox"]) for c in cands) / page_area)
        coverage = sum(cover_vals) / max(1, len(cover_vals))

        per_query[query_id] = {
            "class": cls,
            "qtype": qtype,
            "area_ratio": area_mean,
            "area_best_gold_ratio": area_best,
            "ocr_coverage": coverage,
            "topk_best_iou": topk_best,
            "oracle_best_iou": oracle_best,
            "matched": query_id in matched_q,
            "page_hit": page_hit,
            "gold": best_gold or golds[0],
            "n_cands_best_page": n_cands_best_page,
        }

    area_vals = sorted(v["area_ratio"] for v in per_query.values())
    cov_vals = sorted(v["ocr_coverage"] for v in per_query.values())
    n = len(area_vals)
    area_cuts = [area_vals[n // 3], area_vals[2 * n // 3]]
    cov_cuts = [cov_vals[n // 3], cov_vals[2 * n // 3]]

    def area_bin(v: float) -> str:
        if v <= area_cuts[0]:
            return "small"
        if v <= area_cuts[1]:
            return "medium"
        return "large"

    def dens_bin(v: float) -> str:
        if v <= cov_cuts[0]:
            return "sparse"
        if v <= cov_cuts[1]:
            return "medium"
        return "dense"

    for info in per_query.values():
        info["area_bin"] = area_bin(info["area_ratio"])
        info["density_bin"] = dens_bin(info["ocr_coverage"])

    # ---- stratification table ----
    strata: dict[str, Counter] = {}
    for info in per_query.values():
        for key in (f"qtype={info['qtype']}", f"area={info['area_bin']}", f"density={info['density_bin']}"):
            strata.setdefault(key, Counter())[info["class"]] += 1
    strat_rows = []
    for key in sorted(strata):
        c = strata[key]
        total = sum(c.values())
        page_hits = c["A"] + c["B"]
        region_hits = c["A"] + c["C"]
        strat_rows.append(
            {
                "stratum": key,
                "n": total,
                "A": c["A"],
                "B": c["B"],
                "C": c["C"],
                "D": c["D"],
                "page_hit_rate": round(page_hits / total, 4) if total else 0.0,
                "region_hit_rate": round(region_hits / total, 4) if total else 0.0,
                "b_share_of_page_hits": round(c["B"] / page_hits, 4) if page_hits else 0.0,
            }
        )
    (out_dir / "stratification.json").write_text(
        json.dumps(
            {
                "meta": {
                    "k": args.k,
                    "iou_threshold": args.iou,
                    "area_definition": "MEAN over query gold rows of bbox_area/page_area (binning key); area_best_gold_ratio stored per case for reference only",
                    "coverage_definition": "MEAN over query gold rows of sum(node bboxes on gold page)/page_area",
                    "area_tertiles": area_cuts,
                    "coverage_tertiles": cov_cuts,
                    "run_dir": str(run_dir),
                },
                "rows": strat_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ---- task 1: matched/unmapped_only x A/B/C/D + addressability ----
    ctab = {"matched": Counter(), "unmapped_only": Counter()}
    for _qid, info in per_query.items():
        key = "matched" if info["matched"] else "unmapped_only"
        ctab[key][info["class"]] += 1
    b_qids = [qid for qid, v in per_query.items() if v["class"] == "B"]
    b_unmapped = sum(1 for q in b_qids if not per_query[q]["matched"])
    b_matched = len(b_qids) - b_unmapped
    page_hits_all = sum(1 for v in per_query.values() if v["page_hit"])
    matched_page_hits = sum(1 for v in per_query.values() if v["page_hit"] and v["matched"])
    n_layout_gold = sum(1 for v in per_query.values() if v["matched"])
    share_page = b_matched / page_hits_all if page_hits_all else 0.0
    share_gold = b_matched / n_layout_gold if n_layout_gold else 0.0
    (out_dir / "crosstab.json").write_text(
        json.dumps(
            {
                "meta": {"k": args.k, "iou_threshold": args.iou, "matched_def": "query has >=1 matched gold row (1598 incl. 2 both); unmapped_only = only unmapped rows (60)"},
                "rows": [
                    {"source": "matched", "queries": sum(ctab["matched"].values()), "A": ctab["matched"]["A"], "B": ctab["matched"]["B"], "C": ctab["matched"]["C"], "D": ctab["matched"]["D"]},
                    {"source": "unmapped_only", "queries": sum(ctab["unmapped_only"].values()), "A": ctab["unmapped_only"]["A"], "B": ctab["unmapped_only"]["B"], "C": ctab["unmapped_only"]["C"], "D": ctab["unmapped_only"]["D"]},
                ],
                "b_total": len(b_qids),
                "b_unmapped_only": b_unmapped,
                "b_matched": b_matched,
                "b_unmapped_share_of_b": round(b_unmapped / len(b_qids), 4) if b_qids else 0.0,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (out_dir / "addressability.json").write_text(
        json.dumps(
            {
                "meta": {"k": args.k, "iou_threshold": args.iou, "gate_line": GATE_LINE, "addressable_B_def": "B queries with matched source (gold box exists in nodes)"},
                "b_total": len(b_qids),
                "b_unmapped_only": b_unmapped,
                "b_addressable_matched": b_matched,
                "denominator_page_hits_1390": page_hits_all,
                "denominator_layout_gold_1598": n_layout_gold,
                "denominator_matched_page_hits": matched_page_hits,
                "b_share_addressable_of_page_hits": round(share_page, 4),
                "b_share_addressable_of_layout_gold": round(share_gold, 4),
                "gap_to_gate_page_hits_pp": round((GATE_LINE - share_page) * 100, 2),
                "gap_to_gate_layout_gold_pp": round((GATE_LINE - share_gold) * 100, 2),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ---- task 2: oracle ceiling ----
    oracle_hit_all = sum(1 for v in per_query.values() if v["oracle_best_iou"] >= args.iou)
    oracle_hit_page = sum(1 for v in per_query.values() if v["page_hit"] and v["oracle_best_iou"] >= args.iou)
    oracle_miss_page = page_hits_all - oracle_hit_page
    (out_dir / "oracle.json").write_text(
        json.dumps(
            {
                "meta": {"k": args.k, "iou_threshold": args.iou, "oracle_def": "max IoU over ALL gold-page candidates, ignoring Top-K page constraint; C_topk=0 is definitional because topk region_hit requires page_hit"},
                "all_queries": {"n": len(per_query), "oracle_hit": oracle_hit_all, "oracle_hit_rate": round(oracle_hit_all / len(per_query), 4)},
                "page_hit_queries": {"n": page_hits_all, "oracle_hit": oracle_hit_page, "oracle_miss_box_gap": oracle_miss_page, "oracle_hit_rate": round(oracle_hit_page / page_hits_all, 4) if page_hits_all else 0.0},
                "c_topk_definitional": 0,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ---- histograms (area + coverage, 20 bins, tertile lines, B overlay) ----
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    area_all = [v["area_ratio"] for v in per_query.values()]
    area_b = [per_query[q]["area_ratio"] for q in b_qids]
    cov_all = [v["ocr_coverage"] for v in per_query.values()]
    cov_b = [per_query[q]["ocr_coverage"] for q in b_qids]

    def save_hist(values_all: list[float], values_b: list[str], cuts: list[float], title: str, xlabel: str, png: Path, js: Path) -> None:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.hist(values_all, bins=20, alpha=0.6, label="all 1658")
        ax.hist(values_b, bins=20, alpha=0.8, label="B 45")
        for c in cuts:
            ax.axvline(c, linestyle="--")
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("queries")
        ax.legend()
        fig.tight_layout()
        fig.savefig(png, dpi=120)
        plt.close(fig)
        counts, edges = __import__("numpy").histogram(values_all, bins=20)
        bcounts, _ = __import__("numpy").histogram(values_b, bins=list(edges))
        js.write_text(json.dumps({"cuts": cuts, "edges": [round(float(e), 6) for e in edges], "counts_all": [int(x) for x in counts], "counts_b": [int(x) for x in bcounts]}, ensure_ascii=False, indent=2), encoding="utf-8")

    save_hist(area_all, area_b, area_cuts, "gold area ratio (mean per query): all vs B", "area_ratio", out_dir / "strat_area_hist.png", out_dir / "strat_area_hist.json")
    save_hist(cov_all, cov_b, cov_cuts, "gold-page node coverage (mean per query): all vs B", "ocr_coverage", out_dir / "strat_cov_hist.png", out_dir / "strat_cov_hist.json")

    # ---- cases: keep extreme 20 + 10 middle ----
    a_sorted = sorted([q for q, v in per_query.items() if v["class"] == "A"], key=lambda q: per_query[q]["topk_best_iou"], reverse=True)
    b_sorted = sorted(b_qids, key=lambda q: per_query[q]["topk_best_iou"])
    success = a_sorted[:10]
    failure = b_sorted[:10]
    fail_set = set(failure)
    pool = [q for q in b_qids if q not in fail_set and (0.3 <= per_query[q]["topk_best_iou"] < 0.5 or (per_query[q]["area_bin"] == "large" and per_query[q]["n_cands_best_page"] >= 10))]
    # diversity-greedy fill to 10
    middle: list[str] = []
    seen_keys: set[str] = set()
    for q in sorted(pool, key=lambda q: per_query[q]["topk_best_iou"]):
        key = (per_query[q]["qtype"], per_query[q]["area_bin"], per_query[q]["density_bin"])
        if key not in seen_keys or len(pool) <= 10:
            middle.append(q)
            seen_keys.add(key)
        if len(middle) == 10:
            break
    if len(middle) < 10:
        for q in b_sorted:
            if q not in fail_set and q not in middle:
                middle.append(q)
            if len(middle) == 10:
                break

    images_root = data_root() / "interim" / "mmdocir_evaluation" / "page_images"
    case_dir = out_dir / "overlays_cases"
    mid_dir = out_dir / "overlays_cases_mid"
    entries = []
    missing: list[str] = []

    def render(qid: str, prefix: str, folder: Path) -> None:
        info = per_query[qid]
        gold = info["gold"]
        page_id = gold["page_id"]
        image_path = _page_image_for(page_id, images_root)
        if image_path is None:
            missing.append(page_id)
            return
        rows = list(nodes_by_page.get(page_id, []))
        rows.append({"node_id": "GOLD", "node_type": "gold", "bbox": [float(v) for v in gold["bbox"]]})
        out = folder / f"{prefix}_{qid}_{page_id}.jpg"
        draw_overlay(image_path, rows, out)
        entries.append(
            {
                "query_id": qid,
                "class": info["class"],
                "tier": prefix,
                "page_id": page_id,
                "topk_best_iou": round(info["topk_best_iou"], 4),
                "oracle_best_iou": round(info["oracle_best_iou"], 4),
                "qtype": info["qtype"],
                "area_bin": info["area_bin"],
                "density_bin": info["density_bin"],
                "n_cands_best_page": info["n_cands_best_page"],
                "matched": info["matched"],
                "overlay": str(out),
            }
        )

    for q in success:
        render(q, "A", case_dir)
    for q in failure:
        render(q, "B", case_dir)
    for q in middle:
        render(q, "M", mid_dir)

    (out_dir / "cases.json").write_text(
        json.dumps(
            {
                "meta": {
                    "k": args.k,
                    "iou_threshold": args.iou,
                    "area_definition": "MEAN over gold rows for binning; area_best_gold_ratio stored per case for reference",
                    "area_tertiles": area_cuts,
                    "coverage_tertiles": cov_cuts,
                    "success_def": "A with highest topk_best_iou (10)",
                    "failure_def": "B with lowest topk_best_iou (10)",
                    "middle_def": "B with IoU in [0.3,0.5) or large-box multi-candidate miss, diversity-greedy over (qtype,area,density) (10)",
                    "judge_protocol": "yellow thick box=gold; check whether colored layout boxes enclose real text/table, ignore grid lines; top/bottom small print or page numbers unenclosed = official sparsity",
                },
                "success": success,
                "failure": failure,
                "middle": middle,
                "entries": entries,
                "missing": missing,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"strata={len(strat_rows)} success={len(success)} failure={len(failure)} middle={len(middle)} missing={len(missing)}")
    print(f"out={out_dir}")


if __name__ == "__main__":
    main()
