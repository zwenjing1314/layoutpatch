"""Deterministic, metadata-only manifests for the new MMDocIR data roles.

This module never trains or scores a model. The caller supplies annotations and
audit evidence; an evidence status is recorded, not independently certified here.
Legacy manifests and source annotations are inputs and are never modified.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROLES = ("source_train", "source_val", "source_dev", "quarantine")


def document_id(name: str) -> str:
    """Strip exactly the final PDF extension, preserving dots inside IDs."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Document names must be nonempty strings")
    return name[:-4] if name.lower().endswith(".pdf") else name


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _nonnegative_index(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def _source_records(
    annotation_rows: Iterable[tuple[int, Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    rows = list(annotation_rows)
    for line, _ in rows:
        _nonnegative_index(line, "annotation_line")
    if len({line for line, _ in rows}) != len(rows):
        raise ValueError("Duplicate annotation_line in source")
    records: list[dict[str, Any]] = []
    seen_docs: set[str] = set()
    for line, annotation in sorted(rows, key=lambda row: row[0]):
        doc = document_id(annotation["doc_name"])
        if doc in seen_docs:
            raise ValueError(f"Duplicate source document: {doc}")
        seen_docs.add(doc)
        questions = annotation["questions"]
        if not isinstance(questions, list) or not questions:
            raise ValueError(f"Source document has no question list: {doc}")
        domain = annotation.get("domain")
        if domain is not None and not isinstance(domain, str):
            raise ValueError("domain must be a string or null")
        for index, question in enumerate(questions):
            if not isinstance(question, Mapping):
                raise ValueError("Each question must be an object")
            record = {
                "query_id": f"mmdocir_{len(records):05d}",
                "doc_id": doc,
                "source_ref": {"annotation_line": line, "question_index": index},
                "has_layout_gold": bool(question.get("layout_mapping")),
            }
            if domain is not None:
                record["domain"] = domain
            records.append(record)
    if not records:
        raise ValueError("Source annotations are empty")
    return records


def _legacy_assignments(
    records: Sequence[dict[str, Any]],
    legacy_dev_ids: Iterable[Mapping[str, Any]],
    legacy_test_ids: Iterable[Mapping[str, Any]],
) -> tuple[dict[tuple[int, int], str], dict[str, str]]:
    lookup = {
        (row["source_ref"]["annotation_line"], row["source_ref"]["question_index"]): row
        for row in records
    }
    assignments: dict[tuple[int, int], str] = {}
    document_pools: dict[str, str] = {}
    for pool, legacy in (("dev_eval", legacy_dev_ids), ("test_eval", legacy_test_ids)):
        for old in legacy:
            ref = (
                _nonnegative_index(old["annotation_line"], "annotation_line"),
                _nonnegative_index(old["question_index"], "question_index"),
            )
            if ref in assignments:
                raise ValueError(f"Duplicate legacy source reference: {ref}")
            if ref not in lookup:
                raise ValueError(f"Legacy reference absent from source: {ref}")
            current = lookup[ref]
            doc = document_id(old["doc_name"])
            if doc != current["doc_id"]:
                raise ValueError(f"Legacy doc_name disagrees with source at {ref}")
            if "query_id" in old and old["query_id"] != current["query_id"]:
                raise ValueError(f"Legacy query_id disagrees with global source order at {ref}")
            if (
                "has_layout_gold" in old
                and old["has_layout_gold"] != current["has_layout_gold"]
            ):
                raise ValueError(f"Legacy has_layout_gold disagrees with source at {ref}")
            if doc in document_pools and document_pools[doc] != pool:
                raise ValueError(f"Document crosses legacy pools: {doc}")
            assignments[ref] = pool
            document_pools[doc] = pool
    missing = set(lookup) - set(assignments)
    if missing:
        raise ValueError(f"Legacy manifests do not cover {len(missing)} source questions")
    return assignments, document_pools


def _identity_components(units: Iterable[Iterable[str]], known: set[str]) -> list[list[str]]:
    """Partition of all known documents; declared identity units merge transitively."""
    parent = {doc: doc for doc in known}

    def find(doc: str) -> str:
        while parent[doc] != doc:
            parent[doc] = parent[parent[doc]]
            doc = parent[doc]
        return doc

    for unit in units:
        docs = sorted({document_id(doc) for doc in unit})
        if len(docs) < 2 or set(docs) - known:
            raise ValueError("Identity units need at least two known source documents")
        for doc in docs[1:]:
            parent[find(doc)] = find(docs[0])
    groups: dict[str, list[str]] = {}
    for doc in sorted(known):
        groups.setdefault(find(doc), []).append(doc)
    return sorted(groups.values())


def build_route_v2_plan(
    annotation_rows: Iterable[tuple[int, Mapping[str, Any]]],
    legacy_dev_ids: Iterable[Mapping[str, Any]],
    legacy_test_ids: Iterable[Mapping[str, Any]],
    *,
    external_manifest: Mapping[str, Any],
    provenance: Mapping[str, Any],
    overlap_report: Mapping[str, Any],
    quarantined_docs: Iterable[str] = (),
    identity_units: Iterable[Iterable[str]] = (),
    near_duplicate_groups: Iterable[Iterable[str]] = (),
    seed: int = 42,
    train_ratio: float = 0.8,
) -> dict[str, Any]:
    """Build roles without writing or exposing questions, answers, or gold boxes.

    ``annotation_rows`` carries the physical zero-based JSONL line index, including
    gaps from blank lines. Global query IDs enumerate all questions in that order,
    before quarantine. The entire supplied annotation source must be covered by
    the two legacy manifests. Old dev becomes ``source_dev``; old test is split by
    identity unit into ``source_train``/``source_val``. Quarantine propagates through
    identity units. A unit touching an unquarantined old-dev document keeps its dev
    documents and quarantines its old-test members, so no unit spans two roles.
    ``near_duplicate_groups`` is a stricter optional mode: a group crossing roles
    is quarantined whole.

    ``overlap_report['status'] == 'passed'`` marks caller-audited data identity
    readiness only. Training is always disabled until its separate protocol and
    implementation are frozen. Missing license information remains unconfirmed.
    """
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if not isinstance(train_ratio, (int, float)) or not 0 < train_ratio < 1:
        raise ValueError("train_ratio must lie strictly between zero and one")
    records = _source_records(annotation_rows)
    assignments, document_pools = _legacy_assignments(
        records, legacy_dev_ids, legacy_test_ids
    )
    known_docs = set(document_pools)
    quarantine = {document_id(doc) for doc in quarantined_docs}
    if quarantine - known_docs:
        raise ValueError("Quarantine contains documents absent from MMDocIR source")
    groups = [sorted({document_id(doc) for doc in group}) for group in near_duplicate_groups]
    for group in groups:
        if len(group) < 2 or set(group) - known_docs:
            raise ValueError("Near-duplicate groups need at least two known source documents")
    components = _identity_components(identity_units, known_docs)
    external_quarantine = sorted(quarantine)
    # Propagate a predeclared quarantine through identity units and strict groups.
    while True:
        expanded = set(quarantine)
        for group in [*groups, *components]:
            if quarantine.intersection(group):
                expanded.update(group)
        if expanded == quarantine:
            break
        quarantine = expanded
    dev_twins = sorted(
        doc
        for component in components
        if any(document_pools[d] == "dev_eval" and d not in quarantine for d in component)
        for doc in component
        if document_pools[doc] == "test_eval" and doc not in quarantine
    )
    quarantine.update(dev_twins)
    units = [
        [doc for doc in component if document_pools[doc] == "test_eval" and doc not in quarantine]
        for component in components
    ]
    units = sorted((unit for unit in units if unit), key=lambda unit: unit[0])
    total = sum(len(unit) for unit in units)
    if total < 2:
        raise ValueError("At least two unquarantined legacy test documents are required")
    if len(units) < 2:
        raise ValueError("At least two legacy test identity units are required")
    random.Random(seed).shuffle(units)
    cut = max(1, min(total - 1, math.floor(total * train_ratio)))
    train_docs: list[str] = []
    val_docs: list[str] = []
    for unit in units:
        (train_docs if len(train_docs) < cut else val_docs).extend(unit)
    if not val_docs:
        raise ValueError("Identity units leave no document for source_val")
    doc_roles = {doc: "source_train" for doc in train_docs}
    doc_roles.update({doc: "source_val" for doc in val_docs})
    doc_roles.update(
        {doc: "source_dev" for doc, pool in document_pools.items() if pool == "dev_eval"}
    )
    doc_roles.update({doc: "quarantine" for doc in quarantine})
    crossing_groups: list[list[str]] = []
    while True:
        changed = False
        for group in groups:
            if len({doc_roles[doc] for doc in group}) > 1:
                if group not in crossing_groups:
                    crossing_groups.append(group)
                for doc in group:
                    if doc_roles[doc] != "quarantine":
                        doc_roles[doc] = "quarantine"
                        changed = True
        if not changed:
            break
    roles: dict[str, list[dict[str, Any]]] = {name: [] for name in ROLES}
    documents = {name: sorted(doc for doc in known_docs if doc_roles[doc] == name) for name in ROLES}
    for record in records:
        source_ref = record["source_ref"]
        ref = source_ref["annotation_line"], source_ref["question_index"]
        role = doc_roles[record["doc_id"]]
        roles[role].append({**record, "legacy_pool": assignments[ref], "role": role})
    identity_passed = overlap_report.get("status") == "passed"
    evidence = {
        "external_manifest_sha256": _digest(external_manifest),
        "provenance_sha256": _digest(provenance),
        "overlap_report_sha256": _digest(overlap_report),
        "independence_status": overlap_report.get("status", "unconfirmed"),
        "license_status": external_manifest.get("license_status", "unconfirmed"),
    }
    summary = {
        "schema": "route-v2-data-roles-v1",
        "status": "assigned" if identity_passed else "provisional",
        "data_identity_ready": identity_passed,
        "training_ready": False,
        "training_blocker": "Loss, metrics, and training runner require a separate frozen protocol.",
        "identity_evidence_origin": "Caller-supplied overlap report; builder verifies local roles only.",
        "seed": seed,
        "train_document_ratio": train_ratio,
        "shuffle": "sort exact document IDs, then random.Random(seed).shuffle",
        "question_id_policy": "all source questions in physical-line order, before exclusions",
        "source_documents": len(known_docs),
        "source_questions": len(records),
        "legacy_pools": {
            pool: {
                "documents": sum(value == pool for value in document_pools.values()),
                "questions": sum(value == pool for value in assignments.values()),
            }
            for pool in ("dev_eval", "test_eval")
        },
        "roles": {
            role: {
                "documents": len(documents[role]),
                "questions": len(roles[role]),
                "with_layout_gold": sum(row["has_layout_gold"] for row in roles[role]),
            }
            for role in ROLES
        },
        "role_names": {
            "source_train": "old test_eval documents, training",
            "source_val": "old test_eval documents, early stopping and model selection",
            "source_dev": "old dev_eval documents, development benchmark (seen in old exploration)",
            "quarantine": "excluded from every role",
        },
        "assignment": "identity units atomic; dev members kept, old-test twins quarantined",
        "external_quarantine": external_quarantine,
        "dev_twin_quarantine": dev_twins,
        "identity_units": [
            {"documents": c, "roles": sorted({doc_roles[d] for d in c})}
            for c in components
            if len(c) > 1
        ],
        "identity_units_crossing_roles": [
            c for c in components if len({doc_roles[d] for d in c} - {"quarantine"}) > 1
        ],
        "near_duplicate_groups": groups,
        "cross_role_groups_quarantined": crossing_groups,
        "empty_training_role": not roles["source_train"] or not roles["source_val"],
        "pairwise_document_intersections": {
            f"{left}__{right}": sorted(set(documents[left]) & set(documents[right]))
            for index, left in enumerate(ROLES)
            for right in ROLES[index + 1 :]
        },
        "evidence": evidence,
    }
    return {"roles": roles, "documents": documents, "summary": summary}


def write_route_v2_plan(plan: Mapping[str, Any], output_dir: str | Path) -> dict[str, Any]:
    """Write only to a new directory; never replace an existing split or output.

    Hashes cover the exact emitted bytes. The proof does not hash itself. The
    caller may independently save metadata audit evidence beside these outputs.
    """
    payloads: dict[str, bytes] = {}
    for role in ROLES:
        payloads[f"{role}_ids.jsonl"] = "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in plan["roles"][role]
        ).encode("utf-8")
        payloads[f"{role}_doc_ids.txt"] = "".join(
            doc + "\n" for doc in plan["documents"][role]
        ).encode("utf-8")
        payloads[f"{role}_query_ids.txt"] = "".join(
            row["query_id"] + "\n" for row in plan["roles"][role]
        ).encode("utf-8")
    proof = {
        **plan["summary"],
        "file_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()},
    }
    payloads["split_proof.json"] = _json_bytes(proof)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=False)
    for name, data in payloads.items():
        with (target / name).open("xb") as handle:
            handle.write(data)
    return proof
