"""Verify identity candidates using document content, never questions or gold boxes.

This is a conservative second stage: unresolved candidates remain quarantined.
The report is not a declaration that a final train/test split has passed.
"""

from __future__ import annotations

import hashlib
import io
import itertools
import json
import re
import tarfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pymupdf
from PIL import Image, ImageOps

REV = "9bdca77be633cc3259d7e3739d35b38ab00bf5d9"
EXTERNAL = Path("data/raw/sciegqa_bench") / REV
PAGES = Path("data/raw/mmdocir_evaluation/MMDocIR_pages.parquet")
IDENTITY = Path("artifacts/route_v2_data/identity_v1")
OUT = Path("artifacts/route_v2_data/verification_v1")
POLICY = {
    "version": "verification-v1",
    "min_text_tokens": 80,
    "shingle_words": 3,
    "confirmed_shingle_jaccard_min": 0.80,
    "confirmed_shared_shingles_min": 20,
    "rejected_shingle_jaccard_max": 0.05,
    "rejected_word_jaccard_max": 0.30,
    "rejected_ink_dice_max": 0.60,
    "image_size": 160,
    "image_translation_pixels": [-2, -1, 0, 1, 2],
    "title_min_words": 4,
    "title_shingle_containment_min": 0.85,
    "title_min_shared_shingles": 3,
    "local_text_pages": 2,
    "decision": "unresolved means quarantine; image similarity alone cannot confirm identity",
}


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalized_words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    return re.findall(r"[^\W_]+", text)


def text_shingles(words: list[str]) -> set[tuple[str, ...]]:
    n = POLICY["shingle_words"]
    return {tuple(words[index:index + n]) for index in range(len(words) - n + 1)}


def jaccard(left: set, right: set) -> float:
    return len(left & right) / len(left | right) if left or right else 0.0


def lexical_metrics(left: str, right: str) -> dict:
    lw, rw = normalized_words(left), normalized_words(right)
    ls, rs = text_shingles(lw), text_shingles(rw)
    return {
        "left_tokens": len(lw), "right_tokens": len(rw),
        "normalized_exact": bool(lw) and lw == rw,
        "word_jaccard": jaccard(set(lw), set(rw)),
        "shingle_jaccard": jaccard(ls, rs), "shared_shingles": len(ls & rs),
    }


def strong_text_match(metrics: dict) -> bool:
    enough = min(metrics["left_tokens"], metrics["right_tokens"]) >= POLICY["min_text_tokens"]
    return enough and (metrics["normalized_exact"] or (
        metrics["shingle_jaccard"] >= POLICY["confirmed_shingle_jaccard_min"]
        and metrics["shared_shingles"] >= POLICY["confirmed_shared_shingles_min"]
    ))


def image_canvas(image: Image.Image) -> np.ndarray:
    side = POLICY["image_size"]
    resized = ImageOps.contain(image.convert("L"), (side, side), Image.Resampling.LANCZOS)
    canvas = Image.new("L", (side, side), 255)
    canvas.paste(resized, ((side - resized.width) // 2, (side - resized.height) // 2))
    return np.asarray(canvas, dtype=np.float32) / 255.0


def translated(array: np.ndarray, dx: int, dy: int) -> np.ndarray:
    height, width = array.shape
    result = np.zeros_like(array)
    sx, sy = max(0, -dx), max(0, -dy)
    tx, ty = max(0, dx), max(0, dy)
    result[ty:height - max(0, -dy), tx:width - max(0, -dx)] = array[
        sy:height - max(0, dy), sx:width - max(0, dx)
    ]
    return result


def image_metrics(left: np.ndarray, right: np.ndarray) -> dict:
    # Continuous foreground Dice does not let a large white background dominate.
    li, ri = 1.0 - left, 1.0 - right
    denominator = float(li.sum() + ri.sum())
    best, shift = 0.0, (0, 0)
    if denominator > 0:
        for dx, dy in itertools.product(POLICY["image_translation_pixels"], repeat=2):
            score = float(2 * np.minimum(li, translated(ri, dx, dy)).sum() / denominator)
            if score > best:
                best, shift = score, (dx, dy)
    return {
        "ink_dice": best, "alignment_translation": list(shift),
        "gray_rmse": float(np.sqrt(np.mean((left - right) ** 2))),
        "left_ink_fraction": float(li.mean()), "right_ink_fraction": float(ri.mean()),
    }


def classify_candidate(lexical: dict, visual: dict) -> tuple[str, str]:
    if strong_text_match(lexical):
        return "confirmed", "long_normalized_text_or_high_threegram_overlap"
    enough = min(lexical["left_tokens"], lexical["right_tokens"]) >= POLICY["min_text_tokens"]
    if (enough and lexical["shingle_jaccard"] <= POLICY["rejected_shingle_jaccard_max"]
            and lexical["word_jaccard"] <= POLICY["rejected_word_jaccard_max"]
            and visual["ink_dice"] < POLICY["rejected_ink_dice_max"]):
        return "rejected_template", "sufficient_text_disagrees_and_foreground_image_disagrees"
    return "unresolved", "insufficient_or_intermediate_identity_evidence"


def title_match(title: str, page_text: str) -> dict:
    tw, pw = normalized_words(title), normalized_words(page_text)
    ts, ps = text_shingles(tw), text_shingles(pw)
    exact = bool(tw) and f" {' '.join(tw)} " in f" {' '.join(pw)} "
    shared = len(ts & ps)
    containment = shared / len(ts) if ts else 0.0
    eligible = len(tw) >= POLICY["title_min_words"]
    matched = eligible and (exact or (
        containment >= POLICY["title_shingle_containment_min"]
        and shared >= POLICY["title_min_shared_shingles"]
    ))
    return {"matched": matched, "title_tokens": len(tw), "exact_phrase": exact,
            "shared_shingles": shared, "shingle_containment": containment}


def identity_name(name: str) -> str:
    return name[:-4] if name.lower().endswith(".pdf") else name


def assert_receipt(directory: Path, receipt: dict) -> None:
    path = directory / "input_receipt.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != receipt:
        raise RuntimeError("Source, policy, or script changed: use a new verification directory")
    dump(path, receipt)


def load_local(required: set[tuple[str, int]]) -> dict:
    selected = {}
    source = pq.ParquetFile(PAGES)
    for batch in source.iter_batches(
        batch_size=64, columns=["doc_name", "passage_id", "ocr_text", "image_binary"]
    ):
        for row in batch.to_pylist():
            key = (identity_name(row["doc_name"]), int(row["passage_id"]))
            if key not in required:
                continue
            if key in selected:
                raise ValueError(f"Duplicate local page identity: {key}")
            with Image.open(io.BytesIO(row["image_binary"])) as image:
                selected[key] = {"text": row.get("ocr_text") or "", "image": image_canvas(image)}
    if set(selected) != required:
        raise ValueError("Required local candidate/first-page identity missing")
    return selected


def load_external(required: set[tuple[str, int]]) -> tuple[dict, dict]:
    selected, titles = {}, {}
    with tarfile.open(EXTERNAL / "PDF.tar") as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.lower().endswith(".pdf"):
                continue
            name = Path(member.name).stem
            match = re.match(r"(\d{4}\.\d{4,5})(?:v\d+)?[_ -]*(.*)", name)
            if not match:
                raise ValueError(f"PDF lacks arXiv identity: {member.name}")
            doc, title = match.groups()
            if doc in titles:
                raise ValueError(f"Duplicate external document identity: {doc}")
            titles[doc] = title.replace("_", " ")
            pages = {page for document, page in required if document == doc}
            if not pages:
                continue
            stream = archive.extractfile(member)
            assert stream is not None
            with pymupdf.open(stream=stream.read(), filetype="pdf") as pdf:
                for page_num in sorted(pages):
                    page = pdf[page_num - 1]
                    scale = POLICY["image_size"] / max(page.rect.width, page.rect.height)
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                         colorspace=pymupdf.csGRAY, alpha=False)
                    image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
                    selected[(doc, page_num)] = {"text": page.get_text(), "image": image_canvas(image)}
    if set(selected) != required:
        raise ValueError("Required external candidate page identity missing")
    return selected, titles


def main() -> None:
    report_path = IDENTITY / "overlap_report.json"
    fingerprint_path = IDENTITY / "mmdocir_fingerprints.json"
    inputs = [report_path, fingerprint_path, PAGES, EXTERNAL / "PDF.tar"]
    hashes = {str(path).replace("\\", "/"): sha(path) for path in inputs}
    original = json.loads(report_path.read_text(encoding="utf-8"))
    for path in [PAGES, EXTERNAL / "PDF.tar"]:
        if original["inputs"][path.as_posix()] != hashes[path.as_posix()]:
            raise RuntimeError("Raw input changed since identity-v1; regenerate first stage")
    OUT.mkdir(parents=True, exist_ok=True)
    assert_receipt(OUT, {"policy": POLICY, "source_sha256": hashes,
                         "script_sha256": sha(Path(__file__))})
    records = json.loads(fingerprint_path.read_text(encoding="utf-8"))["records"]
    doc_pages = defaultdict(set)
    for row in records:
        doc_pages[row["doc_id"]].add(row["page"])
    first_pages = {doc: sorted(pages)[:POLICY["local_text_pages"]] for doc, pages in doc_pages.items()}
    pairs = [row for row in original["matches"] if row["kind"] == "page_image"]
    needed_local = {(doc, page) for doc, pages in first_pages.items() for page in pages}
    needed_local.update((row["local_doc"], row["local_page"]) for row in pairs)
    needed_external = {(row["external_doc"], row["external_page"]) for row in pairs}
    local = load_local(needed_local)
    external, titles = load_external(needed_external)
    verified = []
    for pair in pairs:
        lp = local[(pair["local_doc"], pair["local_page"])]
        ep = external[(pair["external_doc"], pair["external_page"])]
        lexical, visual = lexical_metrics(lp["text"], ep["text"]), image_metrics(lp["image"], ep["image"])
        decision, reason = classify_candidate(lexical, visual)
        verified.append({**pair, "lexical": lexical, "visual": visual,
                         "decision": decision, "reason": reason})
    title_candidates, local_text_edges = [], []
    for doc, pages in first_pages.items():
        for page in pages:
            text = local[(doc, page)]["text"]
            for external_doc, title in titles.items():
                result = title_match(title, text)
                if result["matched"]:
                    title_candidates.append({"local_doc": doc, "local_page": page,
                                             "external_doc": external_doc, **result,
                                             "decision": "unresolved_title_candidate"})
    # Inverted shingles avoid repeatedly tokenizing every possible document pair.
    ordered_pages = sorted((doc, page) for doc, pages in first_pages.items() for page in pages)
    page_words = [normalized_words(local[key]["text"]) for key in ordered_pages]
    page_shingles = [text_shingles(words) for words in page_words]
    index = defaultdict(list)
    for page_index, words in enumerate(page_shingles):
        for word in words:
            index[word].append(page_index)
    for i, (left, lp) in enumerate(ordered_pages):
        if len(page_words[i]) < POLICY["min_text_tokens"]:
            continue
        shared = Counter(j for word in page_shingles[i] for j in index[word] if j > i)
        for j, count in shared.items():
            right, rp = ordered_pages[j]
            if left == right or (
                count < POLICY["confirmed_shared_shingles_min"] and page_words[i] != page_words[j]
            ):
                continue
            result = lexical_metrics(local[(left, lp)]["text"], local[(right, rp)]["text"])
            if strong_text_match(result):
                local_text_edges.append({"left_doc": left, "right_doc": right,
                                         "left_page": lp, "right_page": rp,
                                         "lexical": result, "reason": "first_two_pages_strong_text_match"})
    quarantined = {row["local_doc"] for row in verified if row["decision"] != "rejected_template"}
    quarantined.update(row["local_doc"] for row in title_candidates)
    result = {
        "status": "verification_complete_pending_split_audit", "policy": POLICY,
        "source_sha256": hashes, "candidate_decisions": verified,
        "decision_counts": dict(Counter(row["decision"] for row in verified)),
        "title_candidates": title_candidates, "title_document_count": len(titles),
        "local_first_pages_document_count": len(first_pages),
        "local_first_pages_text_edges": local_text_edges,
        "local_exact_page_duplicate_groups": original["local_exact_page_duplicate_groups"],
        "quarantine_from_this_verification": sorted(quarantined),
        "other_identity_matches": [row for row in original["matches"] if row["kind"] != "page_image"],
        "limitations": ["Not a final independence pass: apply all quarantine and local duplicate components before split validation.",
                        "Title matches in first two pages are candidates, not automatic document identity.",
                        "Image-only ambiguous candidates are conservatively unresolved.",
                        "Local text comparison covers first two pages; separate full-page near-duplicate audit is required.",
                        "Thresholds identify observable similarities; they cannot rule out every rewriting or translation."],
        "questions_or_gold_read": False, "retrieval_or_model_scoring": False,
    }
    dump(OUT / "verification_report.json", result)
    print(json.dumps({"status": result["status"], "image_candidate_decisions": result["decision_counts"],
                      "title_candidates": len(title_candidates), "local_text_edges": len(local_text_edges),
                      "quarantine_documents": len(quarantined)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
