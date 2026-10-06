"""Audit benchmark/data identities with CPU fingerprints; never run retrieval."""

from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pymupdf
from PIL import Image
from scipy.fft import dctn

REV = "9bdca77be633cc3259d7e3739d35b38ab00bf5d9"
EXTERNAL = Path("data/raw/sciegqa_bench") / REV
LOCAL = Path("data/raw/mmdocir_evaluation")
OUT = Path("artifacts/route_v2_data/identity_v1")
# Fixed before examining any match or model outcome.
POLICY = {
    "version": "identity-v1", "external_revision": REV,
    "page_text_shingle_words": 5, "min_page_tokens": 80,
    "page_text_jaccard_min": 0.80, "candidate_shared_shingles_min": 20,
    "image_phash_bits": 64, "phash_hamming_max": 6,
    "image_normalized_rmse_max": 0.06, "min_image_std": 12.0,
    "query_token_jaccard_min": 0.90, "query_min_tokens": 8,
    "policy": "quarantine matched MMDocIR documents; never remove external test records",
}


def dump(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def doc_id(name: str) -> str:
    return name[:-4] if name.lower().endswith(".pdf") else name


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKC", text).lower())


def shingles(text: str) -> set[str]:
    words = tokens(text)
    if len(words) < POLICY["min_page_tokens"]:
        return set()
    return {hashlib.blake2b(" ".join(words[i:i + 5]).encode(), digest_size=8).hexdigest()
            for i in range(len(words) - 4)}


def fingerprint(image: Image.Image) -> tuple[int, np.ndarray]:
    small = np.asarray(image.convert("L").resize((32, 32), Image.Resampling.LANCZOS))
    low = dctn(small.astype(float), type=2, norm="ortho")[:8, :8].flatten()
    bits = low > np.median(low[1:])
    bits[0] = False
    return int.from_bytes(np.packbits(bits).tobytes(), "big"), small


def page_fp(doc: str, page: int, text: str, image: Image.Image) -> tuple[dict, np.ndarray, set[str]]:
    ph, small = fingerprint(image)
    return {"doc_id": doc, "page": page, "phash": ph, "image_std": float(small.std())}, small, shingles(text)


def external_pages() -> tuple[list, np.ndarray, list]:
    records, thumbnails, texts = [], [], []
    with tarfile.open(EXTERNAL / "PDF.tar") as archive:
        members = sorted((m for m in archive.getmembers() if m.isfile() and m.name.endswith(".pdf")), key=lambda x: x.name)
        for i, member in enumerate(members):
            match = re.search(r"(\d{4}\.\d{4,5})(?:v\d+)?", member.name)
            if not match:
                raise ValueError(f"No arXiv identity in PDF path: {member.name}")
            doc = match.group(1)
            stream = archive.extractfile(member)
            assert stream is not None
            with pymupdf.open(stream=stream.read(), filetype="pdf") as pdf:
                for page_index, page in enumerate(pdf):
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(96 / page.rect.width, 96 / page.rect.height), colorspace=pymupdf.csGRAY, alpha=False)
                    image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
                    record, thumb, words = page_fp(doc, page_index + 1, page.get_text(), image)
                    records.append(record)
                    thumbnails.append(thumb)
                    texts.append(words)
            if (i + 1) % 10 == 0:
                print(f"External identity: {i + 1}/{len(members)} documents", flush=True)
    return records, np.asarray(thumbnails), texts


def local_pages() -> tuple[list, np.ndarray, list]:
    records, thumbnails, texts = [], [], []
    source = pq.ParquetFile(LOCAL / "MMDocIR_pages.parquet")
    for batch in source.iter_batches(batch_size=128, columns=["doc_name", "passage_id", "image_binary", "ocr_text"]):
        for row in batch.to_pylist():
            with Image.open(io.BytesIO(row["image_binary"])) as image:
                record, thumb, words = page_fp(doc_id(row["doc_name"]), int(row["passage_id"]), row.get("ocr_text") or "", image)
            record["image_bytes_sha256"] = hashlib.sha256(row["image_binary"]).hexdigest()
            records.append(record)
            thumbnails.append(thumb)
            texts.append(words)
        if len(records) % 1024 == 0:
            print(f"MMDocIR identity: {len(records)}/{source.metadata.num_rows} pages", flush=True)
    return records, np.asarray(thumbnails), texts


def cached_pages(name: str, builder) -> tuple[list, np.ndarray, list]:
    path = OUT / f"{name}_fingerprints.json"
    images = OUT / f"{name}_thumbnails.npz"
    binding_path = OUT / f"{name}_cache_binding.json"
    source = EXTERNAL / "PDF.tar" if name == "external" else LOCAL / "MMDocIR_pages.parquet"
    binding = {"source": source.as_posix(), "source_sha256": sha(source), "fingerprint_algorithm": "grayscale32-lanczos-dct64-v1+normalized-word5-blake2b64-v1", "policy": POLICY}
    if path.exists() and images.exists():
        if not binding_path.exists():
            # Adopt the first run only when its recorded source hashes verify it.
            report_path = OUT / "overlap_report.json"
            previous = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
            if previous.get("inputs", {}).get(source.as_posix()) != binding["source_sha256"] or previous.get("policy") != POLICY:
                raise RuntimeError("Unbound cache: recreate fingerprints under a new version")
            dump(binding_path, binding)
        if json.loads(binding_path.read_text(encoding="utf-8")) != binding:
            raise RuntimeError("Fingerprint source/policy changed; use a new audit version")
        data = json.loads(path.read_text(encoding="utf-8"))
        return data["records"], np.load(images)["images"], [set(s) for s in data["text_shingles"]]
    records, thumbs, texts = builder()
    dump(path, {"records": records, "text_shingles": [sorted(s) for s in texts]})
    np.savez_compressed(images, images=thumbs)
    dump(binding_path, binding)
    return records, thumbs, texts


def compare_pages(left, limages, ltext, right, rimages, rtext) -> tuple[list, dict]:
    matches = []
    index = defaultdict(list)
    for j, words in enumerate(rtext):
        for word in words:
            index[word].append(j)
    hashes = np.asarray([r["phash"] for r in right], dtype=np.uint64)
    lookup = np.asarray([int(i).bit_count() for i in range(256)], dtype=np.uint8)
    image_candidates = 0
    for i, row in enumerate(left):
        # Full external/local page comparison, not just filenames or evidence pages.
        shared = Counter(j for word in ltext[i] for j in index.get(word, []))
        for j, count in shared.items():
            if count < POLICY["candidate_shared_shingles_min"]:
                continue
            score = count / len(ltext[i] | rtext[j])
            if score >= POLICY["page_text_jaccard_min"]:
                matches.append({"kind": "page_text", "local_doc": row["doc_id"], "local_page": row["page"], "external_doc": right[j]["doc_id"], "external_page": right[j]["page"], "jaccard": score})
        if row["image_std"] < POLICY["min_image_std"]:
            continue
        xor = (hashes ^ np.uint64(row["phash"])).view(np.uint8).reshape(-1, 8)
        distances = lookup[xor].sum(axis=1)
        for j in np.flatnonzero(distances <= POLICY["phash_hamming_max"]):
            if right[j]["image_std"] < POLICY["min_image_std"]:
                continue
            image_candidates += 1
            rmse = float(np.sqrt(np.mean((limages[i].astype(float) / 255 - rimages[j] / 255) ** 2)))
            if rmse <= POLICY["image_normalized_rmse_max"]:
                matches.append({"kind": "page_image", "local_doc": row["doc_id"], "local_page": row["page"], "external_doc": right[j]["doc_id"], "external_page": right[j]["page"], "hamming": int(distances[j]), "rmse": rmse})
        if (i + 1) % 4096 == 0:
            print(f"Compared {i + 1}/{len(left)} local pages", flush=True)
    return matches, {"image_candidates": image_candidates}


def main() -> None:
    start = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)
    policy_path = OUT / "identity_policy.json"
    if policy_path.exists() and json.loads(policy_path.read_text()) != POLICY:
        raise RuntimeError("Do not change an existing fingerprint policy; use a new version")
    dump(policy_path, POLICY)
    annotations = [json.loads(s) for s in (LOCAL / "MMDocIR_annotations.jsonl").read_text(encoding="utf-8").splitlines() if s.strip()]
    external_rows = [json.loads(s) for s in (EXTERNAL / "SciEGQA_Bench.jsonl").read_text(encoding="utf-8").splitlines() if s.strip()]
    external_docs = {doc_id(r["doc_name"]) for r in external_rows}
    local_docs = {doc_id(r["doc_name"]) for r in annotations}
    matches = []
    for doc in sorted(local_docs):
        base = re.sub(r"v\d+$", "", doc)
        if base in external_docs:
            matches.append({"kind": "document_id", "local_doc": doc, "external_doc": base})
    q_external = [set(tokens(row["query"])) for row in external_rows]
    for item in annotations:
        doc = doc_id(item["doc_name"])
        for qi, q in enumerate(item["questions"]):
            qt = set(tokens(q["Q"]))
            if len(qt) < POLICY["query_min_tokens"]:
                continue
            for j, et in enumerate(q_external):
                if len(et) < POLICY["query_min_tokens"]:
                    continue
                score = len(qt & et) / len(qt | et)
                if score >= POLICY["query_token_jaccard_min"]:
                    matches.append({"kind": "query_text", "local_doc": doc, "local_question_index": qi, "external_row": j, "external_doc": external_rows[j]["doc_name"], "jaccard": score})
    ext, ei, et = cached_pages("external", external_pages)
    local, li, lt = cached_pages("mmdocir", local_pages)
    if {r["doc_id"] for r in ext} != external_docs or {r["doc_id"] for r in local} != local_docs:
        raise RuntimeError("Fingerprint document coverage mismatch")
    found, counts = compare_pages(local, li, lt, ext, ei, et)
    matches.extend(found)
    quarantine = sorted({m["local_doc"] for m in matches})
    # Detect identical raw pages inside the MMDocIR universe, including old split boundaries.
    groups = defaultdict(set)
    for row in local:
        groups[row["image_bytes_sha256"]].add(row["doc_id"])
    duplicate_groups = sorted([sorted(group) for group in groups.values() if len(group) > 1])
    proof = {
        "status": "screening_complete", "meaning": "screening candidates only; image/template matches need verification before quarantine and split checks",
        "policy": POLICY, "counts": {"mmdocir_documents": len(local_docs), "mmdocir_pages": len(local), "external_documents": len(external_docs), "external_pdf_pages": len(ext), "external_questions": len(external_rows), **counts},
        "matches": matches, "quarantined_docs": quarantine,
        "local_exact_page_duplicate_groups": duplicate_groups,
        "inputs": {p.as_posix(): sha(p) for p in [LOCAL / "MMDocIR_annotations.jsonl", LOCAL / "MMDocIR_pages.parquet", EXTERNAL / "SciEGQA_Bench.jsonl", EXTERNAL / "PDF.tar"]},
        "limitations": ["heuristic near-duplicate thresholds cannot prove absence of every reformatting/translation", "external images are rendered from official PDFs; original PNG archive not acquired", "short generic questions excluded from semantic near-duplicate matching", "pretraining exposure unknown", "dataset license is separately unresolved"],
        "test_scored": False, "elapsed_seconds": time.monotonic() - start,
    }
    dump(OUT / "overlap_report.json", proof)
    print(json.dumps({"counts": proof["counts"], "match_counts": dict(Counter(m["kind"] for m in matches)), "quarantined_docs": quarantine, "local_duplicate_groups": len(duplicate_groups), "elapsed_seconds": proof["elapsed_seconds"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
