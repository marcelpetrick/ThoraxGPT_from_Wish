# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
import subprocess
from pathlib import Path

import numpy as np
import pytest

from thoraxbench import perf, provenance
from thoraxbench.calibration import (
    AbstentionRule,
    IsotonicCalibrator,
    PlattCalibrator,
    TemperatureScaler,
    calibrator_from_dict,
    fit_thresholds,
)

Y = [0, 0, 0, 1, 1, 1, 0, 1, 1, 0]
P = [0.1, 0.4, 0.35, 0.8, 0.7, 0.9, 0.6, 0.55, 0.95, 0.2]


def test_thresholds() -> None:
    th = fit_thresholds({"a": Y, "b": [1] * 10}, {"a": P, "b": P})
    assert 0.4 < th["a"] <= 0.7
    assert th["b"] == 0.5
    sens = fit_thresholds({"a": Y}, {"a": P}, method="sensitivity", target_sensitivity=1.0)
    assert sens["a"] <= 0.55
    with pytest.raises(ValueError, match="unknown"):
        fit_thresholds({"a": Y}, {"a": P}, method="magic")
    with pytest.raises(ValueError, match="sealed"):
        fit_thresholds({"a": Y}, {"a": P}, phase="sealed")
    with pytest.raises(ValueError, match="equal length"):
        fit_thresholds({"a": Y}, {"a": P[:3]})


@pytest.mark.parametrize("cls", [TemperatureScaler, PlattCalibrator, IsotonicCalibrator])
def test_calibrators_roundtrip(cls: type) -> None:
    cal = cls().fit(Y, P, phase="development")
    out = cal.transform(P)
    assert out.shape == (10,)
    assert np.all((out >= 0) & (out <= 1))
    again = calibrator_from_dict(cal.to_dict())
    assert np.allclose(again.transform(P), out)
    with pytest.raises(ValueError, match="sealed"):
        cls().fit(Y, P, phase="sealed")


def test_calibrator_errors() -> None:
    with pytest.raises(ValueError, match="both classes"):
        PlattCalibrator().fit([1, 1], [0.2, 0.3])
    with pytest.raises(ValueError, match="unknown calibrator"):
        calibrator_from_dict({"kind": "nope"})
    assert np.allclose(IsotonicCalibrator().transform([0.3]), [0.3])


def test_abstention_rule() -> None:
    rule = AbstentionRule(0.4, 0.6)
    assert rule.decide(0.5) is None
    assert rule.decide(0.9) is True
    assert rule.decide(0.1) is False
    assert AbstentionRule.from_dict(rule.to_dict()) == rule
    with pytest.raises(ValueError, match="low"):
        AbstentionRule(0.7, 0.2)


def test_measure_records_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    values = iter([100.0, 300.0, 200.0, 250.0])
    monkeypatch.setattr(perf, "gpu_memory_used_mb", lambda: next(values))
    with perf.measure() as m:
        with m.stage("preprocess"):
            pass
        with m.stage("preprocess"):
            pass
    rec = m.record
    assert "preprocess" in rec.stages_s
    assert rec.gpu_memory_peak_mb == 300.0
    assert rec.peak_rss_mb
    assert rec.peak_rss_mb > 0
    assert not rec.failed


def test_measure_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(perf, "gpu_memory_used_mb", lambda: None)
    with pytest.raises(TimeoutError), perf.measure() as m:
        raise TimeoutError("slow")
    assert m.record.timed_out
    assert m.record.failed
    with pytest.raises(RuntimeError), perf.measure() as m2:
        raise RuntimeError("boom")
    assert m2.record.error == "RuntimeError: boom"
    s = perf.summarize([m.record, m2.record, perf.PerfRecord(total_s=2.0, tokens_generated=5)])
    assert s["failures"] == 2
    assert s["timeouts"] == 1
    assert perf.summarize([]) == {"n": 0}
    assert perf.throughput_per_hour([perf.PerfRecord()]) is None


def test_gpu_memory_and_rss(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(perf.shutil, "which", lambda _n: None)
    assert perf.gpu_memory_used_mb() is None
    monkeypatch.setattr(perf.shutil, "which", lambda _n: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(
        perf.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="100\n50\n"),
    )
    assert perf.gpu_memory_used_mb() == 150.0
    monkeypatch.setattr(
        perf.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="\n"),
    )
    assert perf.gpu_memory_used_mb() is None

    def boom(*_a: object, **_k: object) -> None:
        raise subprocess.TimeoutExpired("x", 1)

    monkeypatch.setattr(perf.subprocess, "run", boom)
    assert perf.gpu_memory_used_mb() is None
    status = tmp_path / "status"
    status.write_text("Name: x\nVmRSS:\t 2048 kB\n")
    assert perf.current_rss_mb(status) == 2.0
    status.write_text("Name: x\n")
    assert perf.current_rss_mb(status) is None
    assert perf.current_rss_mb(tmp_path / "missing") is None


def test_hash_helpers(tmp_path: Path) -> None:
    assert provenance.sha256_of_obj({"b": 1, "a": 2}) == provenance.sha256_of_obj({"a": 2, "b": 1})
    f = tmp_path / "f.txt"
    f.write_bytes(b"abc")
    assert provenance.sha256_of_file(f).startswith("ba7816bf")


def test_provenance_collect(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    outputs = {
        "rev-parse": "abc123",
        "status": " M file",
        "--query-gpu=name,driver_version": "RTX A2000, 580.1",
        "nvidia-smi": "| NVIDIA-SMI 580.1   Driver Version: 580.1   CUDA Version: 13.0 |",
    }

    def fake_run(args: list[str], cwd: Path | None = None) -> str | None:
        for key, val in outputs.items():
            if key in args[1:] or (key == "nvidia-smi" and args == ["nvidia-smi"]):
                return val
        return None

    monkeypatch.setattr(provenance, "_run", fake_run)
    prov = provenance.RunProvenance.collect(tmp_path, model_id="m", seed=3)
    assert prov.git_commit == "abc123"
    assert prov.git_dirty is True
    assert prov.gpu == "RTX A2000"
    assert prov.driver == "580.1"
    assert prov.cuda == "13.0"
    assert len(prov.fingerprint()) == 64
    monkeypatch.setattr(provenance, "_run", lambda *_a, **_k: None)
    bare = provenance.RunProvenance.collect(tmp_path)
    assert bare.git_commit is None
    assert bare.gpu is None


def test_run_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provenance.shutil, "which", lambda _n: None)
    assert provenance._run(["git", "status"]) is None
    monkeypatch.setattr(provenance.shutil, "which", lambda n: f"/usr/bin/{n}")

    def fail(*_a: object, **_k: object) -> None:
        raise subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr(provenance.subprocess, "run", fail)
    assert provenance._run(["git", "status"]) is None
    monkeypatch.setattr(
        provenance.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=" ok \n"),
    )
    assert provenance._run(["git", "status"]) == "ok"
