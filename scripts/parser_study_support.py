"""Isolated, model-free CLI loading and I/O for the parser candidate study."""
from __future__ import annotations

import hashlib
import json
import sys
import types
from base64 import b64encode
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRITE_BROKER = False


def enable_write_broker():
    global WRITE_BROKER
    WRITE_BROKER = True


def write_bytes(path, data):
    """Exclusive writes, optionally acknowledged by a path-restricted PS parent.

    The parent persists each write before acknowledging; a raw reference/identity
    is therefore on disk before candidate export continues. No silent buffering.
    """
    path = Path(path).resolve()
    relative = path.relative_to(ROOT)
    if relative.parts[:3] not in {("artifacts", "parser_candidate_comparison", "v1"), ("runs", "parser_candidate_comparison", "v1")}:
        raise ValueError(f"study writes outside isolated artifacts/runs forbidden: {path}")
    if WRITE_BROKER:
        print(json.dumps({"event": "study_write", "path": str(path), "base64": b64encode(data).decode("ascii")}), flush=True)
        acknowledgement = sys.stdin.readline().strip()
        if acknowledgement != "ok":
            raise OSError(f"write broker did not acknowledge {path}: {acknowledgement}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)


def enable_geometry_only_imports():
    """CLI/test processes only: avoid eager torch imports in package __init__."""
    for package in ("layoutpatch", "layoutpatch.datasets", "layoutpatch.evaluation", "layoutpatch.layout"):
        if package in sys.modules:
            continue
        namespace = types.ModuleType(package)
        namespace.__path__ = [str(ROOT / "src" / package.replace(".", "/"))]
        sys.modules[package] = namespace


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def read_jsonl(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def within(root, value):
    root = Path(root).resolve()
    path = (root / value).resolve()
    path.relative_to(root)
    return path


def checked(root, value, expected):
    path = within(root, value)
    if sha256(path) != expected:
        raise ValueError(f"SHA256 mismatch: {path}")
    return path


def write_json(path, value):
    write_bytes(path, (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))


def write_jsonl(path, rows):
    write_bytes(path, "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows).encode("utf-8"))
