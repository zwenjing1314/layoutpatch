"""固定16题/19unit的D技术验收；无val/dev评分，无正式训练。"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

import polars as pl  # noqa: E402
import torch  # noqa: E402
from torch.nn.functional import normalize  # noqa: E402

from layoutpatch.evaluation.localization import (  # noqa: E402
    question_macro,
    rank_candidates,
    unit_metrics,
)
from layoutpatch.retrieval.colpali import _source_signature  # noqa: E402
from layoutpatch.retrieval.colpali_layout import split_page_embedding  # noqa: E402
from layoutpatch.retrieval.route_v2_exp1 import finite, memory_guard  # noqa: E402
from layoutpatch.retrieval.route_v2_layout import LayoutPatchD  # noqa: E402
from layoutpatch.retrieval.route_v2_query_cache import file_sha256  # noqa: E402
from layoutpatch.retrieval.route_v2_scoring import (  # noqa: E402
    local_contrastive_loss,
    patch_iou_matrix,
    patch_scores,
    region_scores,
    separation,
)

REPO = Path(__file__).resolve().parents[1]
NODES = REPO / "artifacts/route_v2_data/d_nodes_v1"
REGIONS = REPO / "artifacts/route_v2_data/regions_v1"
OLD = REPO / "artifacts/route_v2_smoke/20261006_153418"


def write(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)


def load_items():
    preconditions = json.loads((OLD / "preconditions.json").read_text("utf-8"))
    chosen = next(r["detail"] for r in preconditions["preconditions"] if r["check"] == "fixed_questions")
    old_result = json.loads((OLD / "smoke_result.json").read_text("utf-8"))
    if len(chosen) != 16:
        raise ValueError("fixed smoke question count mismatch")
    units = pl.scan_parquet(REGIONS / "units.parquet").filter(
        (pl.col("role") == "source_train") & pl.col("query_id").is_in(chosen) &
        pl.col("local_loss_ready") & ~pl.col("page_overlap_excluded")).collect().to_dicts()
    if [u["unit_id"] for u in units] != old_result["unit_ids"]:
        raise ValueError("fixed smoke units mismatch")
    cache = REPO / "artifacts/route_v2_data/query_cache_v1/source_queries.pt"
    receipt = json.loads((REPO / "artifacts/route_v2_data/query_cache_v1/runs/20261006_153320_261096/run_info.json").read_text("utf-8"))
    if file_sha256(cache) != receipt["cache_sha256"]:
        raise ValueError("query cache hash mismatch")
    queries = torch.load(cache, map_location="cpu", weights_only=True)["embeddings"]
    manifest = json.loads((NODES / "manifest.json").read_text("utf-8"))
    for path, digest in manifest["audit"]["input_sha256"].items():
        if file_sha256(REPO / path) != digest:
            raise ValueError(f"node input hash mismatch: {path}")
    node_of = {(r["doc_id"], r["page"]): r for r in manifest["pages"]}
    pages = {r["page_id"]: Path(r["page_image_path"]) for r in pl.read_parquet(
        REPO / "data/processed/mmdocir_evaluation/pages.parquet", columns=["page_id", "page_image_path"]).to_dicts()}
    candidates = pl.scan_parquet(REGIONS / "candidates.parquet").filter(
        pl.col("doc_id").is_in(sorted({u["doc_id"] for u in units}))).collect().to_dicts()
    items = []
    for u in units:
        p = REPO / f"artifacts/colpali/mmdocir_evaluation/vidore_colpali/{u['page_cache_id']}.pt"
        payload = torch.load(p, map_location="cpu", weights_only=True)
        if payload["model_name"] != "vidore/colpali" or payload["source_signature"] != _source_signature(pages[u["page_cache_id"]], "vidore/colpali"):
            raise ValueError("page signature mismatch")
        page = payload["embedding"].float().to("cuda:0")
        finite(page, "page input")
        row = node_of[u["doc_id"], u["page"]]
        if file_sha256(NODES / row["file"]) != row["sha256"] or row["role"] != "source_train":
            raise ValueError("node cache signature/role mismatch")
        nodes = torch.load(NODES / row["file"], map_location="cpu", weights_only=True)
        layout = {k: v.to("cuda:0") for k, v in nodes["layout"].items()}
        cs = sorted([c for c in candidates if (c["doc_id"], c["page"]) == (u["doc_id"], u["page"])], key=lambda c: c["layout_id"])
        if [c["layout_id"] for c in cs] != [n["layout_id"] for n in nodes["nodes"]]:
            raise ValueError("candidate/node ID mismatch")
        pos = torch.zeros(1024, dtype=torch.bool, device="cuda:0")
        ignore = pos.clone()
        pos[u["patch_pos_idx"]] = True
        ignore[u["patch_ignore_idx"]] = True
        items.append({"unit": u, "page": page, "query": queries[u["query_id"]].float().to("cuda:0"),
                      "patches": split_page_embedding(page)[0], "layout": layout, "pos": pos, "neg": ~(pos | ignore),
                      "candidates": cs, "iou": patch_iou_matrix([c["bbox"] for c in cs], u["page_size"]).to("cuda:0")})
    return items, chosen, file_sha256(NODES / "manifest.json")


def main():
    out = REPO / "artifacts/route_v2_d_smoke" / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    report = {"status": "started", "seed": 42, "steps": 200, "optimizer": "AdamW", "lr": .001,
              "weight_decay": .01, "device": "cuda:0", "train_only": True}
    started = time.perf_counter()
    try:
        torch.manual_seed(42)
        torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.cuda.reset_peak_memory_stats()
        items, chosen, digest = load_items()
        module = LayoutPatchD().to("cuda:0")
        initial_params = {k: v.detach().clone() for k, v in module.named_parameters()}
        optimizer = torch.optim.AdamW(module.parameters(), lr=.001, weight_decay=.01)
        report.update({"questions": len(chosen), "query_ids": chosen, "units": len(items),
                       "node_manifest_sha256": digest, "parameters": sum(p.numel() for p in module.parameters()),
                       "node_parameters": sum(p.numel() for p in module.nodes.parameters()),
                       "fusion_parameters": sum(p.numel() for p in module.fusion.parameters())})
        gate_values = []
        hook = module.fusion.gate.register_forward_hook(lambda _m, _a, output: gate_values.append(torch.sigmoid(output.detach())))

        def diagnostics():
            gate_values.clear()
            losses, gaps, hit_rows, amplitudes = [], [], [], []
            with torch.no_grad():
                for item in items:
                    updated_page = module.forward_page(item["page"], item["layout"])
                    if not torch.equal(updated_page[1024:], item["page"][1024:]):
                        raise ValueError("prompt tokens changed")
                    updated = updated_page[:1024]
                    empty = item["layout"]["cover_mass"].squeeze(-1) == 0
                    if not torch.equal(updated[empty], item["patches"][empty]):
                        raise ValueError("empty patches changed")
                    s = patch_scores(item["query"], updated)
                    finite(s, "diagnostic scores")
                    losses.append(float(local_contrastive_loss(s, item["pos"], item["neg"])))
                    gaps.append(separation(s, item["pos"], item["neg"]))
                    amplitudes.append((normalize(updated, dim=-1) - normalize(item["patches"], dim=-1)).norm(dim=-1))
                    score = region_scores(s, item["iou"])
                    finite(score, "region scores")
                    cs = item["candidates"]
                    order = rank_candidates(score.tolist(), [c["layout_id"] for c in cs])
                    metric = unit_metrics([cs[i]["bbox"] for i in order], item["unit"]["gold_boxes"], item["unit"]["page_size"])
                    hit_rows.append({"query_id": item["unit"]["query_id"], **metric})
            gates, residual = torch.cat([g.flatten() for g in gate_values]), torch.cat(amplitudes)
            return {"loss": sum(losses) / len(losses), **{k: sum(g[k] for g in gaps) / len(gaps) for k in gaps[0]},
                    "gate_mean": float(gates.mean()), "gate_min": float(gates.min()), "gate_max": float(gates.max()),
                    "normalized_patch_change_mean": float(residual.mean()), "normalized_patch_change_max": float(residual.max()),
                    "train_metrics_question_macro": {k: sum(question_macro(hit_rows, k).values()) / len(chosen)
                                                     for k in ("hit1@0.5", "cov@1", "cov@5", "gold_recall@5@0.5")}}

        with torch.no_grad():
            for item in items:
                b = region_scores(patch_scores(item["query"], item["patches"]), item["iou"])
                d = region_scores(patch_scores(item["query"], module(item["patches"], item["layout"])), item["iou"])
                if not torch.allclose(b, d, atol=1e-6, rtol=0):
                    raise ValueError("initial D/B score mismatch")
        report["initial"] = diagnostics()
        gradient_first, gradient_later_max, logs = {}, {}, []
        train_start = time.perf_counter()
        for step in range(200):
            gate_values.clear()
            optimizer.zero_grad(set_to_none=True)
            total = 0.0
            for item in items:
                updated = module(item["patches"], item["layout"])
                s = patch_scores(item["query"], updated)
                finite(s, "training scores")
                loss = local_contrastive_loss(s, item["pos"], item["neg"])
                finite(loss, "loss")
                (loss / len(items)).backward()
                total += float(loss.detach()) / len(items)
                memory_guard("cuda:0", 12)
            grads = {}
            for k, p in module.named_parameters():
                if p.grad is not None:
                    finite(p.grad, f"gradient {k}")
                    grads[k] = float(p.grad.norm())
            if step == 0:
                gradient_first = grads
            else:
                for k, value in grads.items():
                    gradient_later_max[k] = max(value, gradient_later_max.get(k, 0))
            norm = sum(v * v for v in grads.values()) ** .5
            if not norm > 0:
                raise ValueError("zero total gradient")
            optimizer.step()
            for p in module.parameters():
                finite(p, "updated parameter")
            for state in optimizer.state.values():
                for value in state.values():
                    if isinstance(value, torch.Tensor):
                        finite(value, "optimizer state")
            memory_guard("cuda:0", 12)
            if step % 10 == 0 or step == 199:
                log = {"step": step, "loss": total, "gradient_norm": norm}
                logs.append(log)
                print(json.dumps(log), flush=True)
                with (out / "steps.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps(log) + "\n")
        torch.cuda.synchronize()
        report["training_seconds"] = time.perf_counter() - train_start
        report["final"] = diagnostics()
        hook.remove()
        report["gradient_first"] = gradient_first
        report["gradient_later_max"] = gradient_later_max
        report["parameter_delta_l2"] = {k: float((p.detach() - initial_params[k]).norm()) for k, p in module.named_parameters()}
        required = ["nodes.text_proj.weight", "nodes.coord_proj.weight", "nodes.type_emb.weight", "nodes.fuse.weight",
                    "fusion.value.weight", "fusion.gate.weight", "fusion.residual.1.weight", "fusion.residual.3.weight"]
        report["checks"] = {"loss_decreased": report["final"]["loss"] < report["initial"]["loss"],
                            "upstream_later_signal": all(gradient_later_max[k] > 0 for k in required),
                            "parameters_changed": all(report["parameter_delta_l2"][k] > 0 for k in required),
                            "initial_D_equals_B": True, "prompt_unchanged": True, "empty_patch_unchanged": True,
                            "numerically_finite": True}
        report["passed"] = all(report["checks"].values())
        report["status"] = "completed" if report["passed"] else "acceptance_failed"
        report["peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
        report["peak_reserved_bytes"] = torch.cuda.max_memory_reserved()
        torch.save(module.state_dict(), out / "D_smoke.pt")
        report["note"] = "仅固定训练样本技术验收；不证明泛化或创新；禁止作为正式D初始化"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["elapsed_seconds"] = time.perf_counter() - started
        write(out / "metrics.json", report)
        print(json.dumps({"run_dir": str(out), **report}), flush=True)
    if not report["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
