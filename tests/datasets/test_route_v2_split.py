"""Synthetic checks for exact source identity and leak-free data-role manifests."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from layoutpatch.datasets.route_v2_split import build_route_v2_plan, write_route_v2_plan


def inputs():
    annotations = []
    dev = []
    test = []
    for index in range(8):
        doc = f"article.{index}.v2.pdf"
        questions = [
            {"question": "DO NOT EXPORT", "answer": "SECRET", "layout_mapping": [[1, 2, 3]]},
            {"question": "DO NOT EXPORT", "answer": "SECRET", "layout_mapping": []},
        ]
        # Physical lines may have gaps; question IDs must not have gaps.
        annotations.append((index * 2, {"doc_name": doc, "questions": questions, "domain": "paper"}))
        for question_index in range(2):
            (dev if index < 2 else test).append(
                {
                    "annotation_line": index * 2,
                    "question_index": question_index,
                    "doc_name": doc[:-4],
                    "has_layout_gold": question_index == 0,
                }
            )
    return annotations, dev, test


def build(annotations=None, dev=None, test=None, **kwargs):
    defaults = inputs()
    evidence = {
        "external_manifest": {"dataset_id": "synthetic-external", "revision": "immutable"},
        "provenance": {"source_sha256": "synthetic"},
        "overlap_report": {"status": "unresolved"},
    }
    evidence.update(kwargs)
    return build_route_v2_plan(
        defaults[0] if annotations is None else annotations,
        defaults[1] if dev is None else dev,
        defaults[2] if test is None else test,
        **evidence,
    )


def test_global_ids_and_physical_source_refs_survive_quarantine():
    plan = build(quarantined_docs=["article.3.v2.pdf"])
    rows = [row for role in plan["roles"].values() for row in role]
    assert len(rows) == 16
    assert {row["query_id"] for row in rows} == {f"mmdocir_{index:05d}" for index in range(16)}
    lookup = {row["query_id"]: row for row in rows}
    assert lookup["mmdocir_00007"]["source_ref"] == {"annotation_line": 6, "question_index": 1}
    assert lookup["mmdocir_00007"]["doc_id"] == "article.3.v2"
    assert lookup["mmdocir_00007"]["role"] == "quarantine"
    assert lookup["mmdocir_00008"]["doc_id"] == "article.4.v2"
    assert "SECRET" not in json.dumps(plan)
    assert "DO NOT EXPORT" not in json.dumps(plan)
    assert "layout_mapping" not in json.dumps(plan)


def test_seed_reproducible_source_order_independent_and_inputs_unchanged():
    annotations, dev, test = inputs()
    before = copy.deepcopy((annotations, dev, test))
    first = build(annotations, dev, test)
    second = build(list(reversed(annotations)), list(reversed(dev)), list(reversed(test)))
    assert first == second
    assert (annotations, dev, test) == before
    assert first["summary"]["roles"]["source_train"]["documents"] == 4
    assert first["summary"]["roles"]["source_val"]["documents"] == 2
    assert first["documents"]["source_dev"] == ["article.0.v2", "article.1.v2"]
    assert all(not overlap for overlap in first["summary"]["pairwise_document_intersections"].values())
    query_sets = [set(row["query_id"] for row in rows) for rows in first["roles"].values()]
    assert sum(map(len, query_sets)) == len(set.union(*query_sets))


def test_legacy_document_identity_must_match_exactly():
    annotations, dev, test = inputs()
    dev[0]["doc_name"] = "article"
    with pytest.raises(ValueError, match="doc_name disagrees"):
        build(annotations, dev, test)


def test_question_id_is_validated_when_legacy_provides_it():
    annotations, dev, test = inputs()
    dev[0]["query_id"] = "mmdocir_99999"
    with pytest.raises(ValueError, match="query_id disagrees"):
        build(annotations, dev, test)


def test_document_cannot_cross_legacy_pools():
    annotations, dev, test = inputs()
    test.append(dev.pop())
    with pytest.raises(ValueError, match="crosses legacy pools"):
        build(annotations, dev, test)


def test_duplicate_and_missing_legacy_rows_are_rejected():
    annotations, dev, test = inputs()
    with pytest.raises(ValueError, match="Duplicate legacy"):
        build(annotations, dev + [dev[0]], test)
    with pytest.raises(ValueError, match="do not cover"):
        build(annotations, dev[1:], test)


def test_unknown_quarantine_rejected_and_valid_exclusions_complete():
    with pytest.raises(ValueError, match="Quarantine contains"):
        build(quarantined_docs=["not-in-source"])
    plan = build(quarantined_docs=["article.0.v2", "article.4.v2"])
    assert plan["documents"]["quarantine"] == ["article.0.v2", "article.4.v2"]
    assert sum(len(rows) for rows in plan["roles"].values()) == 16
    assert plan["summary"]["roles"]["source_train"]["documents"] == 4
    assert plan["summary"]["roles"]["source_val"]["documents"] == 1


def test_cross_pool_duplicate_groups_quarantined_without_merging_ids():
    plan = build(near_duplicate_groups=[["article.0.v2", "article.3.v2"]])
    assert {"article.0.v2", "article.3.v2"}.issubset(plan["documents"]["quarantine"])
    assert plan["summary"]["cross_role_groups_quarantined"]
    assert sum(len(rows) for rows in plan["roles"].values()) == 16


def test_identity_pass_never_authorizes_training_and_license_not_inferred():
    provisional = build()
    assert provisional["summary"]["status"] == "provisional"
    assert provisional["summary"]["data_identity_ready"] is False
    checked = build(overlap_report={"status": "passed"})
    assert checked["summary"]["data_identity_ready"] is True
    assert checked["summary"]["training_ready"] is False
    assert checked["summary"]["evidence"]["license_status"] == "unconfirmed"


def test_writes_hashes_only_new_directory_and_preserves_sources(tmp_path):
    annotations, dev, test = inputs()
    source = tmp_path / "source.json"
    source.write_text(json.dumps([annotations, dev, test]), encoding="utf-8")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    plan = build(annotations, dev, test)
    output = tmp_path / "new_roles"
    proof = write_route_v2_plan(plan, output)
    for filename, digest in proof["file_sha256"].items():
        assert hashlib.sha256((output / filename).read_bytes()).hexdigest() == digest
    assert json.loads((output / "split_proof.json").read_text(encoding="utf-8")) == proof
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    with pytest.raises(FileExistsError):
        write_route_v2_plan(plan, output)
    assert before == {path.name: path.read_bytes() for path in output.iterdir()}
    with pytest.raises(FileExistsError):
        write_route_v2_plan(plan, source)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash


def role_of(plan, doc):
    return next(role for role, docs in plan["documents"].items() if doc in docs)


def test_identity_unit_touching_dev_keeps_dev_and_quarantines_test_twin():
    plan = build(identity_units=[["article.0.v2", "article.5.v2.pdf"]])
    assert role_of(plan, "article.0.v2") == "source_dev"
    assert role_of(plan, "article.5.v2") == "quarantine"
    assert plan["summary"]["dev_twin_quarantine"] == ["article.5.v2"]
    assert plan["summary"]["identity_units_crossing_roles"] == []
    assert sum(len(rows) for rows in plan["roles"].values()) == 16


def test_identity_units_never_split_between_train_and_val():
    units = [["article.2.v2", "article.3.v2"], ["article.4.v2", "article.6.v2"]]
    for seed in range(12):
        plan = build(identity_units=units, seed=seed)
        for unit in units:
            assert len({role_of(plan, doc) for doc in unit}) == 1
        assert plan["summary"]["identity_units_crossing_roles"] == []
        assert plan["documents"]["source_val"]


def test_external_quarantine_propagates_through_identity_unit():
    plan = build(quarantined_docs=["article.2.v2"], identity_units=[["article.2.v2", "article.7.v2"]])
    assert role_of(plan, "article.7.v2") == "quarantine"
    assert plan["summary"]["external_quarantine"] == ["article.2.v2"]
    assert plan["summary"]["dev_twin_quarantine"] == []


def test_identity_unit_with_unknown_document_rejected():
    with pytest.raises(ValueError, match="Identity units need"):
        build(identity_units=[["article.2.v2", "missing-doc"]])


def test_too_few_documents_rejected():
    with pytest.raises(ValueError, match="At least two"):
        build(quarantined_docs=[f"article.{index}.v2" for index in range(2, 7)])
