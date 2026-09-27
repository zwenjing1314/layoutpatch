"""S2 leakage exclusion lists. Exclusion only; does not authorize training.

Normalization (declared, both sides):
  doc: Path(name).stem, strip a trailing ".pdf" (case-insensitive)
  query: lowercase, delete spaces and tabs (U+0020 / U+0009) only
"""

from __future__ import annotations

import json
from pathlib import Path

EVAL_ANN = Path("data/raw/mmdocir_evaluation/MMDocIR_annotations.jsonl")
EVAL_IDS = Path("experiments/eval313_doc_ids.txt")
TRAIN_DIR = Path("data/raw/mmdocir_train/hf_hub/annotations_top1_negative")
OUT = Path("experiments/s2_exclusion")


def norm_doc(name: str) -> str:
    stem = Path(name).stem
    lowered = stem.lower()
    if lowered.endswith(".pdf"):
        return stem[: -len(".pdf")]
    return stem


def norm_query(text: str) -> str:
    return text.lower().replace(" ", "").replace("\t", "")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    eval_docs = {line.strip() for line in EVAL_IDS.read_text(encoding="utf-8").splitlines() if line.strip()}
    eval_questions: dict[str, list[str]] = {}
    n_eval_q = 0
    for line in EVAL_ANN.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        item = json.loads(line)
        norm_doc(item["doc_name"])
        for question in item["questions"]:
            n_eval_q += 1
            key = norm_query(question["Q"])
            eval_questions.setdefault(key, []).append(question["Q"])

    overlap_docs: set[str] = set()
    overlap_queries: dict[str, dict] = {}
    train_rows: list[dict] = []
    for path in sorted(TRAIN_DIR.glob("*_train.jsonl")):
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line:
                continue
            row = json.loads(line)
            docs = sorted(
                {
                    norm_doc(passage["doc_name"])
                    for passage in row["positive_passages"] + row["negative_passages"]
                }
            )
            key = norm_query(row["query"])
            record = {
                "domain": path.stem.replace("_train", ""),
                "line_index": index,
                "query_id": row.get("query_id", ""),
                "doc_names": docs,
                "normalized_query": key,
            }
            train_rows.append(record)
            hit_docs = sorted(set(docs) & eval_docs)
            if hit_docs:
                overlap_docs.update(hit_docs)
            if key in eval_questions:
                bucket = overlap_queries.setdefault(
                    key,
                    {"normalized": key, "eval_examples": eval_questions[key][:3], "train": []},
                )
                bucket["train"].append({**record, "query": row["query"]})

    (OUT / "overlap_doc_names.txt").write_text(
        "\n".join(sorted(overlap_docs)) + "\n",
        encoding="utf-8",
    )
    (OUT / "overlap_queries.json").write_text(
        json.dumps(list(overlap_queries.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUT / "train_question_index.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in train_rows),
        encoding="utf-8",
    )
    summary = {
        "norm_doc": "Path.stem, strip one trailing .pdf case-insensitive",
        "norm_query": "lowercase; delete U+0020 and U+0009 only",
        "eval_docs": len(eval_docs),
        "eval_questions": n_eval_q,
        "eval_questions_unique_normalized": len(eval_questions),
        "train_questions": len(train_rows),
        "train_docs": len({doc for row in train_rows for doc in row["doc_names"]}),
        "overlap_docs": len(overlap_docs),
        "overlap_queries": len(overlap_queries),
    }
    (OUT / "text_overlap_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
