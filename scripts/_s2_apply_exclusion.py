"""Apply the declared S2 exclusion union and prove the remainder has zero overlap.

Union = all train questions of the 24 overlap docs
      + the 38 overlap questions
      + md5 page-image hits (none).
Does not filter by T_oracle and does not build training labels.
"""

from __future__ import annotations

import json
from pathlib import Path

EXCL = Path("experiments/s2_exclusion")


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    overlap_docs = {
        line.strip()
        for line in (EXCL / "overlap_doc_names.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    overlap_queries = json.loads((EXCL / "overlap_queries.json").read_text(encoding="utf-8"))
    query_keys = {item["normalized"] for item in overlap_queries}
    md5 = json.loads((EXCL / "md5_reuse.json").read_text(encoding="utf-8"))
    if md5["reuse_count"] != 0:
        raise SystemExit(f"md5 reuse {md5['reuse_count']} > 0; stop before writing kept ids")

    rows = load_jsonl(EXCL / "train_question_index.jsonl")
    before_docs = {doc for row in rows for doc in row["doc_names"]}
    excluded = []
    kept = []
    for row in rows:
        reasons = []
        hit_docs = sorted(set(row["doc_names"]) & overlap_docs)
        if hit_docs:
            reasons.append("overlap_doc")
        if norm_of(row) in query_keys:
            reasons.append("overlap_query")
        if reasons:
            excluded.append({**row, "reasons": reasons, "hit_docs": hit_docs})
        else:
            kept.append(row)

    after_docs = {doc for row in kept for doc in row["doc_names"]}
    after_query_keys = {norm_of(row) for row in kept}
    doc_intersection = sorted(after_docs & overlap_docs)
    query_intersection = sorted(after_query_keys & query_keys)
    if doc_intersection or query_intersection:
        raise SystemExit(
            f"exclusion failed docs={len(doc_intersection)} queries={len(query_intersection)}"
        )

    (EXCL / "excluded_train_ids.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in excluded),
        encoding="utf-8",
    )
    (EXCL / "kept_train_ids.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in kept),
        encoding="utf-8",
    )
    report = {
        "union": "24 overlap docs (all their train questions) + 38 overlap questions + md5 hits",
        "md5_hits_added": 0,
        "before_questions": len(rows),
        "before_docs": len(before_docs),
        "excluded_questions": len(excluded),
        "excluded_by_doc": sum("overlap_doc" in row["reasons"] for row in excluded),
        "excluded_by_query": sum("overlap_query" in row["reasons"] for row in excluded),
        "excluded_by_both": sum(len(row["reasons"]) == 2 for row in excluded),
        "after_questions": len(kept),
        "after_docs": len(after_docs),
        "doc_intersection_after": doc_intersection,
        "query_intersection_after": query_intersection,
        "training_authorized": False,
    }
    (EXCL / "exclusion_proof.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


def norm_of(row: dict) -> str:
    return row["normalized_query"]


if __name__ == "__main__":
    main()
