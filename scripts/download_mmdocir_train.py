"""Download MMDocIR train dataset from HuggingFace (one-shot script).

Usage (project root, Windows PowerShell):
    uv run --with datasets,huggingface_hub python scripts/download_mmdocir_train.py
    uv run --with datasets,huggingface_hub python scripts/download_mmdocir_train.py --dry-run

Notes:
- Target dir: data/raw/mmdocir_train/  (kept OUT of git via .gitignore data/).
- Uses domestic mirror if available: set HF_ENDPOINT=https://hf-mirror.com
  in PowerShell:  $env:HF_ENDPOINT='https://hf-mirror.com'
- ~50GB: needs stable network + disk space; script is resumable (HF cache).
- After download, inspect file list, then wire `lp prepare --dataset mmdocir_train`
  (needs PAPER_SPEC 4.2 label-rule review first; do NOT train on evaluation gold).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

DATASET_ID = "MMDocIR/MMDocIR_Train_Dataset"
TARGET_DIR = Path("data/raw/mmdocir_train")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download MMDocIR train set.")
    p.add_argument("--dataset", default=DATASET_ID)
    p.add_argument("--target", default=str(TARGET_DIR))
    p.add_argument("--dry-run", action="store_true", help="Only print plan, no download.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    target = Path(args.target)
    endpoint = os.getenv("HF_ENDPOINT", "(default official endpoint)")
    print(f"Dataset : {args.dataset}")
    print(f"Target  : {target.resolve()}")
    print(f"HF_ENDPOINT: {endpoint}")
    print(f"Disk free : {disk_free_gb(target):.1f} GB (need ~55GB+)")
    if args.dry_run:
        print("dry-run: stop before download.")
        return
    target.mkdir(parents=True, exist_ok=True)

    # NOTE: load_dataset() fails on this repo because its JSON builder declares
    # page_id as int64, but rows contain strings like 'train_33324'
    # (pyarrow ArrowInvalid). So download raw jsonl files directly instead
    # of going through the datasets builder.
    from huggingface_hub import snapshot_download

    snap = snapshot_download(
        repo_id=args.dataset, repo_type="dataset", local_dir=str(target / "hf_hub")
    )
    print(f"Snapshot downloaded to {snap}")
    files = sorted(Path(snap).rglob("*.jsonl"))
    print(f"Found {len(files)} jsonl files:")
    for f in files:
        print(f"  {f.relative_to(snap)}  {f.stat().st_size/1e6:.2f} MB")
    if not files:
        raise SystemExit("No jsonl files found in snapshot, check repo layout.")
    print("OK: raw jsonl ready. Next: inspect schema, then write prepare adapter.")
    with open(target / "DATASET_CARD.txt", "w", encoding="utf-8") as f:
        f.write(f"dataset_id={args.dataset}\n")
        f.write(f"endpoint={endpoint}\n")
        f.write(f"files={[x.name for x in files]}\n")
    print("Wrote DATASET_CARD.txt")


def disk_free_gb(path: Path) -> float:
    import shutil

    probe = path if path.exists() else Path.cwd()
    return shutil.disk_usage(probe).free / 1e9


if __name__ == "__main__":
    main()
