# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Deterministic, label-stratified, patient-level 80/20 splits.

* 20 % of patients (per stratum) form the **sealed validation** set. It is stored apart in
  ``data/sealed/<dataset>.json`` (read-only) and only hashes go into Git.
* The remaining 80 % is the **development** set, subdivided into ``calibration`` (80 %) and
  ``internal_test`` (20 %) for prompt/threshold work and internal checks (Vision §15).

Ordering uses ``sha256(salt + patient_id)``, so the split is reproducible from the patient list
and the salt alone, and splitting is always by patient, never by study or slice.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections import defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

SPLIT_VERSION = "1"
DEFAULT_SALT = "thoraxbench-split-v1"


class Phase(StrEnum):
    """Which part of the data a run may touch."""

    CALIBRATION = "calibration"
    INTERNAL_TEST = "internal_test"
    DEVELOPMENT = "development"  # calibration + internal_test
    SEALED = "sealed"


class CaseRecord(BaseModel):
    """One study of one patient, with the stratum used for stratification."""

    dataset: str
    patient_id: str
    case_id: str
    stratum: str = "all"


def _hash(salt: str, value: str) -> str:
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()


class SplitManifest(BaseModel):
    """Committed, ID-free description of a split (counts + salted hashes)."""

    dataset: str
    split_version: str = SPLIT_VERSION
    salt: str
    sealed_fraction: float
    calibration_fraction: float
    created_at: str
    patients: dict[str, int]
    cases: dict[str, int]
    strata: dict[str, dict[str, int]]
    patient_hashes: dict[str, list[str]]
    sealed_set_sha256: str
    development_set_sha256: str


class SplitResult(BaseModel):
    """Full split with plaintext IDs (stored only in the git-ignored data directory)."""

    manifest: SplitManifest
    assignments: dict[str, Phase] = Field(description="case_id -> phase")
    patient_of: dict[str, str]

    def cases(self, phase: Phase) -> list[str]:
        """Case IDs belonging to *phase* (DEVELOPMENT = calibration + internal_test)."""
        wanted = {Phase.CALIBRATION, Phase.INTERNAL_TEST} if phase is Phase.DEVELOPMENT else {phase}
        return sorted(c for c, p in self.assignments.items() if p in wanted)


def _set_hash(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


def make_split(
    cases: list[CaseRecord],
    dataset: str,
    *,
    sealed_fraction: float = 0.2,
    calibration_fraction: float = 0.8,
    salt: str = DEFAULT_SALT,
) -> SplitResult:
    """Create the patient-level split for *dataset*.

    A patient's stratum is the lexicographically greatest stratum among their cases (so a
    patient with any positive study is stratified as positive when strata are e.g.
    ``neg``/``pos``). Each stratum contributes ``round(n * sealed_fraction)`` patients
    (at least one when the stratum has two or more patients) to the sealed set.

    Raises:
        ValueError: on empty input, mixed datasets, or a patient's cases split across IDs.
    """
    if not cases:
        msg = "cannot split an empty case list"
        raise ValueError(msg)
    if any(c.dataset != dataset for c in cases):
        msg = f"all cases must belong to dataset {dataset}"
        raise ValueError(msg)
    if not 0.0 < sealed_fraction < 1.0 or not 0.0 < calibration_fraction <= 1.0:
        msg = "fractions must be in (0, 1)"
        raise ValueError(msg)
    by_patient: dict[str, list[CaseRecord]] = defaultdict(list)
    for c in cases:
        by_patient[c.patient_id].append(c)
    stratum_of = {p: max(c.stratum for c in cs) for p, cs in by_patient.items()}
    by_stratum: dict[str, list[str]] = defaultdict(list)
    for p, s in stratum_of.items():
        by_stratum[s].append(p)

    patient_phase: dict[str, Phase] = {}
    for patients in by_stratum.values():
        ordered = sorted(patients, key=lambda p: _hash(salt, p))
        n_sealed = round(len(ordered) * sealed_fraction)
        if len(ordered) >= 2:
            n_sealed = max(1, n_sealed)
        dev = ordered[n_sealed:]
        n_cal = round(len(dev) * calibration_fraction)
        if len(dev) >= 2 and calibration_fraction < 1.0:
            n_cal = min(n_cal, len(dev) - 1)
        for p in ordered[:n_sealed]:
            patient_phase[p] = Phase.SEALED
        for i, p in enumerate(dev):
            patient_phase[p] = Phase.CALIBRATION if i < n_cal else Phase.INTERNAL_TEST

    assignments = {c.case_id: patient_phase[c.patient_id] for c in cases}
    patient_of = {c.case_id: c.patient_id for c in cases}
    phases = (Phase.CALIBRATION, Phase.INTERNAL_TEST, Phase.SEALED)
    strata_counts: dict[str, dict[str, int]] = {}
    for s, patients in sorted(by_stratum.items()):
        strata_counts[s] = {
            ph.value: sum(1 for p in patients if patient_phase[p] is ph) for ph in phases
        }
    sealed_patients = [p for p, ph in patient_phase.items() if ph is Phase.SEALED]
    dev_patients = [p for p, ph in patient_phase.items() if ph is not Phase.SEALED]
    manifest = SplitManifest(
        dataset=dataset,
        salt=salt,
        sealed_fraction=sealed_fraction,
        calibration_fraction=calibration_fraction,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        patients={ph.value: sum(1 for v in patient_phase.values() if v is ph) for ph in phases},
        cases={ph.value: sum(1 for v in assignments.values() if v is ph) for ph in phases},
        strata=strata_counts,
        patient_hashes={
            ph.value: sorted(_hash(salt, p) for p, v in patient_phase.items() if v is ph)
            for ph in phases
        },
        sealed_set_sha256=_set_hash(sealed_patients),
        development_set_sha256=_set_hash(dev_patients),
    )
    return SplitResult(manifest=manifest, assignments=assignments, patient_of=patient_of)


def split_paths(data_dir: Path, manifests_dir: Path, dataset: str) -> dict[str, Path]:
    """Locations of the development file, the sealed file and the committed manifest."""
    return {
        "development": data_dir / "splits" / f"{dataset}.json",
        "sealed": data_dir / "sealed" / f"{dataset}.json",
        "manifest": manifests_dir / "splits" / f"{dataset}.json",
    }


def save_split(
    result: SplitResult, data_dir: Path, manifests_dir: Path, *, overwrite: bool = False
) -> dict[str, Path]:
    """Persist a split: development IDs, sealed IDs (read-only) and the hash-only manifest.

    Raises:
        FileExistsError: if a split for this dataset already exists and *overwrite* is false
            (splits are frozen once created).
    """
    paths = split_paths(data_dir, manifests_dir, result.manifest.dataset)
    if not overwrite and any(p.exists() for p in paths.values()):
        msg = f"split for {result.manifest.dataset} already exists and is frozen"
        raise FileExistsError(msg)
    dev = {
        c: {"phase": ph.value, "patient_id": result.patient_of[c]}
        for c, ph in sorted(result.assignments.items())
        if ph is not Phase.SEALED
    }
    sealed = {
        c: {"phase": ph.value, "patient_id": result.patient_of[c]}
        for c, ph in sorted(result.assignments.items())
        if ph is Phase.SEALED
    }
    header = result.manifest.model_dump(exclude={"patient_hashes"})
    _write(paths["development"], {"manifest": header, "cases": dev})
    sealed_path = paths["sealed"]
    if sealed_path.exists():
        os.chmod(sealed_path, stat.S_IRUSR | stat.S_IWUSR)
    _write(sealed_path, {"manifest": header, "cases": sealed})
    os.chmod(sealed_path, stat.S_IRUSR)
    _write(paths["manifest"], result.manifest.model_dump())
    return paths


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_split(
    data_dir: Path, manifests_dir: Path, dataset: str, *, include_sealed: bool
) -> SplitResult:
    """Load a stored split. Sealed IDs are only read when *include_sealed* is true.

    The committed manifest is verified against the development file so a tampered or
    regenerated split is detected.

    Raises:
        FileNotFoundError: if the split does not exist.
        ValueError: if the stored files disagree with the committed manifest.
    """
    paths = split_paths(data_dir, manifests_dir, dataset)
    manifest = SplitManifest.model_validate_json(paths["manifest"].read_text(encoding="utf-8"))
    dev = json.loads(paths["development"].read_text(encoding="utf-8"))
    files = [dev]
    if include_sealed:
        files.append(json.loads(paths["sealed"].read_text(encoding="utf-8")))
    assignments: dict[str, Phase] = {}
    patient_of: dict[str, str] = {}
    for payload in files:
        for case_id, info in payload["cases"].items():
            assignments[case_id] = Phase(info["phase"])
            patient_of[case_id] = info["patient_id"]
    dev_patients = sorted({patient_of[c] for c, p in assignments.items() if p is not Phase.SEALED})
    if _set_hash(dev_patients) != manifest.development_set_sha256:
        msg = f"development split of {dataset} does not match the committed manifest"
        raise ValueError(msg)
    if include_sealed:
        sealed_patients = sorted(
            {patient_of[c] for c, p in assignments.items() if p is Phase.SEALED}
        )
        if _set_hash(sealed_patients) != manifest.sealed_set_sha256:
            msg = f"sealed split of {dataset} does not match the committed manifest"
            raise ValueError(msg)
    return SplitResult(manifest=manifest, assignments=assignments, patient_of=patient_of)
