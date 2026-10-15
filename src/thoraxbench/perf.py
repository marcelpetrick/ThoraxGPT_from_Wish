# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Performance measurements per study (Vision §21).

``measure()`` is a context manager that records wall time, named stage timings
(preprocess / inference / parse / …), peak resident memory of this process and GPU memory
in use (via ``nvidia-smi``; ``None`` when no NVIDIA GPU is available).
"""

from __future__ import annotations

import resource
import shutil
import subprocess
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel, Field

NVIDIA_SMI_TIMEOUT_S = 5


class PerfRecord(BaseModel):
    """Measurements for one study/model run."""

    total_s: float = 0.0
    stages_s: dict[str, float] = Field(default_factory=dict)
    peak_rss_mb: float | None = None
    gpu_memory_used_mb: float | None = None
    gpu_memory_peak_mb: float | None = None
    model_vram_mb: float | None = None
    model_disk_mb: float | None = None
    input_bytes: int | None = None
    n_images: int | None = None
    tokens_generated: int | None = None
    failed: bool = False
    timed_out: bool = False
    error: str | None = None


def peak_rss_mb() -> float:
    """Peak resident set size of this process in MB (``ru_maxrss`` is KiB on Linux)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def current_rss_mb(status: Path = Path("/proc/self/status")) -> float | None:
    """Return the current resident set size from ``/proc``; ``None`` where unavailable."""
    try:
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return float(line.split()[1]) / 1024.0
    except OSError:
        return None
    return None


def gpu_memory_used_mb() -> float | None:
    """Total GPU memory in use (MB) summed over GPUs, or ``None`` without nvidia-smi."""
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return None
    try:
        out = subprocess.run(  # noqa: S603 - trusted executable, static arguments
            [exe, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
            timeout=NVIDIA_SMI_TIMEOUT_S,
        ).stdout
        values = [float(v) for v in out.split() if v.strip()]
    except OSError, subprocess.SubprocessError, ValueError:
        return None
    return sum(values) if values else None


class Measurement:
    """Mutable handle yielded by :func:`measure`."""

    def __init__(self) -> None:
        self.record = PerfRecord()
        self._gpu_peak: float | None = None

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """Time a named stage; repeated stages accumulate."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.record.stages_s[name] = self.record.stages_s.get(name, 0.0) + elapsed
            self.sample_gpu()

    def sample_gpu(self) -> None:
        """Sample GPU memory now and keep the peak."""
        used = gpu_memory_used_mb()
        if used is not None:
            self._gpu_peak = used if self._gpu_peak is None else max(self._gpu_peak, used)
            self.record.gpu_memory_used_mb = used
        self.record.gpu_memory_peak_mb = self._gpu_peak


@contextmanager
def measure() -> Iterator[Measurement]:
    """Measure a block; exceptions are recorded (``failed``/``error``) and re-raised."""
    m = Measurement()
    m.sample_gpu()
    start = time.perf_counter()
    try:
        yield m
    except TimeoutError as exc:
        m.record.failed = m.record.timed_out = True
        m.record.error = f"timeout: {exc}"
        raise
    except Exception as exc:
        m.record.failed = True
        m.record.error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        m.record.total_s = time.perf_counter() - start
        m.record.peak_rss_mb = peak_rss_mb()
        m.sample_gpu()


def throughput_per_hour(records: Sequence[PerfRecord]) -> float | None:
    """Successful studies per hour given the summed wall time of all records."""
    total = sum(r.total_s for r in records)
    ok = sum(1 for r in records if not r.failed)
    return ok * 3600.0 / total if total > 0 else None


def summarize(records: Sequence[PerfRecord]) -> dict[str, float | int | None]:
    """Aggregate latency/memory/failure statistics over many records."""
    if not records:
        return {"n": 0}
    totals = sorted(r.total_s for r in records)
    gpu = [r.gpu_memory_peak_mb for r in records if r.gpu_memory_peak_mb is not None]
    rss = [r.peak_rss_mb for r in records if r.peak_rss_mb is not None]
    tokens = [r.tokens_generated for r in records if r.tokens_generated is not None]
    return {
        "n": len(records),
        "failures": sum(r.failed for r in records),
        "timeouts": sum(r.timed_out for r in records),
        "latency_mean_s": sum(totals) / len(totals),
        "latency_median_s": totals[len(totals) // 2],
        "latency_max_s": totals[-1],
        "peak_gpu_memory_mb": max(gpu) if gpu else None,
        "peak_rss_mb": max(rss) if rss else None,
        "tokens_mean": sum(tokens) / len(tokens) if tokens else None,
        "throughput_per_hour": throughput_per_hour(records),
    }
