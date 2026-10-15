# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
from pathlib import Path

import numpy as np
import pydicom

from thoraxbench.dicom import discover_series, load_study, select_series
from thoraxbench.dicom.discovery import SeriesInfo
from thoraxbench.dicom.volume import lung_voxel_fraction
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series


def test_discovery_groups_and_skips_non_dicom(phantom_dir: Path) -> None:
    series = discover_series(phantom_dir)
    assert len(series) == 2  # axial series + scout; README.txt skipped
    assert any(s.is_localizer for s in series)


def test_selection_rejects_scout(phantom_dir: Path) -> None:
    sel = select_series(discover_series(phantom_dir))
    assert sel.series is not None
    assert sel.series.n_files == 65  # 64 + duplicate
    assert "localizer/scout series" in sel.rejected.values()
    assert "axial CT" in sel.reason


def test_load_volume_geometry_and_hu(phantom_dir: Path, phantom_spec: PhantomSpec) -> None:
    vol, meta = load_study(phantom_dir)
    assert vol is not None
    assert meta["selected_series"] == vol.series_uid
    assert vol.shape == phantom_spec.shape
    expected = make_phantom(phantom_spec)
    assert np.array_equal(vol.hu, expected)  # sorted cranial-first despite shuffled files
    assert vol.qc.duplicates_removed == 1
    assert vol.qc.adequate
    assert vol.qc.spacing_mm == (5.0, 2.5, 2.5)
    assert vol.qc.axial_coverage_mm == 320.0
    assert not vol.qc.gantry_tilt_suspected
    d = vol.qc.to_dict()
    assert d["adequate"] is True
    assert any("duplicate" in w for w in d["limitations"])


def test_qc_flags_inadequate_study(tmp_path: Path) -> None:
    spec = PhantomSpec(shape=(40, 64, 64), spacing_mm=(2.0, 2.0, 2.0))
    hu = make_phantom(spec)
    hu[:] = 40  # no lung at all
    out = write_dicom_series(hu, tmp_path, spec.spacing_mm, include_scout=False)
    for f in sorted(out.glob("img_*.dcm")):
        if 10 <= int(pydicom.dcmread(f, stop_before_pixels=True).InstanceNumber) <= 25:
            f.unlink()
    vol, _ = load_study(tmp_path)
    assert vol is not None
    assert not vol.qc.adequate
    joined = " ".join(vol.qc.limitations)
    assert "coverage" in joined
    assert "lung" in joined
    assert "slice gap" in joined
    assert vol.qc.non_uniform_spacing is True


def test_qc_gap_and_too_few_slices(tmp_path: Path) -> None:
    spec = PhantomSpec(shape=(30, 32, 32), spacing_mm=(1.0, 2.0, 2.0))
    hu = make_phantom(spec)
    out = write_dicom_series(hu, tmp_path / "s", (1.0, 2.0, 2.0), include_scout=False)
    files = sorted(out.glob("img_*.dcm"))
    # remove 25 contiguous slices -> big gap and too few slices
    for f in files:
        ds = pydicom.dcmread(f)
        if 2 <= int(ds.InstanceNumber) <= 26:
            f.unlink()
    sel = select_series(discover_series(out))
    assert sel.series is None
    assert "no eligible" in sel.reason


def test_no_series(tmp_path: Path) -> None:
    vol, meta = load_study(tmp_path)
    assert vol is None
    assert meta["selected_series"] is None


def test_series_info_orientation_rules() -> None:
    s = SeriesInfo("st", "se", "p", "CT", orientation=None)
    assert not s.is_axial
    coronal = SeriesInfo("st", "se", "p", "CT", orientation=(1, 0, 0, 0, 0, -1))
    assert not coronal.is_axial


def test_selection_rules() -> None:
    def mk(
        uid: str,
        n: int,
        modality: str = "CT",
        orient: tuple[float, ...] = (1, 0, 0, 0, 1, 0),
        thick: float | None = 1.0,
    ) -> SeriesInfo:
        return SeriesInfo(
            "st",
            uid,
            "p",
            modality,
            files=[Path(f"{i}") for i in range(n)],
            orientation=orient,
            slice_thickness=thick,
        )

    sel = select_series(
        [
            mk("a", 100, thick=5.0),
            mk("b", 100, thick=1.0),
            mk("c", 50),
            mk("d", 100, "MR"),
            mk("e", 100, orient=(1, 0, 0, 0, 0, -1)),
            mk("f", 5),
        ]
    )
    assert sel.series is not None
    assert sel.series.series_uid == "b"
    assert sel.rejected["d"].startswith("modality")
    assert sel.rejected["e"] == "not an axial acquisition"
    assert "only 5" in sel.rejected["f"]
    assert "ranked lower" in sel.rejected["a"]


def test_lung_fraction_empty() -> None:
    assert lung_voxel_fraction(np.zeros((0, 0, 0), dtype=np.int16)) == 0.0


def test_phantom_variants() -> None:
    hu = make_phantom(
        PhantomSpec(shape=(20, 48, 48), emphysema=True, nodule_radius_mm=6, nodule_side="left")
    )
    assert (hu < -950).sum() > 0


def test_padding_missing_position_and_tilt(tmp_path: Path) -> None:
    spec = PhantomSpec(shape=(24, 32, 32), spacing_mm=(2.0, 2.0, 2.0))
    out = write_dicom_series(
        make_phantom(spec), tmp_path / "a", spec.spacing_mm, include_scout=False, shuffle=False
    )
    for f in sorted(out.glob("img_*.dcm")):
        ds = pydicom.dcmread(f)
        ds.add_new(0x00280120, "US", 0)
        ds.ImagePositionPatient = [float(ds.InstanceNumber), 0.0, ds.ImagePositionPatient[2]]
        ds.save_as(f)
    vol, _ = load_study(out)
    assert vol is not None
    assert vol.qc.gantry_tilt_suspected
    assert vol.qc.hu_min == -1024

    out_b = write_dicom_series(
        make_phantom(spec), tmp_path / "b", spec.spacing_mm, include_scout=False, shuffle=False
    )
    for f in sorted(out_b.glob("img_*.dcm")):
        ds = pydicom.dcmread(f)
        del ds.ImagePositionPatient
        ds.save_as(f)
    vol_b, _ = load_study(out_b)
    assert vol_b is not None
    assert any("InstanceNumber" in w for w in vol_b.qc.warnings)


def test_unreadable_file_skipped(tmp_path: Path) -> None:
    (tmp_path / "broken.dcm").write_bytes(b"DICM" * 10)
    assert discover_series(tmp_path) == []
