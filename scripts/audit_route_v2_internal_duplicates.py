"""Audit internal MMDocIR page identities using metadata and OCR, never model scores.

No question, answer, evidence mapping, or raw OCR text is emitted. Run only after
registering this command. Existing outputs cannot be replaced by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import re
import time
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

POLICY = {
    "version": "internal-identity-v1",
    "text_ngram_words": 3,
    "text_min_tokens": 80,
    "text_min_unique_ngrams": 40,
    "text_jaccard_confirm_min": 0.85,
    "text_sketch_ngrams": 32,
    "text_candidate_shared_sketch_min": 2,
    "text_posting_max_pages": 64,
    "exact_long_text_channel": "NFKC + lowercase + whitespace collapse; not sketch-filtered",
    "phash_bits": 64,
    "phash_hamming_max": 4,
    "phash_bucket_bits": [13, 13, 13, 13, 12],
    "phash_bucket_max_pages": 256,
    "image_min_std": 12.0,
    "image_ink_threshold": 245,
    "image_min_ink_fraction": 0.03,
    "image_min_occupied_rows": 8,
    "image_min_occupied_columns": 8,
    "doc_pair_min_distinct_matching_pages_each": 2,
    "single_page_document_exception": "both documents contain exactly one page",
    "singleton_page_overlap": "unresolved document relation; never call whole documents identical",
    "no_text_image_match": "unknown, not automatically confirmed",
    "same_document_pairs": "ignored",
    "unknown_group_policy": "report only; role-level quarantine belongs to the split runner",
}


def doc_id(name: str) -> str:
    return name[:-4] if name.lower().endswith(".pdf") else name


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def text_signature(text: str) -> tuple[int, set[int]]:
    words = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).lower())
    grams = {
        int.from_bytes(hashlib.blake2b(" ".join(words[i : i + 3]).encode(), digest_size=8).digest())
        for i in range(len(words) - 2)
    }
    return len(words), grams


def body_available(signature: tuple[int, set[int]]) -> bool:
    count, grams = signature
    return count >= POLICY["text_min_tokens"] and len(grams) >= POLICY["text_min_unique_ngrams"]


def informative_image(record: Mapping, thumbnail: np.ndarray) -> bool:
    ink = thumbnail < POLICY["image_ink_threshold"]
    return (
        record["image_std"] >= POLICY["image_min_std"]
        and float(ink.mean()) >= POLICY["image_min_ink_fraction"]
        and int(ink.any(axis=1).sum()) >= POLICY["image_min_occupied_rows"]
        and int(ink.any(axis=0).sum()) >= POLICY["image_min_occupied_columns"]
    )


def components(pairs: Sequence[tuple[str, str]]) -> list[list[str]]:
    parent: dict[str, str] = {}

    def root(doc: str) -> str:
        parent.setdefault(doc, doc)
        if parent[doc] != doc:
            parent[doc] = root(parent[doc])
        return parent[doc]

    for left, right in pairs:
        parent[root(left)] = root(right)
    groups: dict[str, set[str]] = defaultdict(set)
    for doc in parent:
        groups[root(doc)].add(doc)
    return sorted(sorted(group) for group in groups.values() if len(group) > 1)


def audit_records(
    records: Sequence[Mapping],
    thumbnails: np.ndarray,
    ocr_texts: Sequence[str],
    pool_by_doc: Mapping[str, str] | None = None,
) -> dict:
    """Return numerical/hash evidence and document IDs; inputs are not modified."""
    if len(records) != len(thumbnails) or len(records) != len(ocr_texts):
        raise ValueError("Page fingerprints, thumbnails, and OCR must align exactly")
    if thumbnails.shape[1:] != (32, 32):
        raise ValueError("Expected cached 32 by 32 thumbnails")
    keys = [(record["doc_id"], record["page"]) for record in records]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate document/page key in cached fingerprints")
    pools = pool_by_doc or {}
    signatures = [text_signature(text) for text in ocr_texts]
    bodies = [body_available(signature) for signature in signatures]
    repetitive = [
        count >= POLICY["text_min_tokens"] and len(grams) < POLICY["text_min_unique_ngrams"]
        for count, grams in signatures
    ]
    image_eligible = [
        informative_image(record, thumbnails[index]) and not repetitive[index]
        for index, record in enumerate(records)
    ]
    candidates: dict[tuple[int, int], set[str]] = defaultdict(set)

    def add(left: int, right: int, kind: str) -> None:
        if records[left]["doc_id"] != records[right]["doc_id"]:
            candidates[min(left, right), max(left, right)].add(kind)

    # Exact long OCR duplicates must not disappear merely because all their
    # trigrams are frequent or their visual template belongs to a large bucket.
    # Hash buckets only join identical normalized pages, never the full corpus.
    exact_text_buckets: dict[str, list[int]] = defaultdict(list)
    for index, text in enumerate(ocr_texts):
        if not bodies[index]:
            continue
        normalized = " ".join(unicodedata.normalize("NFKC", text).lower().split())
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        for other in exact_text_buckets[digest]:
            add(index, other, "exact_normalized_long_text")
        exact_text_buckets[digest].append(index)

    frequency: Counter = Counter()
    for available, (_, grams) in zip(bodies, signatures, strict=True):
        if available:
            frequency.update(grams)
    sketch_index: dict[int, list[int]] = defaultdict(list)
    for index, (_, grams) in enumerate(signatures):
        if not bodies[index]:
            continue
        sketch = heapq.nsmallest(
            POLICY["text_sketch_ngrams"],
            (gram for gram in grams if frequency[gram] <= POLICY["text_posting_max_pages"]),
            key=lambda gram: (frequency[gram], gram),
        )
        shared = Counter(other for gram in sketch for other in sketch_index[gram])
        for other, count in shared.items():
            if count >= POLICY["text_candidate_shared_sketch_min"]:
                add(index, other, "rare_text_sketch")
        for gram in sketch:
            sketch_index[gram].append(index)
    frequency.clear()
    sketch_index.clear()

    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    exact_buckets: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        if not image_eligible[index]:
            continue
        offset = 0
        for segment, width in enumerate(POLICY["phash_bucket_bits"]):
            buckets[segment, (int(record["phash"]) >> offset) & ((1 << width) - 1)].append(index)
            offset += width
        image_sha = record.get("image_bytes_sha256")
        if image_sha:
            exact_buckets[image_sha].append(index)
    skipped_buckets = 0
    skipped_bucket_pages: set[int] = set()
    for bucket in buckets.values():
        if len(bucket) > POLICY["phash_bucket_max_pages"]:
            skipped_buckets += 1
            skipped_bucket_pages.update(bucket)
            continue
        for position, left in enumerate(bucket):
            for right in bucket[position + 1 :]:
                distance = (int(records[left]["phash"]) ^ int(records[right]["phash"])).bit_count()
                if distance <= POLICY["phash_hamming_max"]:
                    add(left, right, "phash")
    for bucket in exact_buckets.values():
        if len(bucket) > POLICY["phash_bucket_max_pages"]:
            skipped_buckets += 1
            skipped_bucket_pages.update(bucket)
            continue
        for position, left in enumerate(bucket):
            for right in bucket[position + 1 :]:
                add(left, right, "exact_image_bytes")

    evidence = []
    confirmed_pages: dict[tuple[str, str], list[dict]] = defaultdict(list)
    unknown_docs: set[tuple[str, str]] = set()
    for (left, right), kinds in sorted(candidates.items()):
        lrow, rrow = records[left], records[right]
        lcount, lgrams = signatures[left]
        rcount, rgrams = signatures[right]
        union = lgrams | rgrams
        jaccard = len(lgrams & rgrams) / len(union) if union else None
        adequate = bodies[left] and bodies[right]
        if adequate and jaccard >= POLICY["text_jaccard_confirm_min"]:
            status, reason = "confirmed_page_overlap", "long_ocr_trigram_agreement"
        elif adequate:
            status, reason = "rejected", "similar_template_but_body_text_differs"
        elif kinds & {"phash", "exact_image_bytes"}:
            status, reason = "unknown", "image_match_without_sufficient_ocr_body"
        else:
            continue
        docs = tuple(sorted((lrow["doc_id"], rrow["doc_id"])))
        row = {
            "left_doc": lrow["doc_id"], "left_page": lrow["page"],
            "right_doc": rrow["doc_id"], "right_page": rrow["page"],
            "candidate_kinds": sorted(kinds), "status": status, "reason": reason,
            "left_tokens": lcount, "right_tokens": rcount,
            "left_unique_trigrams": len(lgrams), "right_unique_trigrams": len(rgrams),
            "text_jaccard": jaccard,
            "phash_hamming": (int(lrow["phash"]) ^ int(rrow["phash"])).bit_count(),
            "thumbnail_rmse": float(np.sqrt(np.mean(
                ((thumbnails[left].astype(float) - thumbnails[right].astype(float)) / 255) ** 2
            ))),
            "exact_image_bytes": bool(lrow.get("image_bytes_sha256"))
            and lrow.get("image_bytes_sha256") == rrow.get("image_bytes_sha256"),
            "left_legacy_pool": pools.get(lrow["doc_id"], "unknown"),
            "right_legacy_pool": pools.get(rrow["doc_id"], "unknown"),
        }
        evidence.append(row)
        if status == "confirmed_page_overlap":
            confirmed_pages[docs].append(row)
        elif status == "unknown":
            unknown_docs.add(docs)

    doc_page_counts = Counter(record["doc_id"] for record in records)
    confirmed_doc_pairs = []
    singleton_pairs = []
    for docs, matches in sorted(confirmed_pages.items()):
        supported = {doc: set() for doc in docs}
        for row in matches:
            supported[row["left_doc"]].add(row["left_page"])
            supported[row["right_doc"]].add(row["right_page"])
        row = {
            "documents": list(docs), "matching_page_pairs": len(matches),
            "distinct_matching_pages": {doc: len(pages) for doc, pages in supported.items()},
            "total_document_pages": {doc: doc_page_counts[doc] for doc in docs},
        }
        enough = min(map(len, supported.values())) >= POLICY["doc_pair_min_distinct_matching_pages_each"]
        if enough or all(doc_page_counts[doc] == 1 for doc in docs):
            confirmed_doc_pairs.append(row)
        else:
            singleton_pairs.append(row)
            unknown_docs.add(docs)
    return {
        "status": "completed_with_unresolved_pairs" if unknown_docs else "completed_with_limits",
        "policy": POLICY,
        "counts": {
            "documents": len(doc_page_counts), "pages": len(records),
            "pages_with_sufficient_body": sum(bodies),
            "pages_image_eligible": sum(image_eligible),
            "repetitive_text_pages_suppressed": sum(repetitive),
            "candidate_page_pairs": len(candidates),
            "pair_statuses": dict(Counter(row["status"] for row in evidence)),
            "oversized_image_buckets_skipped": skipped_buckets,
            "pages_in_skipped_image_buckets": len(skipped_bucket_pages),
        },
        "confirmed_doc_groups": components([tuple(row["documents"]) for row in confirmed_doc_pairs]),
        "unknown_doc_groups": components(sorted(unknown_docs)),
        "confirmed_doc_pairs": confirmed_doc_pairs,
        "singleton_page_overlap_pairs": singleton_pairs,
        "page_pair_evidence": evidence,
        "limitations": [
            "Groups mean shared page evidence requiring role isolation, not whole-document equivalence.",
            "One shared copyright/frontmatter page is not automatically a confirmed document duplicate.",
            "Sparse text sketches and capped image buckets do not guarantee exhaustive near-duplicate recall.",
            "Low-resolution image similarity alone cannot establish page identity; OCR-poor matches remain unknown.",
            "Common trigrams, visually sparse pages, and repetitive text are suppressed to reduce boilerplate links.",
            "Transitive unknown groups are review/isolation candidates, not certified duplication or a final split.",
            "Identical translations, reformatted pages, OCR failures, and semantic paraphrases can be missed.",
        ],
        "training_performed": False, "retrieval_or_region_scoring_performed": False,
    }


def load_pool_ids(paths: Sequence[Path]) -> dict[str, str]:
    result = {}
    for path in paths:
        pool = path.stem.removesuffix("_ids")
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                doc = doc_id(json.loads(line)["doc_name"])
                if doc in result and result[doc] != pool:
                    raise ValueError("Document crosses legacy pools")
                result[doc] = pool
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-dir", type=Path, default=Path("artifacts/route_v2_data/identity_v1"))
    parser.add_argument("--pages", type=Path, default=Path("data/raw/mmdocir_evaluation/MMDocIR_pages.parquet"))
    parser.add_argument("--legacy-dir", type=Path, default=Path("experiments/s2_splits"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/route_v2_data/internal_identity_v1.json"))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to replace audit: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    policy_path = args.output.with_suffix(".policy.json")
    if policy_path.exists():
        if json.loads(policy_path.read_text(encoding="utf-8")) != POLICY:
            raise ValueError("Existing audit policy differs; use a new version/output")
    else:
        with policy_path.open("x", encoding="utf-8") as handle:
            json.dump(POLICY, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    start = time.monotonic()
    fp_path = args.identity_dir / "mmdocir_fingerprints.json"
    image_path = args.identity_dir / "mmdocir_thumbnails.npz"
    legacy_paths = [args.legacy_dir / f"{pool}_ids.jsonl" for pool in ("dev_eval", "test_eval")]
    sources = [fp_path, image_path, args.pages, *legacy_paths]
    before = {path.as_posix(): {"sha256": sha(path), "size_bytes": path.stat().st_size} for path in sources}
    print("Inputs hashed; policy persisted. Reading OCR metadata only.", flush=True)
    records = json.loads(fp_path.read_text(encoding="utf-8"))["records"]
    with np.load(image_path) as archive:
        images = archive["images"]
    text_by_key = {}
    parquet = pq.ParquetFile(args.pages)
    for batch in parquet.iter_batches(batch_size=512, columns=["doc_name", "passage_id", "ocr_text"]):
        for row in batch.to_pylist():
            key = doc_id(row["doc_name"]), int(row["passage_id"])
            if key in text_by_key:
                raise ValueError("Duplicate document/page key in raw page metadata")
            text_by_key[key] = row.get("ocr_text") or ""
    keys = [(row["doc_id"], row["page"]) for row in records]
    if set(keys) != set(text_by_key):
        raise ValueError("Cached fingerprints do not cover the exact raw-page metadata universe")
    report = audit_records(records, images, [text_by_key[key] for key in keys], load_pool_ids(legacy_paths))
    for path in sources:
        if sha(path) != before[path.as_posix()]["sha256"]:
            raise RuntimeError(f"Source changed while auditing: {path}")
    report["inputs"] = before
    report["input_hashes_unchanged"] = True
    report["elapsed_seconds"] = time.monotonic() - start
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"status": report["status"], "counts": report["counts"],
                      "confirmed_doc_groups": len(report["confirmed_doc_groups"]),
                      "unknown_doc_groups": len(report["unknown_doc_groups"]),
                      "output": args.output.as_posix()}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
