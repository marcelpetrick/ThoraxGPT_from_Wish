# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""DICOM discovery follows file contents, including extensionless scanner exports."""

from pathlib import Path
from shutil import copyfile

import numpy as np
import pytest

from thoraxbench.dicom import discover_series, load_study, select_series
from thoraxbench.synthetic import PhantomSpec, make_phantom


@pytest.mark.parametrize("suffix", ["", ".IMA", ".bin"])
def test_ct_series_loads_by_content_with_any_filename_suffix(
    phantom_dir: Path, phantom_spec: PhantomSpec, tmp_path: Path, suffix: str
) -> None:
    target = tmp_path / "scanner-export" / "nested-series"
    target.mkdir(parents=True)
    for index, source in enumerate(sorted(phantom_dir.rglob("*.dcm"))):
        copyfile(source, target / f"image_{index:04d}{suffix}")
    (target / "notes").write_text("Not a DICOM file")
    (target / "misleading.dcm").write_bytes(b"This suffix does not make this DICOM")
    series = discover_series(target.parent)
    assert len(series) == 2
    selection = select_series(series)
    assert selection.series is not None
    assert all(file.suffix == suffix for file in selection.series.files)
    volume, _ = load_study(target.parent)
    assert volume is not None
    assert volume.qc.duplicates_removed == 1
    assert volume.qc.adequate
    assert np.array_equal(volume.hu, make_phantom(phantom_spec))
