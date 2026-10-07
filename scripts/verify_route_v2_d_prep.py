"""只读验收D缓存与EXP-015配置；不访问dev样本或执行训练。"""
import json
from pathlib import Path

import torch
import yaml

from layoutpatch.retrieval.route_v2_layout import LayoutPatchD
from layoutpatch.retrieval.route_v2_query_cache import file_sha256

REPO = Path(__file__).resolve().parents[1]


def main():
    config = yaml.safe_load((REPO / "configs/experiments/route_v2_exp2_D.yaml").read_text("utf-8"))
    baseline = json.loads((REPO / config["baseline_run"] / "config.json").read_text("utf-8"))
    for key in ("seeds", "max_epochs", "optimizer", "units_per_update", "tau", "clip_max_norm", "early_stopping",
                "shuffle", "checkpoint", "device", "dtype", "mixed_precision", "scheduler", "tf32", "deterministic_algorithms", "vram_budget_gib"):
        if config[key] != baseline[key]:
            raise ValueError(f"EXP-014 shared budget mismatch: {key}")
    root = REPO / config["node_cache_train_val"]
    if file_sha256(root / "manifest.json") != config["node_manifest_sha256"]:
        raise ValueError("node manifest mismatch")
    manifest = json.loads((root / "manifest.json").read_text("utf-8"))
    ids, totals = set(), {}
    for row in manifest["pages"]:
        if row["role"] not in ("source_train", "source_val") or file_sha256(root / row["file"]) != row["sha256"]:
            raise ValueError("node page hash or role mismatch")
        payload = torch.load(root / row["file"], weights_only=True, map_location="cpu")
        lay = payload["layout"]
        if not all(bool(torch.isfinite(t).all()) for t in lay.values()):
            raise ValueError("nonfinite node cache")
        if lay["text"].shape != (row["nodes"], 1024):
            raise ValueError("text dimension mismatch")
        if not torch.allclose(lay["W_raw"].sum(-1, keepdim=True), lay["cover_mass"]):
            raise ValueError("cover mass mismatch")
        mass = lay["cover_mass"].squeeze(-1)
        if not torch.allclose(lay["W_attn"].sum(-1), (mass > 0).float(), atol=1e-6):
            raise ValueError("attention row normalization mismatch")
        for i, node in enumerate(payload["nodes"]):
            if node["node_id"] in ids:
                raise ValueError("duplicate node ID")
            ids.add(node["node_id"])
            counter = totals.setdefault(row["role"], {"nodes": 0, "nonempty": 0})
            counter["nodes"] += 1
            counter["nonempty"] += not node["text_missing"]
            if node["text_missing"]:
                if bool(lay["text"][i].any()):
                    raise ValueError("missing text must have zero cached vector")
            elif abs(float(lay["text"][i].norm()) - 1) > 1e-4:
                raise ValueError("nonempty text normalization mismatch")
    smoke = json.loads((REPO / config["smoke_receipt"]).read_text("utf-8"))
    if not smoke["passed"] or smoke["steps"] != 200 or smoke["questions"] != 16:
        raise ValueError("D smoke gate failed")
    for count in totals.values():
        count["coverage"] = count["nonempty"] / count["nodes"]
    model_parameters = sum(p.numel() for p in LayoutPatchD().parameters())
    if model_parameters != config["trainable_parameters"]:
        raise ValueError("parameter count mismatch")
    print(json.dumps({"passed": True, "nodes": len(ids), "roles": totals, "pages": len(manifest["pages"]),
                      "trainable_parameters": model_parameters, "node_cache_bytes": sum(p.stat().st_size for p in root.iterdir()),
                      "shared_training_config_matches_EXP014": True, "formal_training_started": False,
                      "remaining": "source_dev node cache not prepared by current authorization"}, indent=2))


if __name__ == "__main__":
    main()
