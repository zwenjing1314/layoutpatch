"""Validate existing data roles and archive pinned external identities, without scoring.

Does not regenerate/replace data-roles-v1 or regions-v1. The new receipt qualifies
the original split proof: internal page similarity is excluded from local loss,
not proof that every page of every document is disjoint. No model is loaded.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tarfile
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import polars as pl
import pymupdf

from layoutpatch.datasets.route_v2_split import (
    ROLES,
    build_route_v2_plan,
    write_route_v2_plan,
)

REV = "9bdca77be633cc3259d7e3739d35b38ab00bf5d9"
EXTERNAL = Path("data/raw/sciegqa_bench") / REV
SPLIT = Path("experiments/route_v2_splits/data-roles-v1")
REGIONS = Path("artifacts/route_v2_data/regions_v1")
OUT = Path("experiments/route_v2_data/v1")
ARCHIVE = Path("artifacts/route_v2_data/source_archive_v1")
RESEARCH = Path("tmp/route_v2_external_research")
ANN = Path("data/raw/mmdocir_evaluation/MMDocIR_annotations.jsonl")
LEGACY = Path("experiments/s2_splits")
SCREEN = Path("artifacts/route_v2_data/identity_v1/overlap_report.json")
VERIFY = Path("artifacts/route_v2_data/verification_v1/verification_report.json")
INTERNAL = Path("artifacts/route_v2_data/internal_identity_v1.json")


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def archive_sources() -> dict:
    """Keep raw public snapshots outside git; bind URLs to actual snapshot hashes."""
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    root = RESEARCH if (RESEARCH / "source_audit.json").exists() else ARCHIVE
    source = read(root / "source_audit.json")
    names = {Path(row["path"]).name for row in source["receipts"]}
    names.update({"source_audit.json", "bbox_sciegqa_field_comparison.json",
                  "bbox_sciegqa_metadata_audit.json", "snappy_legacy_identity_audit.json",
                  "sciegqa_current_identities.jsonl", "bbox_legacy_identities.jsonl"})
    for name in sorted(names):
        src, dst = root / name, ARCHIVE / name
        if dst.exists():
            require(sha(src) == sha(dst), f"Archive already differs: {name}")
        else:
            shutil.copyfile(src, dst)
    for receipt in source["receipts"]:
        archived = ARCHIVE / Path(receipt["path"]).name
        require(sha(archived) == receipt["sha256"], f"Source receipt differs: {archived}")
        require(archived.stat().st_size == receipt["bytes"], "Source snapshot size differs")
        receipt["original_path"] = receipt["path"]
        receipt["path"] = archived.as_posix()
    # The original subagent scope is retained; root has now processed old test identities.
    source["scope_note"] = "Original exposure notes describe source-research subtask only."
    source["root_exposure"] = {
        "old_test_repurposed": True,
        "old_test_identity_processing": True,
        "external_annotations_programmatically_compared": True,
        "public_ancillary_questions_and_boxes_displayed_initially": True,
        "used_for_training_or_model_selection": False,
        "external_model_scoring": False,
        "strict_never_seen_gold_claim_allowed": False,
    }
    return source


def main() -> None:
    source = archive_sources()
    screen, verify, internal = read(SCREEN), read(VERIFY), read(INTERNAL)
    proof, context = read(SPLIT / "split_proof.json"), read(SPLIT / "identity_inputs.json")
    acquire = read(EXTERNAL / "acquisition.json")
    before: dict[str, str] = {}

    def check_hash(path: str, expected: str) -> None:
        if path not in before:
            before[path] = sha(Path(path))
        require(before[path] == expected, f"Changed input or manifest: {path}")

    for path, digest in context["provenance"]["inputs"].items():
        check_hash(path, digest)
    for report in (screen, verify, internal, read(REGIONS / "audit.json")):
        inputs = report.get("inputs", report.get("source_sha256", {}))
        for path, digest in inputs.items():
            check_hash(path, digest["sha256"] if isinstance(digest, dict) else digest)
    for row in acquire["files"]:
        check_hash(row["path"], row["sha256"])
    for name, digest in proof["file_sha256"].items():
        check_hash((SPLIT / name).as_posix(), digest)
    for role in ("dev_eval", "test_eval"):
        expected = {"dev_eval": "e9179e0734a31a81046139ce7e4dcb3a5389bc938dce11d99db6466ae7dd4e83",
                    "test_eval": "e1910ab08d6494638f46e534f48f55d9dc8db64b26d9242f65ead052f662329c"}
        check_hash((LEGACY / f"{role}_ids.jsonl").as_posix(), expected[role])
    # Record and preserve the other model's accepted work, without editing it.
    protected_paths = [Path("tasks.ps1"), Path("CHANGELOG.md")]
    for directory in ("docs", "configs", "src", "tests", "scripts", "experiments/route_v2_splits"):
        protected_paths.extend(p for p in Path(directory).rglob("*") if p.is_file() and p.suffix in {".py", ".md", ".yaml", ".yml", ".json", ".jsonl", ".txt", ".ps1"})
    protected_paths.extend(Path("artifacts/phase2r").glob("*/ranker.pt"))
    protected_paths.extend(Path("artifacts/fusion/arxivqa").glob("*.pt"))
    protected_paths.extend(REGIONS.glob("*.parquet"))
    for path in protected_paths:
        before.setdefault(path.as_posix(), sha(path))

    annotations = [(i, json.loads(line)) for i, line in enumerate(ANN.read_text(encoding="utf-8").splitlines()) if line.strip()]
    plan = build_route_v2_plan(
        annotations, jsonl(LEGACY / "dev_eval_ids.jsonl"), jsonl(LEGACY / "test_eval_ids.jsonl"),
        external_manifest=acquire, provenance=context["provenance"],
        overlap_report=context["overlap_report"],
        quarantined_docs=verify["quarantine_from_this_verification"],
        identity_units=internal["confirmed_doc_groups"], seed=42, train_ratio=0.8,
    )
    # Reproduce exact outputs in a temporary directory; existing split remains read-only.
    with tempfile.TemporaryDirectory(prefix="route-v2-replay-") as tmp:
        replay = write_route_v2_plan(plan, Path(tmp) / "roles")
        require(replay == proof, "Existing split is not byte-reproducible from its evidence")

    records = [row for role in ROLES for row in jsonl(SPLIT / f"{role}_ids.jsonl")]
    doc_role = {row["doc_id"]: row["role"] for row in records}
    require(len(records) == len({r["query_id"] for r in records}) == 1658, "Question coverage differs")
    require(len(doc_role) == 313, "Document coverage differs")
    require(not proof["identity_units_crossing_roles"], "Confirmed identity units cross active roles")
    ext_conflicts = set(verify["quarantine_from_this_verification"])
    ext_conflicts.update(row["local_doc"] for row in verify["other_identity_matches"])
    require(all(doc_role[d] == "quarantine" for d in ext_conflicts), "External conflicts remain active")

    # Full-page deny list, including nongold pages; future global losses must honor it.
    page_reasons: dict[tuple[str, int], set[str]] = defaultdict(set)
    crossing = []
    for row in internal["page_pair_evidence"]:
        left, right = doc_role[row["left_doc"]], doc_role[row["right_doc"]]
        if row["status"] == "rejected" or left == right or "quarantine" in (left, right):
            continue
        crossing.append(row)
        for side in ("left", "right"):
            page_reasons[(row[f"{side}_doc"], int(row[f"{side}_page"]))].add(row["status"])
    # Earlier title/first-pages audit can find strong text links beyond the stricter full-text rule.
    first_page_additions = 0
    for row in verify["local_first_pages_text_edges"]:
        left, right = doc_role[row["left_doc"]], doc_role[row["right_doc"]]
        if left == right or "quarantine" in (left, right):
            continue
        for side in ("left", "right"):
            key = row[f"{side}_doc"], int(row[f"{side}_page"])
            first_page_additions += key not in page_reasons
            page_reasons[key].add("first_two_pages_strong_text_match")
    units = pl.read_parquet(REGIONS / "units.parquet", columns=[
        "query_id", "doc_id", "page", "role", "local_loss_ready", "page_overlap_excluded",
    ]).to_dicts()
    missed = [u for u in units if (u["doc_id"], u["page"]) in page_reasons and not u["page_overlap_excluded"]]
    require(not missed, f"Unexcluded region units: {len(missed)}; fix a new region version first")
    loss_ready = Counter(u["role"] for u in units if u["local_loss_ready"] and not u["page_overlap_excluded"])
    blocked = [{"doc_id": d, "page": p, "role": doc_role[d], "reasons": sorted(reasons),
                "exclude_from_parameter_updates": True}
               for (d, p), reasons in sorted(page_reasons.items())]

    identities = jsonl(ARCHIVE / "sciegqa_current_identities.jsonl")
    require(len(identities) == 1623, "External record count differs")
    require(len({r["doc_name"] for r in identities}) == 80, "External document count differs")
    require(source["current_revision"] == REV, "External revision differs")
    require(source["metadata"]["sciegqa_current"]["sha256"] == sha(EXTERNAL / "SciEGQA_Bench.jsonl"), "External annotation source differs")
    raw_external = jsonl(EXTERNAL / "SciEGQA_Bench.jsonl")
    for i, (row, identity) in enumerate(zip(raw_external, identities, strict=True)):
        canonical = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        require(hashlib.sha256(canonical).hexdigest() == identity["record_sha256"], "External identity digest differs")
        require(identity["row_index"] == i and row["doc_name"] == identity["doc_name"]
                and row["category"] == identity["category"]
                and row["evidence_page"] == identity["evidence_page"]
                and hashlib.sha256(row["query"].encode()).hexdigest() == identity["query_sha256"],
                "External identity fields differ")
    pdf_pages = {}
    with tarfile.open(EXTERNAL / "PDF.tar") as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.lower().endswith(".pdf"):
                continue
            match = re.match(r"(\d{4}\.\d{4,5})(?:v\d+)?[_ -]", Path(member.name).name)
            require(match is not None, "PDF identity not recognized")
            doc = match.group(1)
            require(doc not in pdf_pages, "Duplicate external PDF identity")
            stream = archive.extractfile(member)
            require(stream is not None, "Missing PDF member")
            with pymupdf.open(stream=stream.read(), filetype="pdf") as pdf:
                pdf_pages[doc] = len(pdf)
    require(set(pdf_pages) == {r["doc_name"] for r in identities}, "PDF documents differ from external manifest")
    evidence_pages = {(r["doc_name"], p) for r in identities for p in r["evidence_page"]}
    missing_pages = sorted((doc, p) for doc, p in evidence_pages if not 1 <= p <= pdf_pages[doc])
    require(not missing_pages and len(evidence_pages) == 837, "Missing referenced external page")
    external_ids = [{"query_id": f"sciegqa_{r['row_index']:05d}", "source_row": r["row_index"],
                     "doc_id": r["doc_name"], "category": r["category"],
                     "evidence_page_count": len(r["evidence_page"]),
                     "query_sha256": r["query_sha256"], "record_sha256": r["record_sha256"],
                     "role": "external_test"} for r in identities]
    failures = source["snappy_identity"]["failures"]
    require({r["sample_id"] for r in failures} == {85, 86, 90, 811}, "Snappy subset identity differs")
    external_manifest = {
        "schema": "route-v2-external-test-v1", "dataset": "Yuwh07/SciEGQA-Bench",
        "revision": REV, "config": "benchmark", "split": "test", "role": "external_test",
        "questions": 1623, "documents": 80, "single_page_questions": 1305,
        "two_page_questions": 318, "unique_evidence_pages": 837,
        "evidence_page_occurrences": 1941, "full_pdf_pages": screen["counts"]["external_pdf_pages"],
        "pdf_page_count_rechecked": sum(pdf_pages.values()),
        "all_referenced_pages_present": True, "missing_referenced_pages": missing_pages,
        "main_test_exclusions": [], "source_files": acquire["files"],
        "license_status": "not_declared_in_dataset_card; unresolved",
        "images_tar": {"downloaded": False, "bytes": 1127372800,
                       "sha256": "aa8f7e6f5c27fb914a2b36f6accc63fdd48f549f97c2212e03f2b6a85e67b368",
                       "url": f"https://huggingface.co/datasets/Yuwh07/SciEGQA-Bench/resolve/{REV}/Images.tar"},
        "historical_name": "BBox-DocVQA Bench; identical common question/answer/bbox fields",
        "historical_snappy_subset": {"questions": 1619, "excluded_rows": failures,
                                     "purpose": "separate historical reproduction only"},
        "test_scored": False, "evaluation_ready": False,
        "remaining": ["Clarify dataset license", "Freeze external parser/candidates and coordinate adapter",
                      "Pin common backbone/metric/failure policy for baseline comparison"],
    }
    exclusions = []
    for doc in plan["documents"]["quarantine"]:
        reason = "external_unresolved" if doc in ext_conflicts else (
            "old_test_twin_of_used_dev" if doc in proof["dev_twin_quarantine"] else "external_identity_unit_propagation")
        exclusions.append({"doc_id": doc, "reason": reason,
                           "query_ids": [r["query_id"] for r in plan["roles"]["quarantine"] if r["doc_id"] == doc]})

    result = {
        "status": "roles_verified_with_limits", "role_manifest_directory": SPLIT.as_posix(),
        "roles": proof["roles"], "external_test": {"documents": 80, "questions": 1623},
        "deterministic_split_replay": True, "manifest_hashes_valid": True,
        "external_conflicts_in_active_roles": [], "external_decisions": verify["decision_counts"],
        "internal_cross_role_page_pairs": len(crossing),
        "internal_cross_role_page_status_counts": dict(Counter(r["status"] for r in crossing)),
        "parameter_update_excluded_pages": len(blocked),
        "parameter_update_excluded_pages_by_role": dict(Counter(r["role"] for r in blocked)),
        "extra_pages_from_first_page_audit": first_page_additions,
        "unexcluded_region_units": len(missed), "local_loss_eligible_units": dict(loss_ready),
        "internal_whole_document_content_disjoint": False,
        "identity_claim": "All observed external conflicts are quarantined. Confirmed local document groups do not cross active roles. Known cross-role pages are excluded from current local loss; full documents are not content-disjoint.",
        "future_global_loss_rule": "Must consume training_page_exclusions.jsonl for every page input, negative, distillation target and precomputation fitted on source data. Page exclusion is not yet a general training-loader guarantee.",
        "limitations": screen["limitations"] + internal["limitations"],
        "license_status": external_manifest["license_status"],
        "training_ready": False, "external_evaluation_ready": False,
        "new_training_performed": False, "model_scoring_performed": False,
        "source_exposure": source["root_exposure"],
        "inputs_verified_sha256": before,
        "script_sha256": sha(Path(__file__)),
        "preservation_scope": "Input files unchanged during final verification; old dev/test manifests match pre-task hashes.",
    }
    for path, digest in before.items():
        require(sha(Path(path)) == digest, f"Input changed while verifying: {path}")
    result["input_hashes_unchanged"] = True
    payloads = {
        "source_audit.json": encoded(source),
        "external_manifest.json": encoded(external_manifest),
        "external_test_ids.jsonl": b"".join((json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode() for r in external_ids),
        "external_test_doc_ids.txt": ("\n".join(sorted({r["doc_id"] for r in external_ids})) + "\n").encode(),
        "snappy_legacy_1619_query_ids.txt": ("\n".join(r["query_id"] for r in external_ids if r["source_row"] not in {85, 86, 90, 811}) + "\n").encode(),
        "training_page_exclusions.jsonl": b"".join((json.dumps(r, sort_keys=True) + "\n").encode() for r in blocked),
        "quarantine_reasons.json": encoded(exclusions),
        "data_verification.json": encoded(result),
        "bbox_sciegqa_field_comparison.json": encoded(source["field_comparison"]),
        "snappy_legacy_identity_audit.json": encoded(source["snappy_identity"]),
        "external_overlap_verification.json": encoded(verify),
        "internal_page_overlap_summary.json": encoded({k: v for k, v in internal.items() if k != "page_pair_evidence"}),
    }
    payloads["checksums.json"] = encoded({name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()})
    if OUT.exists():
        require(set(p.name for p in OUT.iterdir()) == set(payloads), "Existing receipt contains a different file set")
        for name, data in payloads.items():
            require((OUT / name).read_bytes() == data, f"Receipt differs: {name}; use an explicit new version")
        mode = "verified_existing"
    else:
        staging = OUT.with_name(OUT.name + ".partial")
        staging.mkdir(parents=True, exist_ok=False)
        for name, data in payloads.items():
            (staging / name).write_bytes(data)
        staging.rename(OUT)
        mode = "created"
    print(json.dumps({"mode": mode, "output": OUT.as_posix(), **{k: result[k] for k in (
        "status", "roles", "external_test", "internal_cross_role_page_pairs",
        "parameter_update_excluded_pages", "unexcluded_region_units", "training_ready")}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
