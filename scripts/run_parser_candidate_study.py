# ruff: noqa: E402
"""Frozen 40-page A/B/D-no-text scoring; source data and checkpoints read-only."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import random
import statistics
import sys
import tempfile
import time
import types
from pathlib import Path

from parser_study_support import (
    ROOT,
    checked,
    enable_geometry_only_imports,
    enable_write_broker,
    read_json,
    read_jsonl,
    sha256,
    write_bytes,
    write_json,
    write_jsonl,
)

# Process-local only: dill asks for a temp directory during torch import.
# This runner uses acknowledged writes; it does not change system TEMP or ACLs.
tempfile.tempdir = str(ROOT / "runs/parser_candidate_comparison/v1")
os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
enable_geometry_only_imports()
for package in ("layoutpatch.retrieval", "layoutpatch.retrieval.fusion"):
    namespace = types.ModuleType(package)
    namespace.__path__ = [str(ROOT / "src" / package.replace(".", "/"))]
    sys.modules[package] = namespace
import torch
import yaml
from audit_parser_candidates import peak_rss

from layoutpatch.datasets.parser_candidates import validate_candidates
from layoutpatch.evaluation.external_localization import gold_boxes_from_relative
from layoutpatch.evaluation.localization import (
    doc_bootstrap_diff,
    question_macro,
    rank_candidates,
    unit_metrics,
)
from layoutpatch.retrieval.route_v2_attribution import InputAblatedD
from layoutpatch.retrieval.route_v2_layout import page_layout
from layoutpatch.retrieval.route_v2_scoring import (
    area_scores,
    patch_iou_matrix,
    patch_scores,
    region_scores,
)

CONFIG = ROOT / "configs/experiments/parser_candidate_frozen_scoring_v1.yaml"
METRICS = ("hit1@0.5", "cov@5", "gold_recall@5@0.5")
CONDITIONS = ("mineru_top_v1", "mineru_top_plus_annotations_v1")
LABELS = ("A", "B", "D-no-text_seed_0", "D-no-text_seed_1", "D-no-text_seed_2")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def finite(tensor, label):
    require(bool(torch.isfinite(tensor).all()), f"nonfinite {label}")


def validate_page(payload, page_id):
    require(payload["page_id"] == page_id, "P page identity mismatch")
    require(tuple(payload["embedding"].shape) == (1031, 128), "P shape mismatch")
    finite(payload["embedding"], "P")
    return payload["embedding"][:1024].float()


def validate_queries(payload, record, selected, pad_id):
    require(
        set(payload["embeddings"]) == set(payload["tokens"]) == set(record["ids"]),
        "Q identity coverage mismatch",
    )
    require(set(selected) <= set(record["ids"]), "selected Q missing")
    for qid in selected:
        q, token = payload["embeddings"][qid], payload["tokens"][qid]
        require(
            q.ndim == 2 and q.shape[1] == 128 and token["shape"] == list(q.shape),
            "Q shape mismatch",
        )
        require(token["attention_mask"] == [1] * len(q), "Q attention/padding mismatch")
        require(
            len(token["input_ids"]) == len(q) and token["input_ids"][-10:] == [pad_id] * 10,
            "Q augmentation mismatch",
        )
        finite(q, "Q")
        require(bool((q.float().norm(dim=-1) > 1e-6).all()), "unexpected zero valid Q token")


def validate_seeds(rows):
    require([r["seed"] for r in rows] == [0, 1, 2], "three original seeds required")
    require([r["selected_epoch"] for r in rows] == [1, 1, 5], "source_val epochs changed")
    require(all(r["selection_role"] == "source_val" for r in rows), "selection role changed")


def cache_identity(condition, candidate_sha, page, checkpoint_sha, code_sha):
    return dict(
        condition=condition,
        candidates_sha256=candidate_sha,
        page_id=page["page_id"],
        image_sha256=page["parser_image_sha256"],
        P_sha256=page["page_cache_sha256"],
        checkpoint_sha256=checkpoint_sha,
        code_sha256=code_sha,
    )


def check_cache(payload, expected):
    require(payload["identity"] == expected, "cross-condition or stale derived cache rejected")


def save_tensor(path, payload):
    buffer = io.BytesIO()
    torch.save(payload, buffer)
    write_bytes(path, buffer.getvalue())
    return sha256(path)


def validated_scores(values, iou):
    require(len(values) == len(iou), "score count mismatch")
    for score, zero in zip(values, (iou.sum(-1) == 0).tolist(), strict=True):
        require(
            math.isfinite(score) or (score == -math.inf and zero),
            "invalid score or -inf outside zero-IoU candidate",
        )


def prediction(unit, rows, values, iou, condition, method):
    validated_scores(values, iou)
    ids = [r["layout_id"] for r in rows]
    order = rank_candidates(values, ids)
    metrics = unit_metrics([rows[i]["bbox"] for i in order], unit["gold_boxes"], unit["page_size"])
    require(all(math.isfinite(v) for v in metrics.values()), "nonfinite metrics")
    return dict(
        condition=condition,
        method=method,
        query_id=unit["query_id"],
        doc_id=unit["doc_id"],
        page_id=unit["page_id"],
        unit_id=unit["unit_id"],
        candidate_count=len(rows),
        ranked_layout_ids=[ids[i] for i in order],
        ranked_candidate_ids=[rows[i]["candidate_id"] for i in order],
        ranked_scores=[values[i] if math.isfinite(values[i]) else None for i in order],
        zero_iou_candidates=int((iou.sum(-1) == 0).sum()),
        **metrics,
    )


def load_inputs():
    cfg = yaml.safe_load(CONFIG.read_text("utf-8-sig"))
    require(
        cfg["status"] == "frozen"
        and cfg["methods"] == ["A", "B", "D-no-text"]
        and cfg["seeds"] == [0, 1, 2],
        "scoring scope changed",
    )
    require(
        cfg["checkpoint_epochs"] == [1, 1, 5] and cfg["device"] == "cuda:0",
        "frozen execution changed",
    )
    require(
        not cfg["training"] and not cfg["new_parser_inference"] and cfg["fallback"] == "none",
        "forbidden execution",
    )
    require(
        (cfg["bootstrap_iterations"], cfg["bootstrap_seed"], cfg["family_size"]) == (2000, 0, 3),
        "statistics changed",
    )
    audit = ROOT / "runs/parser_candidate_comparison/v1/candidate_audit" / cfg["candidate_run"]
    identity = read_json(audit / "identity.json")
    acfg = identity["config"]
    checked(ROOT, identity["config_path"], identity["config_sha256"])
    for key in ("page_manifest", "unit_manifest", "protocol", "preparation_config"):
        checked(ROOT, acfg[key], acfg[key + "_sha256"])
    for path, digest in read_json(audit / "completed.json")["files_sha256"].items():
        checked(audit, path, digest)
    require(read_json(audit / "visual_review.json")["status"] == "passed", "visual review missing")
    export = read_json(checked(audit, "export_manifest.json", cfg["candidate_export_sha256"]))
    prep = yaml.safe_load((ROOT / acfg["preparation_config"]).read_text("utf-8-sig"))
    source = Path(prep["source_root_read_only"])
    pages = read_jsonl(ROOT / acfg["page_manifest"])
    units = read_jsonl(ROOT / acfg["unit_manifest"])
    require(
        (
            len(pages),
            len(units),
            len({u["query_id"] for u in units}),
            sum(len(u["gold_boxes"]) for u in units),
            len({p["doc_id"] for p in pages}),
        )
        == (40, 126, 125, 159, 35),
        "fixed denominator mismatch",
    )
    require(
        len({p["page_id"] for p in pages}) == 40 and len({u["unit_id"] for u in units}) == 126,
        "duplicate fixed identities",
    )
    candidates = {}
    for condition in CONDITIONS:
        record = export["outputs"][condition]
        rows = read_jsonl(checked(ROOT, record["path"], record["sha256"]))
        require(len(rows) == record["count"], "candidate count mismatch")
        grouped = {p["page_id"]: [] for p in pages}
        for row in rows:
            require(row["condition_id"] == condition, "candidate condition mismatch")
            grouped[row["page_id"]].append(row)
        for page in pages:
            group = grouped[page["page_id"]]
            group.sort(key=lambda r: r["layout_id"])
            validate_candidates(group, page["page_id"], page["evaluation_page_size"])
        candidates[condition] = grouped
    paths = prep["paths"]
    manifest_path = checked(
        source, paths["source_encoding_manifest"], paths["source_encoding_manifest_sha256"]
    )
    manifest = read_json(manifest_path)
    encoding_cfg = yaml.safe_load(
        (source / "configs/tools/route_v2_external_encoding_v1.yaml").read_text("utf-8")
    )
    require(
        manifest["config"] == encoding_cfg
        and manifest["schema"] == "route-v2-external-encoding-v1",
        "P/Q processing config mismatch",
    )
    info = read_json(source / manifest["run_info"])
    require(
        info["status"] == "ready"
        and info["manifest_sha256"] == sha256(manifest_path)
        and info["model_identities"] == manifest["model_identities"],
        "P/Q run identity mismatch",
    )
    annotations = checked(source, paths["source_annotations"], paths["source_annotations_sha256"])
    original = read_jsonl(annotations)
    for unit in units:
        row = original[int(unit["query_id"].split("_")[-1])]
        require(
            row["doc_name"].removesuffix(".pdf") == unit["doc_id"], "Q document identity mismatch"
        )
        indices = [
            i
            for i, p in enumerate(row["evidence_page"])
            if f"{unit['doc_id']}_p{p - 1}" == unit["page_id"]
        ]
        require(len(indices) == 1, "Q page mapping mismatch")
        w, h = unit["page_size"]
        gold = gold_boxes_from_relative(row["rel_bbox"][indices[0]], [w, h])
        require(gold == unit["gold_boxes"], "fixed gold mismatch")
    records = {r["page_id"]: r for r in manifest["pages"]}
    patches = {}
    for page in pages:
        record = records[page["page_id"]]
        require(
            record["sha256"] == page["page_cache_sha256"]
            and record["image_sha256"] == page["parser_image_sha256"],
            "P/image identity mismatch",
        )
        path = checked(manifest_path.parent, record["file"], record["sha256"])
        require(path == Path(page["page_cache_path"]).resolve(), "P path mismatch")
        checked(source, record["image_path"], record["image_sha256"])
        patches[page["page_id"]] = validate_page(
            torch.load(path, weights_only=True, map_location="cpu"), page["page_id"]
        )
    qr = manifest["queries"]
    query_path = checked(manifest_path.parent, qr["file"], qr["sha256"])
    qpayload = torch.load(query_path, weights_only=True, map_location="cpu")
    selected = {u["query_id"] for u in units}
    validate_queries(
        qpayload, qr, selected, manifest["model_identities"]["colpali"]["resolved"]["pad_token_id"]
    )
    wm = read_json(
        checked(source, paths["source_weights_manifest"], paths["source_weights_manifest_sha256"])
    )["D-no-text"]
    checked(source, wm["config"], wm["config_sha256"])
    selection = read_json(
        checked(source, wm["run"] + "/checkpoint_selection.json", wm["selection_sha256"])
    )["D-no-text"]
    validate_seeds(wm["weights"])
    models = {}
    for weight in wm["weights"]:
        path = checked(source, weight["checkpoint"], weight["sha256"])
        payload = torch.load(path, weights_only=True, map_location="cpu")
        chosen = selection[str(weight["seed"])]
        require(
            set(payload) == {"seed", "epoch", "val_score", "state_dict"},
            "checkpoint fields mismatch",
        )
        require(
            payload["seed"] == weight["seed"] == chosen["seed"]
            and payload["epoch"] == weight["selected_epoch"] == chosen["best_epoch"],
            "checkpoint selection mismatch",
        )
        require(
            payload["val_score"] == chosen["best_val"]
            and math.isfinite(payload["val_score"])
            and chosen["checkpoint_sha256"] == weight["sha256"]
            and path.name == chosen["checkpoint"],
            "source_val identity mismatch",
        )
        model = InputAblatedD("text")
        model.load_state_dict(payload["state_dict"], strict=True)
        model.eval().requires_grad_(False)
        for parameter in model.parameters():
            finite(parameter, "checkpoint")
        models[weight["seed"]] = model
    bindings = dict(
        encoding_manifest_sha256=sha256(manifest_path),
        queries_sha256=qr["sha256"],
        annotations_sha256=sha256(annotations),
        weights=wm,
        candidate_outputs=export["outputs"],
        page_manifest_sha256=acfg["page_manifest_sha256"],
        unit_manifest_sha256=acfg["unit_manifest_sha256"],
        protocol_sha256=acfg["protocol_sha256"],
        model_identities=manifest["model_identities"],
    )
    return (
        cfg,
        pages,
        units,
        candidates,
        patches,
        {q: qpayload["embeddings"][q].float() for q in selected},
        models,
        bindings,
    )


def analyze(predictions, units, pages):
    summary, questions = {}, []
    maps = {}
    for condition in CONDITIONS:
        summary[condition] = {}
        for label in LABELS:
            rows = [p for p in predictions if p["condition"] == condition and p["method"] == label]
            require(
                {r["unit_id"] for r in rows} == {u["unit_id"] for u in units}
                and len(rows) == len(units),
                "prediction denominator mismatch",
            )
            qmap = {m: question_macro(rows, m) for m in METRICS}
            maps[condition, label] = qmap
            summary[condition][label] = {m: statistics.mean(qmap[m].values()) for m in METRICS}
            for q in sorted(qmap[METRICS[0]]):
                questions.append(
                    dict(
                        condition=condition,
                        method=label,
                        query_id=q,
                        **{m: qmap[m][q] for m in METRICS},
                    )
                )
        maps[condition, "D-no-text"] = {
            m: {
                q: statistics.mean(maps[condition, f"D-no-text_seed_{s}"][m][q] for s in range(3))
                for q in qmap[m]
            }
            for m in METRICS
        }
        summary[condition]["D-no-text"] = {
            m: dict(
                mean=statistics.mean(
                    summary[condition][f"D-no-text_seed_{s}"][m] for s in range(3)
                ),
                std_ddof1=statistics.stdev(
                    summary[condition][f"D-no-text_seed_{s}"][m] for s in range(3)
                ),
            )
            for m in METRICS
        }
    doc_of = {u["query_id"]: u["doc_id"] for u in units}
    paired, transitions = {}, []
    for label in ("A", "B", "D-no-text"):
        paired[label] = {}
        for metric in METRICS:
            old, new = (maps[c, label][metric] for c in CONDITIONS)
            stats = doc_bootstrap_diff(new, old, doc_of, iterations=2000, seed=0)
            diffs = {q: new[q] - old[q] for q in sorted(old)}
            stats.update(
                improved=sum(d > 0 for d in diffs.values()),
                worsened=sum(d < 0 for d in diffs.values()),
                unchanged=sum(d == 0 for d in diffs.values()),
            )
            if metric == "hit1@0.5":
                by_doc = {}
                for q in sorted(diffs):
                    by_doc.setdefault(doc_of[q], []).append(diffs[q])
                docs = sorted(by_doc)
                rng = random.Random(0)
                samples = []
                for _ in range(2000):
                    ds = [d for doc in (rng.choice(docs) for _ in docs) for d in by_doc[doc]]
                    samples.append(sum(ds) / len(ds))
                samples.sort()
                require(
                    samples[50] == stats["ci95_low"] and samples[1950] == stats["ci95_high"],
                    "bootstrap mismatch",
                )
                tail = 0.05 / (2 * 3)
                stats.update(
                    bonferroni_ci_low=samples[int(tail * 2000)],
                    bonferroni_ci_high=samples[int((1 - tail) * 2000)],
                    family_size=3,
                    confidence=1 - 0.05 / 3,
                )
            paired[label][metric] = stats
            transitions.extend(
                dict(
                    method=label,
                    metric=metric,
                    query_id=q,
                    doc_id=doc_of[q],
                    old=old[q],
                    new=new[q],
                    delta=diffs[q],
                )
                for q in sorted(diffs)
            )
    strata = {}
    for stratum in sorted({p["stratum"] for p in pages}):
        ids = {p["page_id"] for p in pages if p["stratum"] == stratum}
        strata[stratum] = {
            c: {
                label: {
                    m: statistics.mean(
                        question_macro(
                            [
                                p
                                for p in predictions
                                if p["condition"] == c
                                and p["method"] == label
                                and p["page_id"] in ids
                            ],
                            m,
                        ).values()
                    )
                    for m in METRICS
                }
                for label in LABELS
            }
            for c in CONDITIONS
        }
    return (
        dict(
            denominators=dict(pages=40, documents=35, questions=125, units=126, gold_boxes=159),
            summary=summary,
            paired=paired,
            strata=strata,
        ),
        questions,
        transitions,
    )


def paired_units(predictions, units):
    indexed = {(p["condition"], p["method"], p["unit_id"]): p for p in predictions}
    result = []
    for method in ("A", "B", "D-no-text"):
        labels = [f"D-no-text_seed_{s}" for s in range(3)] if method == "D-no-text" else [method]
        for unit in units:
            for metric in METRICS:
                old, new = (
                    statistics.mean(indexed[c, label, unit["unit_id"]][metric] for label in labels)
                    for c in CONDITIONS
                )
                result.append(
                    dict(
                        method=method,
                        unit_id=unit["unit_id"],
                        query_id=unit["query_id"],
                        page_id=unit["page_id"],
                        metric=metric,
                        old=old,
                        new=new,
                        delta=new - old,
                    )
                )
    return result


def code_files():
    paths = {
        Path(__file__).resolve(),
        CONFIG,
        ROOT / "scripts/run_parser_candidate_study.ps1",
        ROOT / "tests/datasets/test_parser_candidate_scoring.py",
    }
    for module in tuple(sys.modules.values()):
        value = getattr(module, "__file__", None)
        if value:
            path = Path(value).resolve()
            if path.is_relative_to(ROOT) and path.suffix == ".py" and path.is_file():
                paths.add(path)
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(paths)}


def execute(run_id, verify=False):
    started = time.perf_counter()
    cfg, pages, units, candidates, patches, queries, models, bindings = load_inputs()
    out = ROOT / "runs/parser_candidate_comparison/v1/frozen_scoring" / run_id
    files = code_files()
    code_sha = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    if verify:
        identity = read_json(out / "identity.json")
        require(
            identity["code_sha256"] == files and identity["bindings"] == bindings,
            "run identity changed",
        )
        completed = read_json(out / "completed.json")
        for path, digest in completed["files_sha256"].items():
            checked(out, path, digest)
        predictions = read_jsonl(out / "predictions.jsonl")
        drecords = read_jsonl(out / "derived_manifest.jsonl")
        require(len(drecords) == 320, "derived page/seed denominator mismatch")
        saved_derived = {}
        for record in drecords:
            payload = torch.load(
                checked(ROOT, record["path"], record["sha256"]),
                weights_only=True,
                map_location="cpu",
            )
            check_cache(payload, record["identity"])
            key = record["identity"]
            page = next(p for p in pages if p["page_id"] == key["page_id"])
            expected = cache_identity(
                key["condition"],
                bindings["candidate_outputs"][key["condition"]]["sha256"],
                page,
                key["checkpoint_sha256"],
                code_sha,
            )
            check_cache(payload, expected)
            require(
                key["checkpoint_sha256"]
                in ["geometry"] + [w["sha256"] for w in bindings["weights"]["weights"]],
                "unknown derived checkpoint",
            )
            saved_key = (key["condition"], key["page_id"], key["checkpoint_sha256"])
            require(saved_key not in saved_derived, "duplicate derived identity")
            saved_derived[saved_key] = payload
            if key["checkpoint_sha256"] == "geometry":
                rows = candidates[key["condition"]][key["page_id"]]
                fresh = page_layout(rows, torch.zeros(len(rows), 1024))
                for name in fresh:
                    require(
                        torch.equal(fresh[name], payload["layout"][name]), "saved layout mismatch"
                    )
                fresh_iou = patch_iou_matrix(
                    [r["bbox"] for r in rows], page["evaluation_page_size"]
                )
                require(torch.equal(fresh_iou, payload["iou"]), "saved IoU mismatch")
        for p in predictions:
            unit = next(u for u in units if u["unit_id"] == p["unit_id"])
            rows = candidates[p["condition"]][p["page_id"]]
            byid = {r["layout_id"]: r for r in rows}
            require(
                len(p["ranked_layout_ids"]) == len(rows)
                and set(p["ranked_layout_ids"]) == set(byid),
                "saved rank coverage mismatch",
            )
            values = {
                lid: (-math.inf if s is None else s)
                for lid, s in zip(p["ranked_layout_ids"], p["ranked_scores"], strict=True)
            }
            iou = patch_iou_matrix([r["bbox"] for r in rows], unit["page_size"])
            expected = prediction(
                unit, rows, [values[r["layout_id"]] for r in rows], iou, p["condition"], p["method"]
            )
            require(expected == p, "saved prediction/metric mismatch")
            if p["method"] == "A":
                actual = torch.tensor(
                    area_scores([r["bbox"] for r in rows]), dtype=torch.float32
                ).tolist()
            else:
                prime = patches[p["page_id"]]
                if p["method"].startswith("D-no-text"):
                    weight = bindings["weights"]["weights"][int(p["method"][-1])]["sha256"]
                    prime = saved_derived[p["condition"], p["page_id"], weight]["P_prime"]
                with torch.inference_mode():
                    actual = (
                        region_scores(
                            patch_scores(
                                queries[unit["query_id"]].to(cfg["device"]), prime.to(cfg["device"])
                            ),
                            iou.to(cfg["device"]),
                        )
                        .cpu()
                        .tolist()
                    )
            require(
                actual == [values[r["layout_id"]] for r in rows],
                "saved candidate score does not reproduce from P/Q/P-prime",
            )
        result, questions, transitions = analyze(predictions, units, pages)
        require(
            result == read_json(out / "metrics.json")
            and questions == read_jsonl(out / "question_scores.jsonl")
            and transitions == read_jsonl(out / "paired_question_changes.jsonl"),
            "saved analytical mismatch",
        )
        require(
            paired_units(predictions, units) == read_jsonl(out / "paired_unit_changes.jsonl"),
            "unit changes mismatch",
        )
        print(
            json.dumps(
                dict(
                    stage="verify",
                    status="passed",
                    prediction_rows=len(predictions),
                    derived_files=len(drecords),
                )
            )
        )
        return
    require(not out.exists(), "run already exists: use new run ID")
    require(torch.cuda.is_available(), "CUDA unavailable; no silent CPU fallback")
    torch.manual_seed(0)
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    identity = dict(
        config=cfg,
        bindings=bindings,
        code_sha256=files,
        combined_code_sha256=code_sha,
        torch=torch.__version__,
        device=torch.cuda.get_device_name(0),
        tf32=False,
        deterministic=True,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        training=False,
        parser_inference=False,
    )
    write_json(out / "identity.json", identity)
    for path in files:
        write_bytes(out / "code" / path, (ROOT / path).read_bytes())
    predictions, derived, resources = [], [], []
    device = cfg["device"]
    torch.cuda.reset_peak_memory_stats()
    with torch.inference_mode():
        for condition in CONDITIONS:
            cand_sha = bindings["candidate_outputs"][condition]["sha256"]
            for index, page in enumerate(pages):
                page_started = time.perf_counter()
                pid = page["page_id"]
                rows = candidates[condition][pid]
                layout = page_layout(rows, torch.zeros(len(rows), 1024, dtype=torch.float32))
                require(
                    not bool(layout["text"].any()) and bool(layout["mask"].all()),
                    "zero text/mask violation",
                )
                iou = patch_iou_matrix([r["bbox"] for r in rows], page["evaluation_page_size"])
                for value in layout.values():
                    finite(value, "layout")
                finite(iou, "IoU")
                expected = cache_identity(condition, cand_sha, page, "geometry", code_sha)
                base = (
                    ROOT
                    / "artifacts/parser_candidate_comparison/v1/derived"
                    / condition
                    / cand_sha[:12]
                    / run_id
                    / pid
                )
                path = base / "layout.pt"
                digest = save_tensor(
                    path,
                    dict(
                        identity=expected,
                        layout=layout,
                        iou=iou,
                        layout_ids=[r["layout_id"] for r in rows],
                    ),
                )
                derived.append(dict(path=str(path), sha256=digest, identity=expected))
                transforms = {"B": patches[pid].to(device)}
                gpu_layout = {k: v.to(device) for k, v in layout.items()}
                for seed, model in models.items():
                    model.to(device)
                    prime = model(transforms["B"], gpu_layout) if rows else transforms["B"].clone()
                    finite(prime, "P prime")
                    label = f"D-no-text_seed_{seed}"
                    transforms[label] = prime
                    expected = cache_identity(
                        condition,
                        cand_sha,
                        page,
                        bindings["weights"]["weights"][seed]["sha256"],
                        code_sha,
                    )
                    path = base / f"P_prime_seed_{seed}.pt"
                    digest = save_tensor(path, dict(identity=expected, P_prime=prime.cpu()))
                    derived.append(dict(path=str(path), sha256=digest, identity=expected))
                for unit in (u for u in units if u["page_id"] == pid):
                    for label in LABELS:
                        if label == "A":
                            values = torch.tensor(
                                area_scores([r["bbox"] for r in rows]), dtype=torch.float32
                            ).tolist()
                        else:
                            scores = patch_scores(
                                queries[unit["query_id"]].to(device), transforms[label]
                            )
                            finite(scores, "patch scores")
                            values = region_scores(scores, iou.to(device)).cpu().tolist()
                        predictions.append(prediction(unit, rows, values, iou, condition, label))
                torch.cuda.synchronize()
                resources.append(
                    dict(
                        condition=condition, page_id=pid, seconds=time.perf_counter() - page_started
                    )
                )
                print(
                    json.dumps(
                        dict(event="progress", condition=condition, pages_done=index + 1, total=40)
                    ),
                    flush=True,
                )
    result, questions, transitions = analyze(predictions, units, pages)
    write_jsonl(out / "predictions.jsonl", predictions)
    write_jsonl(out / "derived_manifest.jsonl", derived)
    write_json(out / "metrics.json", result)
    write_jsonl(out / "question_scores.jsonl", questions)
    write_jsonl(out / "paired_question_changes.jsonl", transitions)
    write_jsonl(out / "paired_unit_changes.jsonl", paired_units(predictions, units))
    write_json(
        out / "resources.json",
        dict(
            page_timings=resources,
            total_seconds=time.perf_counter() - started,
            peak_rss_bytes=peak_rss(),
            peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(),
            peak_cuda_reserved_bytes=torch.cuda.max_memory_reserved(),
            failed_pages=[],
            scored_units_per_condition_method=126,
            zero_iou_sentinels=sum(p["zero_iou_candidates"] for p in predictions),
        ),
    )
    outputs = [
        "identity.json",
        "predictions.jsonl",
        "derived_manifest.jsonl",
        "metrics.json",
        "question_scores.jsonl",
        "paired_question_changes.jsonl",
        "paired_unit_changes.jsonl",
        "resources.json",
    ]
    write_json(
        out / "completed.json",
        dict(status="completed", files_sha256={f: sha256(out / f) for f in outputs}),
    )
    print(
        json.dumps(dict(stage="score", status="completed", run=str(out), summary=result["summary"]))
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--stage", choices=["score", "verify"], required=True)
    parser.add_argument("--write-broker", action="store_true")
    args = parser.parse_args()
    require(args.run_id.replace("_", "").replace("-", "").isalnum(), "invalid run ID")
    if args.write_broker:
        enable_write_broker()
    try:
        execute(args.run_id, args.stage == "verify")
    except Exception as exc:
        out = ROOT / "runs/parser_candidate_comparison/v1/frozen_scoring" / args.run_id
        if (
            args.stage == "score"
            and not (out / "completed.json").exists()
            and not (out / "failed.json").exists()
        ):
            write_json(
                out / "failed.json",
                dict(status="invalid", error_type=type(exc).__name__, message=str(exc)),
            )
        raise


