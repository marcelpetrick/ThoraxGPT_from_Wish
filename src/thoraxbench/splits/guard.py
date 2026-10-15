# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""The sealed-validation guard.

Any code that iterates over cases asks a :class:`CaseGuard` which IDs it may use. Requests
for sealed cases fail with :class:`SealedAccessError` unless an experiment configuration was
**frozen** first (:func:`freeze_experiment`; not yet exposed in the CLI) and the caller passes
the matching freeze record.
Freezing records the config hash; changing the config afterwards invalidates the freeze, so
nobody can tune on the sealed set and re-run (Vision §2.4, §14, §19).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from thoraxbench.splits.split import Phase, SplitResult, load_split


class SealedAccessError(PermissionError):
    """Raised when code tries to read sealed-validation cases without a valid freeze."""


class FreezeRecord(BaseModel):
    """Proof that an experiment config was frozen before touching sealed data."""

    experiment_id: str
    config_sha256: str
    frozen_at: str


def config_sha256(config_path: Path) -> str:
    """Hash of an experiment config file's bytes."""
    return hashlib.sha256(config_path.read_bytes()).hexdigest()


def _freeze_path(data_dir: Path, experiment_id: str) -> Path:
    return data_dir / "sealed" / "freeze" / f"{experiment_id}.json"


def freeze_experiment(config_path: Path, experiment_id: str, data_dir: Path) -> FreezeRecord:
    """Freeze *config_path*; afterwards its hash must not change for sealed evaluation.

    Raises:
        FileExistsError: if the experiment was already frozen with a different config.
    """
    record = FreezeRecord(
        experiment_id=experiment_id,
        config_sha256=config_sha256(config_path),
        frozen_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    path = _freeze_path(data_dir, experiment_id)
    if path.exists():
        existing = FreezeRecord.model_validate_json(path.read_text(encoding="utf-8"))
        if existing.config_sha256 != record.config_sha256:
            msg = f"experiment {experiment_id} is already frozen with a different config"
            raise FileExistsError(msg)
        return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return record


def verify_freeze(config_path: Path, experiment_id: str, data_dir: Path) -> FreezeRecord:
    """Return the freeze record if *config_path* still matches it.

    Raises:
        SealedAccessError: if the experiment was never frozen or the config changed since.
    """
    path = _freeze_path(data_dir, experiment_id)
    if not path.exists():
        msg = f"experiment {experiment_id} is not frozen; freezing is not yet exposed in the CLI"
        raise SealedAccessError(msg)
    record = FreezeRecord.model_validate_json(path.read_text(encoding="utf-8"))
    if record.config_sha256 != config_sha256(config_path):
        msg = f"config of {experiment_id} changed after freezing; sealed access denied"
        raise SealedAccessError(msg)
    return record


class CaseGuard:
    """Hands out case IDs per phase and blocks sealed access by default."""

    def __init__(self, split: SplitResult, *, freeze: FreezeRecord | None = None) -> None:
        self._split = split
        self._freeze = freeze

    @classmethod
    def load(
        cls,
        data_dir: Path,
        manifests_dir: Path,
        dataset: str,
        *,
        freeze: FreezeRecord | None = None,
    ) -> CaseGuard:
        """Load the stored split; sealed IDs are read only when a freeze record is given."""
        split = load_split(data_dir, manifests_dir, dataset, include_sealed=freeze is not None)
        return cls(split, freeze=freeze)

    @property
    def dataset(self) -> str:
        """Dataset id of the guarded split."""
        return self._split.manifest.dataset

    def cases(self, phase: Phase) -> list[str]:
        """Case IDs for *phase*.

        Raises:
            SealedAccessError: for ``Phase.SEALED`` without a freeze record.
        """
        if phase is Phase.SEALED and self._freeze is None:
            msg = "sealed-validation cases require a frozen experiment (--unseal)"
            raise SealedAccessError(msg)
        return self._split.cases(phase)

    def phase_of(self, case_id: str) -> Phase | None:
        """Phase of a known case (sealed cases are unknown unless unsealed)."""
        return self._split.assignments.get(case_id)

    def check(self, case_id: str, phase: Phase) -> None:
        """Assert that *case_id* may be used in *phase*.

        Raises:
            SealedAccessError: if the case is sealed (or unknown) and the phase is not
                an unsealed sealed-evaluation.
        """
        actual = self._split.assignments.get(case_id)
        if actual is None:
            msg = f"case {case_id} is not in the development split (sealed or unknown)"
            raise SealedAccessError(msg)
        if actual is Phase.SEALED and (phase is not Phase.SEALED or self._freeze is None):
            msg = f"case {case_id} is sealed"
            raise SealedAccessError(msg)
        if phase is Phase.DEVELOPMENT and actual in {Phase.CALIBRATION, Phase.INTERNAL_TEST}:
            return
        if phase is not actual:
            msg = f"case {case_id} belongs to {actual.value}, not {phase.value}"
            raise SealedAccessError(msg)

    def summary(self) -> dict[str, object]:
        """Return split counts only (no IDs), safe to print and log."""
        return json.loads(self._split.manifest.model_dump_json(exclude={"patient_hashes"}))  # type: ignore[no-any-return]
