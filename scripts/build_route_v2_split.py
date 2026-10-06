"""Write route-v2 data roles (data-roles-v1) from MMDocIR evaluation and identity evidence.

Inputs (read-only): MMDocIR annotations (only doc names, domains and question order),
legacy dev/test ID manifests, the pinned external acquisition receipt, external identity
screening/verification and the internal identity report. No question text, answer or
gold box is written. Output: experiments/route_v2_splits/data-roles-v1/ (never replaced).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from layoutpatch.datasets.route_v2_split import build_route_v2_plan, write_route_v2_plan

REPO = Path(__file__).resolve().parents[1]
ANN = REPO / "data/raw/mmdocir_evaluation/MMDocIR_annotations.jsonl"
LEGACY_DEV = REPO / "experiments/s2_splits/dev_eval_ids.jsonl"
LEGACY_TEST = REPO / "experiments/s2_splits/test_eval_ids.jsonl"
EXT_REV = "9bdca77be633cc3259d7e3739d35b38ab00bf5d9"
ACQUISITION = REPO / "data/raw/sciegqa_bench" / EXT_REV / "acquisition.json"
SCREEN = REPO / "artifacts/route_v2_data/identity_v1/overlap_report.json"
VERIFY = REPO / "artifacts/route_v2_data/verification_v1/verification_report.json"
INTERNAL = REPO / "artifacts/route_v2_data/internal_identity_v1.json"
OUT = REPO / "experiments/route_v2_splits/data-roles-v1"
SEED = 42
TRAIN_RATIO = 0.8
POLICY = {
    "version": "data-roles-v1",
    "external_quarantine": "verification decisions unresolved or confirmed; screening-only "
    "candidates rejected by content verification are not quarantined",
    "identity_units": "internal confirmed_doc_groups (>=2 distinct matching pages each side), "
    "merged transitively; atomic in assignment",
    "dev_priority": "unit touching old dev keeps dev documents and quarantines old-test members",
    "page_level": "internal unknown/confirmed page pairs across roles are excluded per unit by "
    "build_route_v2_regions.py, not by quarantining documents",
}


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"Refusing to overwrite {OUT}")
    rows = [
        (index, json.loads(line))
        for index, line in enumerate(ANN.read_text(encoding="utf-8").split("\n"))
        if line.strip()
    ]
    screen = json.loads(SCREEN.read_text(encoding="utf-8"))
    verify = json.loads(VERIFY.read_text(encoding="utf-8"))
    internal = json.loads(INTERNAL.read_text(encoding="utf-8"))
    if verify["status"] != "verification_complete_pending_split_audit":
        raise SystemExit(f"external verification not complete: {verify['status']}")
    decisions = verify["candidate_decisions"]
    unresolved = {d["local_doc"] for d in decisions if d["decision"] != "rejected_template"}
    quarantine = sorted(unresolved | set(verify["quarantine_from_this_verification"]))
    others = {m.get("local_doc") for m in verify["other_identity_matches"]} - {None}
    if others - set(quarantine):
        raise SystemExit(f"unhandled identity matches: {sorted(others - set(quarantine))}")
    overlap = {
        "status": "passed",
        "basis": "screening + content verification complete; every unresolved or confirmed "
        "external candidate quarantined; internal confirmed groups isolated as identity units",
        "claim": "no confirmed or unresolved overlap remains in roles under identity-v1 / "
        "verification-v1 thresholds; this is not a proof of zero leakage",
        "external_candidates": len(decisions),
        "external_decisions": verify["decision_counts"],
        "limitations": screen["limitations"] + verify["limitations"] + internal["limitations"],
    }
    provenance = {
        "inputs": {p.relative_to(REPO).as_posix(): sha(p) for p in (
            ANN, LEGACY_DEV, LEGACY_TEST, ACQUISITION, SCREEN, VERIFY, INTERNAL)},
        "script_sha256": sha(Path(__file__)),
        "policy": POLICY,
    }
    plan = build_route_v2_plan(
        rows,
        jsonl(LEGACY_DEV),
        jsonl(LEGACY_TEST),
        external_manifest=json.loads(ACQUISITION.read_text(encoding="utf-8")),
        provenance=provenance,
        overlap_report=overlap,
        quarantined_docs=quarantine,
        identity_units=internal["confirmed_doc_groups"],
        seed=SEED,
        train_ratio=TRAIN_RATIO,
    )
    proof = write_route_v2_plan(plan, OUT)
    with (OUT / "identity_inputs.json").open("x", encoding="utf-8") as handle:
        json.dump({"overlap_report": overlap, "provenance": provenance}, handle, indent=2)
    print(json.dumps({
        "status": proof["status"], "roles": proof["roles"],
        "external_quarantine": proof["external_quarantine"],
        "dev_twin_quarantine": proof["dev_twin_quarantine"],
        "identity_units_crossing_roles": proof["identity_units_crossing_roles"],
        "pairwise_document_intersections_empty": all(
            not v for v in proof["pairwise_document_intersections"].values()),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
