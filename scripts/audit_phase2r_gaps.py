"""Read-only Phase 2-R gap audit. Does not train, encode, or score test_eval.

Resolves the 391/401 denominator, the mixed-train count gap, and per-question
Area@1/Area@5 for the three accepted heads. Writes only experiments/s2_splits/.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import polars as pl
import torch
from torch.nn.functional import normalize

from layoutpatch.evaluation.region_metrics import recall_layout
from layoutpatch.io import _unjsonify
from layoutpatch.layout.correspondence import clamp_bbox, scale_bbox_to_model
from layoutpatch.retrieval.propagation import patch_scores_from_vectors
from layoutpatch.retrieval.region_pooling import coverage_region_scores
from layoutpatch.retrieval.rerank.box_ranker import BoxRanker, area_at_k, build_features, rank_all
from scripts.train_phase2r_arxivqa_dude import (
    DEV,
    DEV_EVAL,
    EVAL_ANN,
    EVAL_PATCH,
    FIT,
    PROCESSED,
    REGION_401,
    dev_eval_rows,
    load_pairs,
    within_doc_top5,
)

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "experiments/s2_splits"
HEADS = {
    "EXP-009": REPO / "artifacts/phase2r/arxivqa/ranker.pt",
    "EXP-010": REPO / "artifacts/phase2r/dude/ranker.pt",
    "EXP-011": REPO / "artifacts/phase2r/arxivqa_dude/ranker.pt",
}
RUNS = {
    "EXP-009": REPO / "runs/retrieval/mmdocir_phase2r_arxivqa/20260928_122544/metrics.json",
    "EXP-010": REPO / "runs/retrieval/mmdocir_phase2r_dude/20260928_142234/metrics.json",
    "EXP-011": REPO / "runs/retrieval/mmdocir_phase2r_arxivqa_dude/20260928_151348/metrics.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def query_ids() -> dict[tuple[int, int], str]:
    """Same index rule as region_labels.py: one id per annotation question."""
    ids = {}
    index = 0
    for line_index, line in enumerate(EVAL_ANN.open(encoding="utf-8")):
        item = json.loads(line)
        for question_index, _question in enumerate(item.get("questions", [])):
            ids[(line_index, question_index)] = f"mmdocir_{index:05d}"
            index += 1
    return ids


def read_rows(name: str) -> list[dict]:
    frame = pl.read_parquet(PROCESSED / name)
    return [{key: _unjsonify(key, value) for key, value in row.items()} for row in frame.to_dicts()]


def denominator() -> dict:
    """Recount matched gold. The frozen rule is the rule, not the old count 391."""
    ids = query_ids()
    dev = [json.loads(line) for line in DEV_EVAL.open(encoding="utf-8") if line.strip()]
    listed = [line.strip() for line in REGION_401.read_text(encoding="utf-8").splitlines() if line.strip()]
    labels: dict[str, set[str]] = {}
    for row in read_rows("region_labels.parquet"):
        labels.setdefault(row["query_id"], set()).add(row["source"])
    matched, unmapped_only, no_layout = [], [], []
    for row in dev:
        qid = ids[(int(row["annotation_line"]), int(row["question_index"]))]
        sources = labels.get(qid, set())
        if "matched" in sources:
            matched.append(qid)
        elif sources:
            unmapped_only.append(qid)
        else:
            no_layout.append(qid)
    extra = sorted(set(listed) - set(matched))
    missing = sorted(set(matched) - set(listed))
    return {
        "dev_eval_n": len(dev),
        "matched_now": len(matched),
        "unmapped_only_now": len(unmapped_only),
        "no_layout_now": len(no_layout),
        "listed_401": len(listed),
        "listed_equals_matched_now": set(listed) == set(matched) and not extra and not missing,
        "extra_in_list": extra,
        "missing_from_list": missing,
        "historical_391": "EXP-005 recount of an older region_labels.parquet; not a second rule",
        "accepted_denominator": 401,
        "rule": "a question enters the region denominator iff it has at least one matched gold",
    }


def count_gap() -> dict:
    """Explain 11575 versus 9241+2312 without deleting or re-encoding anything."""
    rows = {}
    for pool, name in ((FIT, "train_fit"), (DEV, "train_dev")):
        selected, _pages, missing = load_pairs(pool)
        by_domain: dict[str, int] = {}
        for row in selected:
            by_domain[row["domain"]] = by_domain.get(row["domain"], 0) + 1
        rows[name] = {
            "kept": len(selected),
            "by_domain": by_domain,
            "missing_page_refs": len(missing),
            "missing_pages": missing,
        }
    return {
        "single_head_sum_fit": 9241 + 2312,
        "mixed_fit": rows["train_fit"]["kept"],
        "fit_gap": rows["train_fit"]["kept"] - (9241 + 2312),
        "single_head_sum_dev": 1592 + 292,
        "mixed_dev": rows["train_dev"]["kept"],
        "dev_gap": rows["train_dev"]["kept"] - (1592 + 292),
        "pools": rows,
        "note": "9241 and 2312 are post-box-filter counts. Mixed 11575 keeps the 22 questions those filters dropped, because their pages were already encoded for other questions. Same for early-stop 1891 versus 1592+292.",
    }


def load_ranker(path: Path) -> BoxRanker:
    ranker = BoxRanker()
    saved = torch.load(path, map_location="cpu", weights_only=False)
    if isinstance(saved, dict) and set(saved) == {"w", "b"}:
        ranker.linear.weight.data.copy_(saved["w"])
        ranker.linear.bias.data.copy_(saved["b"])
    else:
        ranker.load_state_dict(saved)
    ranker.eval()
    return ranker


def per_question() -> None:
    """Score the three frozen heads on the same 401 questions. No weight update."""
    rows = dev_eval_rows()
    by_id = {row["query_id"]: row for row in read_rows("queries.parquet")}
    nodes: dict[str, list] = {}
    for node in read_rows("nodes.parquet"):
        nodes.setdefault(node["page_id"], []).append(node)
    gold: dict[str, list] = {}
    for label in read_rows("region_labels.parquet"):
        if label["source"] == "matched":
            gold.setdefault(label["query_id"], []).append(label)
    region_ids = [line.strip() for line in REGION_401.read_text(encoding="utf-8").splitlines() if line.strip()]
    top5 = within_doc_top5(rows)
    vectors = torch.load(
        REPO / "artifacts/phase2r/arxivqa_dude/dev_eval_queries.pt",
        map_location="cpu",
        weights_only=False,
    )
    rankers = {name: load_ranker(path) for name, path in HEADS.items()}
    totals = {name: {"a1": 0.0, "a5": 0.0} for name in HEADS}
    base = {"a1": 0.0, "a5": 0.0}
    page_hit = 0
    seen = []
    lines = []
    with torch.no_grad():
        for row, vec in zip(rows, vectors, strict=True):
            query = by_id[row["query_id"]]
            evidence = set(query["evidence_page_ids"])
            hit = bool(top5.get(query["query_id"], set()) & evidence)
            page_hit += int(hit)
            if query["query_id"] not in set(region_ids):
                continue
            golds = gold[query["query_id"]]
            page_id = golds[0]["page_id"]
            cands = nodes.get(page_id, [])
            page_size = [float(v) for v in golds[0]["page_size"]]
            payload = torch.load(EVAL_PATCH / f"{page_id}.pt", map_location="cpu", weights_only=False)
            emb = payload["embedding"] if isinstance(payload, dict) else payload
            boxes = [
                {
                    "bbox": [float(v) for v in cand["bbox"]],
                    "bbox_model": clamp_bbox(scale_bbox_to_model(cand["bbox"], page_size)),
                    "text_vec": None,
                }
                for cand in cands
            ]
            scores = patch_scores_from_vectors(vec, normalize(emb.float(), dim=-1))
            feats = build_features(scores, boxes, page_size[0], page_size[1], None)
            layout = [(i, int(page_id.rsplit("_p", 1)[1]), *cand["bbox"]) for i, cand in enumerate(cands)]
            mapping = [{"page": int(g["page_id"].rsplit("_p", 1)[1]), "bbox": g["bbox"]} for g in golds]
            base_scores = [0.0 if s == float("-inf") else s for s in coverage_region_scores(scores, boxes, "iou_mass")]
            b1 = area_at_k(layout, mapping, base_scores, 1)
            b5 = area_at_k(layout, mapping, base_scores, 5)
            base["a1"] += b1
            base["a5"] += b5
            item = {"query_id": query["query_id"], "page_hit": hit, "base1": b1, "base5": b5}
            for name, ranker in rankers.items():
                order = rank_all(ranker, feats)
                a1 = float(recall_layout(order[:1], layout, mapping))
                a5 = float(recall_layout(order[:5], layout, mapping))
                item[f"{name}_area1"] = a1
                item[f"{name}_area5"] = a5
                totals[name]["a1"] += a1
                totals[name]["a5"] += a5
            seen.append(query["query_id"])
            lines.append(json.dumps(item, ensure_ascii=False))
    if set(seen) != set(region_ids) or len(seen) != 401:
        raise RuntimeError(f"scored {len(seen)} != 401")
    (OUT / "phase2r_per_question.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = {
        "n": 401,
        "page_hits": page_hit,
        "page_n": 415,
        "base1": base["a1"] / 401,
        "base5": base["a5"] / 401,
        "heads": {name: {"area1": v["a1"] / 401, "area5": v["a5"] / 401} for name, v in totals.items()},
        "metrics_match": {},
        "weight_sha256": {name: sha256(path) for name, path in HEADS.items()},
        "text_feature": "query_vec is None, so feature 5 is 0 for every box",
        "test_eval": "not_read",
    }
    for name, path in RUNS.items():
        metrics = json.loads(path.read_text(encoding="utf-8"))
        summary["metrics_match"][name] = {
            "area1": abs(summary["heads"][name]["area1"] - metrics["area1"]) < 1e-9,
            "area5": abs(summary["heads"][name]["area5"] - metrics["area5"]) < 1e-9,
        }
    (OUT / "phase2r_per_question_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    proof = {"denominator": denominator(), "count_gap": count_gap()}
    (OUT / "phase2r_gap_proof.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    per_question()
    print(json.dumps({"wrote": "phase2r_gap_proof.json", "scored": 401}, ensure_ascii=False))


if __name__ == "__main__":
    main()


