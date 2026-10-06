"""Fetch pinned public benchmark sources for identity auditing, never scoring."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO = "Yuwh07/SciEGQA-Bench"
REVISION = "9bdca77be633cc3259d7e3739d35b38ab00bf5d9"
DEST = Path("data/raw/sciegqa_bench") / REVISION
FILES = {
    "SciEGQA_Bench.jsonl": (695934, "338b701830495b984acca753e5b5065b35a7566c308f2d5c81f76b8401a3053f"),
    "PDF.tar": (132444160, "d15569aefec7339ebd360a19d946b384b5ced07b8ffda941f0dfa3494b9f7a16"),
    "README.md": (2223, None),
}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(name: str, size: int, expected: str | None) -> dict:
    path = DEST / name
    url = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{name}"
    if not path.exists():
        partial = path.with_suffix(path.suffix + ".part")
        request = urllib.request.Request(url, headers={"User-Agent": "LayoutPatch-data-identity-audit"})
        start = time.monotonic()
        with urllib.request.urlopen(request, timeout=45) as response, partial.open("wb") as stream:
            total = 0
            last = time.monotonic()
            while block := response.read(1024 * 1024):
                stream.write(block)
                total += len(block)
                if time.monotonic() - last > 15:
                    print(f"{name}: {total}/{size} bytes", flush=True)
                    last = time.monotonic()
        if partial.stat().st_size != size or (expected and digest(partial) != expected):
            raise RuntimeError(f"Size or checksum mismatch: {partial}")
        partial.rename(path)
        print(f"Fetched {name}, {time.monotonic() - start:.1f}s", flush=True)
    actual = digest(path)
    if path.stat().st_size != size or (expected and actual != expected):
        raise RuntimeError(f"Existing source differs from pinned identity: {path}")
    return {"path": path.as_posix(), "url": url, "bytes": size, "sha256": actual}


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    records = [fetch(name, size, expected) for name, (size, expected) in FILES.items()]
    receipt = {
        "dataset": REPO, "revision": REVISION, "files": records,
        "retrieved_utc": datetime.now(UTC).isoformat(),
        "purpose": "document/page identity audit only; no benchmark scoring",
        "license_status": "not_declared_in_dataset_card; unresolved",
        "images_tar_downloaded": False,
    }
    receipt_path = DEST / "acquisition.json"
    if not receipt_path.exists():
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"revision": REVISION, "files": len(records), "bytes": sum(r["bytes"] for r in records)}))


if __name__ == "__main__":
    main()
