# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Reference-lesion coverage of sampled inputs: geometry, phase guard and CLI (synthetic)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from thoraxbench.benchmark.coverage import (
    CoverageRow,
    CoverageSetting,
    default_grid,
    lesion_slices,
    measure,
    phase_entries,
    prepared_ranges,
    render_table,
    smallest_sufficient,
)
from thoraxbench.cli.main import app
from thoraxbench.config import REPO_ROOT, Settings
from thoraxbench.index import IndexEntry
from thoraxbench.preprocess import HUCues
from thoraxbench.schemas import LesionAnnotation, ReferenceLabels
from thoraxbench.splits import (
    CaseGuard,
    CaseRecord,
    Phase,
    SealedAccessError,
    make_split,
    save_split,
)


def _entry(
    case_id: str = "C1",
    lesions: list[tuple[float, float]] | None = None,
    *,
    nz: int = 100,
    dz: float = 2.0,
) -> IndexEntry:
    """A synthetic index entry; *lesions* are ``(centre_z_mm, diameter_mm)`` pairs."""
    les = [LesionAnnotation(center_zyx=(z, 10.0, 10.0), diameter_mm=d) for z, d in (lesions or [])]
    ref = ReferenceLabels(
        dataset="lidc_idri",
        patient_id=case_id,
        study_uid=case_id,
        labels={"pulmonary_nodule": bool(les)},
        lesions=les,
    )
    return IndexEntry(
        dataset="lidc_idri",
        case_id=case_id,
        patient_id=case_id,
        series_uid=f"1.2.{case_id}",
        path=f"raw/lidc_idri/{case_id}",
        stratum="nodule" if les else "negative",
        n_slices=nz,
        spacing_mm=(dz, 0.7, 0.7),
        qc_adequate=True,
        qc_limitations=[],
        reference=ref,
        cues=HUCues(lung_z_extent=(10, 89)),
    )


def test_prepared_ranges_follow_strategy_and_view_slab() -> None:
    entry = _entry()
    assert prepared_ranges(entry, CoverageSetting("uniform", 2)) == [(0, 1), (99, 100)]
    # 10 mm at 2 mm spacing: half-width round(2.5) = 2 slices each side.
    assert prepared_ranges(entry, CoverageSetting("uniform", 2, 10.0)) == [(0, 3), (97, 100)]
    mip = prepared_ranges(entry, CoverageSetting("mip_slabs", 40, 0.0, {"slab_mm": 10.0}))
    assert len(mip) == 16
    assert mip[0][0] <= 10
    assert mip[-1][1] >= 89


def test_lesion_slices_use_spherical_extent_clamped_to_volume() -> None:
    entry = _entry(nz=50)
    les = LesionAnnotation(center_zyx=(20.0, 0.0, 0.0), diameter_mm=6.0)
    assert lesion_slices(les, entry) == (9, 10, 11)
    edge = LesionAnnotation(center_zyx=(99.0, 0.0, 0.0), diameter_mm=30.0)
    assert lesion_slices(edge, entry) == (42, 49, 49)
    tiny = LesionAnnotation(center_zyx=(21.0, 0.0, 0.0), diameter_mm=0.5)
    first, centre, last = lesion_slices(tiny, entry)
    assert first <= centre <= last


def test_measure_counts_lesions_studies_and_tokens() -> None:
    entries = [
        _entry("A", [(0.0, 4.0), (100.0, 8.0)]),  # first slice + mid volume
        _entry("B", [(198.0, 10.0)]),  # last slice
        _entry("C"),  # negative
    ]
    row = measure(entries, CoverageSetting("uniform", 2))
    assert (row.n_studies, row.n_lesions, row.lesions_covered) == (3, 3, 2)
    assert row.lesions_centre_covered == 2
    assert (row.n_lesions_ge6mm, row.lesions_ge6mm_covered) == (2, 1)
    assert (row.n_positive_studies, row.positive_studies_covered) == (2, 2)
    assert (row.mean_images, row.max_images) == (2.0, 2)
    assert row.max_rendered_slab_mm == 2.0
    assert row.lesion_coverage == pytest.approx(2 / 3)
    assert row.fits_context()
    assert not row.fits_context(num_ctx=1000)
    data = row.to_dict()
    assert data["setting"] == "uniform(n=2) slab=0mm"
    assert data["fits_context"] is True
    assert "A" not in json.dumps(data["setting"])
    masses = measure(entries, CoverageSetting("uniform", 2), labels=["pulmonary_mass"])
    assert masses.n_lesions == 0
    assert masses.lesion_coverage is None


def test_setting_validation_and_names() -> None:
    with pytest.raises(ValueError, match="image count"):
        CoverageSetting("uniform", 0)
    with pytest.raises(ValueError, match="slab"):
        CoverageSetting("uniform", 2, -1.0)
    with pytest.raises(KeyError):
        CoverageSetting("nope", 2)
    named = CoverageSetting("mip_slabs", 9, 0.0, {"slab_mm": 10.0}).name
    assert named == "mip_slabs(n=9,slab_mm=10.0) slab=0mm"
    grid = default_grid()
    assert len(grid) == len({s.name for s in grid}) == 70


def _row(n: int, cov: int, slab: float, *, images: int | None = None) -> CoverageRow:
    return CoverageRow(
        setting=CoverageSetting("uniform", n, slab),
        n_studies=1,
        n_lesions=10,
        lesions_covered=cov,
        lesions_centre_covered=cov,
        n_lesions_ge6mm=0,
        lesions_ge6mm_covered=0,
        n_positive_studies=1,
        positive_studies_covered=1,
        mean_images=float(images or n),
        max_images=images or n,
        estimated_prompt_tokens=1000 + 325 * (images or n),
        max_rendered_slab_mm=slab,
    )


def test_smallest_sufficient_respects_target_context_and_slab() -> None:
    rows = [_row(4, 8, 40.0), _row(16, 9, 10.0), _row(16, 10, 5.0), _row(60, 10, 0.0)]
    pick = smallest_sufficient(rows)
    assert pick is rows[2]
    assert smallest_sufficient(rows, target=0.8, max_slab_mm=50.0) is rows[0]
    assert smallest_sufficient(rows, target=0.8) is rows[2]
    assert smallest_sufficient(rows, target=1.0, num_ctx=4000) is None
    empty = _row(4, 0, 0.0)
    object.__setattr__(empty, "n_lesions", 0)
    assert smallest_sufficient([empty]) is None
    table = render_table(rows)
    assert table.count("\n") == len(rows) + 1
    assert "| no |" in table
    assert "n/a" in render_table([empty])


def _write_split_and_index(root: Path, entries: list[IndexEntry]) -> Settings:
    repo = root / "repo"
    repo.mkdir()
    (repo / "configs").symlink_to(REPO_ROOT / "configs", target_is_directory=True)
    records = [
        CaseRecord(dataset="lidc_idri", patient_id=e.case_id, case_id=e.case_id) for e in entries
    ]
    for seed in range(500):
        split = make_split(records, "lidc_idri", salt=f"cov-{seed}")
        if split.cases(Phase.SEALED) and split.cases(Phase.INTERNAL_TEST):
            break
    save_split(split, root, repo / "manifests")
    index = root / "index" / "lidc_idri.json"
    index.parent.mkdir(parents=True)
    index.write_text(json.dumps([e.model_dump(mode="json") for e in entries]), encoding="utf-8")
    return Settings(repo_root=repo, data_dir=root)


def test_phase_entries_returns_only_guarded_calibration_cases(tmp_path: Path) -> None:
    entries = [_entry(f"P{i}", [(50.0, 6.0)]) for i in range(10)]
    settings = _write_split_and_index(tmp_path, entries)
    guard = CaseGuard.load(settings.data_dir, settings.manifests_dir, "lidc_idri")
    calibration = set(guard.cases(Phase.CALIBRATION))
    got = phase_entries("lidc_idri", settings)
    assert {e.case_id for e in got} == calibration
    assert [e.case_id for e in got] == sorted(calibration)
    internal = phase_entries("lidc_idri", settings, Phase.INTERNAL_TEST)
    assert {e.case_id for e in internal} == set(guard.cases(Phase.INTERNAL_TEST))
    with pytest.raises(SealedAccessError):
        phase_entries("lidc_idri", settings, Phase.SEALED)
    with pytest.raises(SealedAccessError):
        phase_entries("lidc_idri", settings, Phase.DEVELOPMENT)


def test_phase_entries_skip_malformed_and_outside_entries(tmp_path: Path) -> None:
    entries = [_entry(f"P{i}") for i in range(10)]
    settings = _write_split_and_index(tmp_path, entries)
    index = tmp_path / "index" / "lidc_idri.json"
    data = json.loads(index.read_text(encoding="utf-8"))
    data.append("not-an-object")
    data.append({"case_id": "SEALED-OR-UNKNOWN"})
    index.write_text(json.dumps(data), encoding="utf-8")
    got = phase_entries("lidc_idri", settings)
    assert all(e.case_id.startswith("P") for e in got)


def test_cli_coverage_prints_table_and_writes_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entries = [_entry(f"P{i}", [(100.0, 8.0)]) for i in range(10)]
    settings = _write_split_and_index(tmp_path, entries)
    monkeypatch.setattr("thoraxbench.cli.coverage.get_settings", lambda: settings)
    out = tmp_path / "results" / "coverage" / "c.json"
    result = CliRunner().invoke(app, ["coverage", "--output", str(out)])
    assert result.exit_code == 0, result.output
    assert "calibration studies" in result.output
    assert "Smallest fitting setting" in result.output
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["phase"] == "calibration"
    assert len(payload["rows"]) == 70
    assert "P0" not in json.dumps(payload["rows"])
    bad = CliRunner().invoke(app, ["coverage", "--output", str(tmp_path / "elsewhere.json")])
    assert bad.exit_code == 1
    assert "Coverage failed" in bad.output
    monkeypatch.setattr(
        "thoraxbench.benchmark.coverage.smallest_sufficient", lambda *_a, **_k: None
    )
    strict = CliRunner().invoke(app, ["coverage", "--target", "1.0"])
    assert strict.exit_code == 0
    assert "lesion coverage: none" in strict.output
