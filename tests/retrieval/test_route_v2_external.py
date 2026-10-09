"""冻结 SciEGQA 外评的合成统计、路径边界与只读入口测试。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import statistics
import sys
from pathlib import Path

import polars as pl
import pytest

from layoutpatch.evaluation.external_localization import (
    compute_analytical_results,
    joint_document_statistics,
)
from layoutpatch.evaluation.localization import question_macro, unit_metrics


def load_runner():
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_route_v2_external.py"
    spec = importlib.util.spec_from_file_location("route_v2_external_runner", script)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def frozen_config() -> dict:
    return {
        "seeds": [0, 1, 2],
        "trained_methods": ["C", "C-wide", "D", "D-no-text"],
        "statistics": {
            "primary_comparisons": ["D-no-text-A", "D-no-text-B", "D-no-text-C-wide"],
            "bootstrap": {"iterations": 2000, "seed": 0},
            "multiple_comparisons": {"family_alpha": 0.05},
        },
    }


def synthetic_units() -> list[dict]:
    return [
        {"query_id": "q1", "doc_id": "d1", "page_id": "p1", "unit_id": "q1:p1"},
        {"query_id": "q1", "doc_id": "d1", "page_id": "p2", "unit_id": "q1:p2"},
        {"query_id": "q2", "doc_id": "d2", "page_id": "p3", "unit_id": "q2:p3"},
    ]


def prediction_row(unit: dict, method: str, hit: bool) -> dict:
    multigold = unit["unit_id"] == "q1:p1"
    gold = [[0, 0, 20, 20], [80, 80, 100, 100]] if multigold else [[0, 0, 20, 20]]
    good = [0, 0, 20, 20]
    second_good = [80, 80, 100, 100]
    bad = [40, 40, 60, 60]
    if multigold:
        ranked = [good, second_good, bad] if hit else [bad, good, second_good]
        ranked_ids = [1, 3, 2] if hit else [2, 1, 3]
    else:
        ranked = [good, bad] if hit else [bad, good]
        ranked_ids = [1, 2] if hit else [2, 1]
    return {
        **unit,
        "role": "external_test",
        "method": method,
        "candidate_count": len(ranked),
        "page_overlap_excluded": False,
        "ranked_layout_ids": ranked_ids,
        "ranked_scores": [1.0, 0.5, 0.0][: len(ranked)],
        **unit_metrics(ranked, gold, [100, 100]),
    }


def synthetic_methods() -> dict[str, list[dict]]:
    units = synthetic_units()
    patterns = {
        "A": [True, False, True],
        "B": [False, False, True],
    }
    for method in ("C", "C-wide", "D", "D-no-text"):
        patterns[f"{method}_seed_0"] = [False, False, False]
        patterns[f"{method}_seed_1"] = [True, False, True]
        patterns[f"{method}_seed_2"] = [True, True, True]
    return {
        method: [prediction_row(unit, method, hit) for unit, hit in zip(units, hits, strict=True)]
        for method, hits in patterns.items()
    }


def test_multpage_multigold_question_macro_and_seed_sample_std():
    methods = synthetic_methods()
    result = compute_analytical_results(methods, synthetic_units(), frozen_config())
    a = result["methods"]["A"]["all"]
    assert question_macro(methods["A"], "hit1@0.5") == {"q1": 0.5, "q2": 1.0}
    assert a["questions"] == 2 and a["units"] == 3
    assert a["metrics"]["hit1@0.5"] == pytest.approx(0.75)
    assert methods["A"][0]["gold_recall@5@0.5"] == 1.0
    seed_values = [0.0, 0.75, 1.0]
    aggregate = result["seed_aggregates"]["D-no-text"]["all"]
    assert aggregate["metrics"]["hit1@0.5"] == pytest.approx(statistics.mean(seed_values))
    assert aggregate["std"]["hit1@0.5"] == pytest.approx(statistics.stdev(seed_values))
    assert aggregate["questions"] == 2 and aggregate["units"] == 3


def test_joint_document_bootstrap_and_three_primary_bonferroni_intervals():
    reference = {"q1": 1.0, "q2": 0.5, "q3": 0.0, "q4": 1.0}
    doc_of = {"q1": "d1", "q2": "d1", "q3": "d2", "q4": "d3"}
    comparisons = {
        "p1": {query: value - 0.2 for query, value in reference.items()},
        "p2": {query: value - (0.1 if query != "q3" else -0.1) for query, value in reference.items()},
        "p3": {query: value for query, value in reference.items()},
        "secondary": {query: value + 0.2 for query, value in reference.items()},
    }
    result = joint_document_statistics(
        reference,
        comparisons,
        doc_of,
        primary=["p1", "p2", "p3"],
    )
    by_doc = {"d1": ["q1", "q2"], "d2": ["q3"], "d3": ["q4"]}
    rng = random.Random(0)
    samples = {name: [] for name in comparisons}
    docs = sorted(by_doc)
    for _ in range(2000):
        questions = [q for doc in (rng.choice(docs) for _ in docs) for q in by_doc[doc]]
        for name, baseline in comparisons.items():
            samples[name].append(sum(reference[q] - baseline[q] for q in questions) / len(questions))
    for name in comparisons:
        values = sorted(samples[name])
        assert result[name]["ci95_low"] == values[50]
        assert result[name]["ci95_high"] == values[1950]
        if name in {"p1", "p2", "p3"}:
            assert result[name]["bonferroni_ci_low"] == values[16]
            assert result[name]["bonferroni_ci_high"] == values[1983]
        else:
            assert "bonferroni_ci_low" not in result[name]
    assert result["p1"]["documents"] == 3 and result["p1"]["queries"] == 4


def test_manifest_hash_precedes_json_parse_and_paths_reject_escape(tmp_path, monkeypatch):
    runner = load_runner()
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("not json", encoding="utf-8")
    cfg = {
        "encoding_manifest": "manifest.json",
        "encoding_manifest_sha256": runner.EXPECTED_ENCODING_MANIFEST_SHA256,
    }
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        runner.load_encoding_manifest(cfg)
    cfg["encoding_manifest_sha256"] = hashlib.sha256(b"not json").hexdigest()
    with pytest.raises(ValueError, match="hash binding changed"):
        runner.load_encoding_manifest(cfg)
    for value in ("../outside", str((tmp_path / "absolute").resolve())):
        with pytest.raises(ValueError, match="absolute|traversal"):
            runner.safe_repo_path(value, label="test")
        with pytest.raises(ValueError, match="absolute|traversal"):
            runner.safe_run_path(tmp_path, value, label="test")


def test_preflight_verify_and_reuse_branches_do_not_write(tmp_path, monkeypatch, capsys):
    runner = load_runner()
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    report = {
        "status": "ready",
        "counts": {"questions": 2},
        "input_sha256": {"manifest": "m", "weights": "w"},
        "seconds": 0.1,
    }
    cfg = {"encoding_manifest": "manifest", "weights_manifest": "weights", "output": "runs"}
    monkeypatch.setattr(runner, "preflight", lambda *_args, **_kwargs: (report, {}))
    runner.preflight_entry(cfg)
    assert list(tmp_path.rglob("*")) == []

    completed = tmp_path / "runs" / "20261009_000000"
    completed.mkdir(parents=True)
    monkeypatch.setattr(runner, "find_completed", lambda _cfg: completed)
    monkeypatch.setattr(runner, "verify_saved", lambda *_args: {"passed": True})
    monkeypatch.setattr(
        runner,
        "preflight",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("heavy preflight called")),
    )
    monkeypatch.setattr(
        runner,
        "write_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("write attempted")),
    )
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert runner.run_evaluation(cfg) == completed
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert after == before

    monkeypatch.setattr(runner, "load_config", lambda: cfg)
    monkeypatch.setattr(runner, "checked_result_run", lambda _cfg, run: run.resolve())
    monkeypatch.setattr(sys, "argv", ["run_route_v2_external.py", "verify", "--run-dir", str(completed)])
    runner.main()
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before
    assert "passed" in capsys.readouterr().out


def test_saved_prediction_verification_never_loads_tensor_caches(tmp_path, monkeypatch):
    runner = load_runner()
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    candidates = tmp_path / "candidates.jsonl"
    candidate_rows = [
        {"page_id": "doc_p0", "layout_id": 1, "bbox": [0, 0, 20, 20], "page_size": [100, 100]},
        {"page_id": "doc_p0", "layout_id": 2, "bbox": [40, 40, 60, 60], "page_size": [100, 100]},
    ]
    candidates.write_text("".join(json.dumps(row) + "\n" for row in candidate_rows), encoding="utf-8")
    annotations = tmp_path / "annotations.jsonl"
    annotation = {
        "doc_name": "doc.pdf",
        "evidence_page": [1],
        "bbox": [[[0, 0, 20, 20]]],
        "rel_bbox": [[[0, 0, 200, 200]]],
        "subimg_type": [["text"]],
    }
    annotations.write_text(json.dumps(annotation) + "\n", encoding="utf-8")
    cfg = frozen_config() | {
        "candidates": "candidates.jsonl",
        "candidates_sha256": hashlib.sha256(candidates.read_bytes()).hexdigest(),
        "annotations": "annotations.jsonl",
        "annotations_sha256": hashlib.sha256(annotations.read_bytes()).hexdigest(),
        "denominators": {"questions": 1, "unique_pages": 1, "question_page_units": 1, "candidates": 2},
    }
    unit = {
        "query_id": "sciegqa_00000",
        "doc_id": "doc",
        "page_id": "doc_p0",
        "unit_id": "sciegqa_00000:doc_p0",
    }
    labels = ["A", "B", *(f"{name}_seed_{seed}" for name in cfg["trained_methods"] for seed in cfg["seeds"])]
    methods = {
        label: [prediction_row(unit, label, True)]
        for label in labels
    }
    data = runner.SavedInputs(cfg)
    analytical = compute_analytical_results(methods, data.units, cfg)
    run = tmp_path / "result"
    run.mkdir()
    rows = [row for label in sorted(methods) for row in methods[label]]
    pl.DataFrame(rows).write_parquet(run / "predictions.parquet")
    pl.DataFrame(runner.question_rows(methods)).write_parquet(run / "question_scores.parquet")
    (run / "metrics.json").write_text(json.dumps({"analytical": analytical}), encoding="utf-8")
    monkeypatch.setattr(
        runner.torch,
        "load",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("tensor cache loaded")),
    )
    before = {path: path.stat().st_mtime_ns for path in run.iterdir()}
    verification = runner.verify_saved(run, cfg)
    after = {path: path.stat().st_mtime_ns for path in run.iterdir()}
    assert verification["passed"] and verification["model_scoring_reexecuted"] is False
    assert after == before
