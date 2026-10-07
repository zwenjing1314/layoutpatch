"""在独立解析环境调用已安装CLI；仅增加计时、实际后端和本进程内存回执。"""
from __future__ import annotations

import ctypes
import importlib.metadata
import json
import sys
import time
from pathlib import Path


class Memory(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
        (name, ctypes.c_size_t) for name in
        ("peak", "working", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")
    ]


def peak_memory():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    api = ctypes.WinDLL("psapi", use_last_error=True)
    api.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(Memory), ctypes.c_ulong]
    counters = Memory()
    counters.cb = ctypes.sizeof(counters)
    if not api.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return counters.peak


def main():
    receipt = Path(sys.argv[1])
    sys.argv = ["mineru-kit", *sys.argv[2:]]
    started = time.perf_counter()
    report = {"status": "started", "sessions": [], "memory_scope": "parser_python_process_OS_peak_working_set"}
    try:
        import onnxruntime as ort

        original = ort.InferenceSession.__init__

        def measured(session, *args, **kwargs):
            begin = time.perf_counter()
            original(session, *args, **kwargs)
            providers = session.get_providers()
            report["sessions"].append({"model": str(args[0]) if args else None,
                                       "load_seconds": time.perf_counter() - begin, "providers": providers})
            if providers != ["CPUExecutionProvider"]:
                raise RuntimeError(f"unexpected inference provider: {providers}")

        ort.InferenceSession.__init__ = measured
        entry = next(e for e in importlib.metadata.distribution("mineru").entry_points if e.name == "mineru-kit")
        cli = entry.load()
        report["tool_import_seconds"] = time.perf_counter() - started
        report["peak_after_import_bytes"] = peak_memory()
        try:
            cli()
        except SystemExit as exc:
            if exc.code not in (0, None):
                raise
        report["status"] = "completed"
    finally:
        report["total_seconds"] = time.perf_counter() - started
        report["model_session_load_seconds"] = sum(s["load_seconds"] for s in report["sessions"])
        report["peak_working_set_bytes"] = peak_memory()
        report["gpu_used"] = any(s["providers"] != ["CPUExecutionProvider"] for s in report["sessions"])
        with receipt.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
