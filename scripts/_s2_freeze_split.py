"""Freeze the four split id lists. Does not train and does not score test_eval.

seed=42. Documents are sorted by normalized name, shuffled, then cut by document ratio.
A train question whose positive and negative pages name two documents stays on one side;
if those names land on opposite sides, the whole question is dropped from both train pools.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 42
TRAIN_FIT_RATIO = 0.90
DEV_EVAL_RATIO = 0.30
KEPT = Path("experiments/s2_exclusion/kept_train_ids.jsonl")
EVAL_IDS = Path("experiments/eval313_doc_ids.txt")
EVAL_ANN = Path("data/raw/mmdocir_evaluation/MMDocIR_annotations.jsonl")
OUT = Path("experiments/s2_splits")


def norm_doc(name: str) -> str:
    stem = Path(name).stem
    if stem.lower().endswith(".pdf"):
        return stem[: -len(".pdf")]
    return stem


def shuffle_docs(names: set[str]) -> list[str]:
    ordered = sorted(names)
    random.Random(SEED).shuffle(ordered)
    return ordered


def cut(docs: list[str], ratio: float) -> tuple[set[str], set[str]]:
    n_left = int(len(docs) * ratio)
    return set(docs[:n_left]), set(docs[n_left:])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    kept = [json.loads(line) for line in KEPT.read_text(encoding="utf-8").splitlines() if line]
    train_docs = {doc for row in kept for doc in row["doc_names"]}
    fit_docs, dev_docs = cut(shuffle_docs(train_docs), TRAIN_FIT_RATIO)

    train_fit = []
    train_dev = []
    dropped = []
    for row in kept:
        sides = {doc: "fit" if doc in fit_docs else "dev" for doc in row["doc_names"]}
        if len(set(sides.values())) > 1:
            dropped.append({**row, "reason": "pos_neg_docs_split"})
            continue
        (train_fit if next(iter(sides.values())) == "fit" else train_dev).append(row)

    eval_docs = {line.strip() for line in EVAL_IDS.read_text(encoding="utf-8").splitlines() if line.strip()}
    dev_eval_docs, test_eval_docs = cut(shuffle_docs(eval_docs), DEV_EVAL_RATIO)
    dev_eval = []
    test_eval = []
    for line_index, line in enumerate(EVAL_ANN.read_text(encoding="utf-8").splitlines()):
        if not line:
            continue
        item = json.loads(line)
        doc = norm_doc(item["doc_name"])
        pool = "dev_eval" if doc in dev_eval_docs else "test_eval"
        for question_index, question in enumerate(item["questions"]):
            record = {
                "annotation_line": line_index,
                "question_index": question_index,
                "doc_name": doc,
                "has_layout_gold": bool(question.get("layout_mapping")),
            }
            (dev_eval if pool == "dev_eval" else test_eval).append(record)

    pools = {
        "train_fit": (train_fit, {doc for row in train_fit for doc in row["doc_names"]}),
        "train_dev": (train_dev, {doc for row in train_dev for doc in row["doc_names"]}),
        "dev_eval": (dev_eval, {row["doc_name"] for row in dev_eval}),
        "test_eval": (test_eval, {row["doc_name"] for row in test_eval}),
    }
    names = list(pools)
    intersections = {
        f"{left}__{right}": sorted(pools[left][1] & pools[right][1])
        for index, left in enumerate(names)
        for right in names[index + 1 :]
    }
    train_vs_eval = sorted((pools["train_fit"][1] | pools["train_dev"][1] | {doc for row in dropped for doc in row["doc_names"]}) & eval_docs)
    if any(intersections.values()) or train_vs_eval:
        raise SystemExit("split intersection is not empty")

    for name, (rows, _) in pools.items():
        (OUT / f"{name}_ids.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
    (OUT / "train_cross_doc_dropped.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in dropped),
        encoding="utf-8",
    )
    proof = {
        "seed": SEED,
        "shuffle": "sort normalized doc name, then random.Random(42).shuffle",
        "ratios": {"train_fit_docs": TRAIN_FIT_RATIO, "dev_eval_docs": DEV_EVAL_RATIO},
        "cut_counts": {
            "train_docs_before_drop": len(train_docs),
            "train_fit_docs_assigned": len(fit_docs),
            "train_dev_docs_assigned": len(dev_docs),
            "eval_docs": len(eval_docs),
            "dev_eval_docs_assigned": len(dev_eval_docs),
            "test_eval_docs_assigned": len(test_eval_docs),
        },
        "pools": {
            name: {
                "questions": len(rows),
                "docs": len(docs),
                "with_layout_gold": sum(row.get("has_layout_gold", False) for row in rows),
            }
            for name, (rows, docs) in pools.items()
        },
        "cross_doc_dropped_questions": len(dropped),
        "pairwise_doc_intersections": intersections,
        "train_pool_vs_eval313_docs": train_vs_eval,
        "test_eval_scored": False,
        "training_authorized": False,
    }
    (OUT / "split_proof.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(proof, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
