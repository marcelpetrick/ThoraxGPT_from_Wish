# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Shared fixtures: synthetic DICOM phantoms (never real patient data)."""

from __future__ import annotations

from pathlib import Path

import pytest

from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series


@pytest.fixture(scope="session")
def phantom_spec() -> PhantomSpec:
    return PhantomSpec(nodule_radius_mm=8.0, effusion=True, coronary_calcification=True)


@pytest.fixture(scope="session")
def phantom_dir(tmp_path_factory: pytest.TempPathFactory, phantom_spec: PhantomSpec) -> Path:
    hu = make_phantom(phantom_spec)
    out = tmp_path_factory.mktemp("phantom") / "study"
    return write_dicom_series(hu, out, phantom_spec.spacing_mm, duplicate_slice=True)
