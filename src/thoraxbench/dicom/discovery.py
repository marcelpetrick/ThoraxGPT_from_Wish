# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Header-only study discovery and deterministic chest-series selection (Vision §9.1)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from thoraxbench.dicom.headers import HEADER_ERRORS, read_header, record_header_error
from thoraxbench.dicom.progress import Progress, emit_progress

AXIAL_TOLERANCE = 0.1
MIN_SERIES_SLICES = 20


@dataclass
class SeriesInfo:
    """Header metadata of one DICOM series (no pixel data loaded)."""

    study_uid: str
    series_uid: str
    patient_id: str
    modality: str
    files: list[Path] = field(default_factory=list)
    description: str = ""
    image_type: tuple[str, ...] = ()
    slice_thickness: float | None = None
    kernel: str | None = None
    contrast: str | None = None
    orientation: tuple[float, ...] | None = None
    manufacturer: str | None = None

    @property
    def n_files(self) -> int:
        """Number of image files in the series."""
        return len(self.files)

    @property
    def is_localizer(self) -> bool:
        """True for scout/localizer/topogram series."""
        tokens = {t.upper() for t in self.image_type}
        desc = self.description.upper()
        return bool(
            tokens & {"LOCALIZER", "SCOUT", "TOPOGRAM"}
            or any(word in desc for word in ("SCOUT", "LOCALIZER", "TOPOGRAM", "SURVIEW"))
        )

    @property
    def is_axial(self) -> bool:
        """True when the image orientation is (close to) axial."""
        if self.orientation is None or len(self.orientation) != 6:
            return False
        rx, ry, rz, cx, cy, cz = self.orientation
        normal_z = rx * cy - ry * cx
        return abs(abs(normal_z) - 1.0) < AXIAL_TOLERANCE and abs(rz) < 0.5 and abs(cz) < 0.5


def _text(value: object) -> str:
    return "" if value is None else str(value)


def discover_series(
    root: Path,
    stats: dict[str, int] | None = None,
    issue_types: dict[str, int] | None = None,
    *,
    progress: Progress | None = None,
) -> list[SeriesInfo]:
    """Read DICOM headers below *root* and group files by series.

    Non-DICOM files are skipped. The result is sorted by (study UID, series UID) so the
    discovery is deterministic.
    """
    groups: dict[str, SeriesInfo] = {}
    files_by_series: dict[str, list[Path]] = defaultdict(list)
    counts = stats if stats is not None else {}
    counts.update(files_scanned=0, headers_readable=0, headers_unreadable=0, non_dicom_files=0)
    emit_progress(progress, "discovery", 0, None)
    files = sorted(p for p in root.rglob("*") if p.is_file())
    emit_progress(progress, "discovery", 0, len(files))
    for completed, path in enumerate(files, 1):
        emit_progress(progress, "discovery", completed - 1, len(files))
        counts["files_scanned"] += 1
        ds = read_header(path, counts, issue_types)
        if ds is None:
            continue
        try:
            series_uid = _text(ds.get("SeriesInstanceUID"))
            orientation = ds.get("ImageOrientationPatient")
            thickness = ds.get("SliceThickness")
            info = SeriesInfo(
                study_uid=_text(ds.get("StudyInstanceUID")),
                series_uid=series_uid,
                patient_id=_text(ds.get("PatientID")),
                modality=_text(ds.get("Modality")).upper(),
                description=_text(ds.get("SeriesDescription")),
                image_type=tuple(str(v) for v in (ds.get("ImageType") or ())),
                slice_thickness=float(thickness) if thickness not in (None, "") else None,
                kernel=_text(ds.get("ConvolutionKernel")) or None,
                contrast=_text(ds.get("ContrastBolusAgent")) or None,
                orientation=tuple(float(v) for v in orientation) if orientation else None,
                manufacturer=_text(ds.get("Manufacturer")) or None,
            )
        except HEADER_ERRORS as error:
            record_header_error(error, issue_types)
            counts["headers_unreadable"] += 1
            continue
        counts["headers_readable"] += 1
        if not series_uid:
            continue
        files_by_series[series_uid].append(path)
        groups.setdefault(series_uid, info)
    emit_progress(progress, "discovery", len(files), len(files))
    for uid, info in groups.items():
        info.files = files_by_series[uid]
    return sorted(groups.values(), key=lambda s: (s.study_uid, s.series_uid))


@dataclass(frozen=True)
class SeriesSelection:
    """The chosen series plus the recorded reasons for every decision (Vision §9.1.7)."""

    series: SeriesInfo | None
    reason: str
    rejected: dict[str, str]


def select_series(candidates: list[SeriesInfo]) -> SeriesSelection:
    """Pick the intended chest CT series deterministically.

    Rules, in order: CT modality; not a localizer; at least ``MIN_SERIES_SLICES`` images;
    axial orientation; then prefer most images, then thinnest slices, then lowest series UID.
    """
    rejected: dict[str, str] = {}
    eligible: list[SeriesInfo] = []
    for s in candidates:
        if s.modality != "CT":
            rejected[s.series_uid] = f"modality {s.modality or 'unknown'} is not CT"
        elif s.is_localizer:
            rejected[s.series_uid] = "localizer/scout series"
        elif s.n_files < MIN_SERIES_SLICES:
            rejected[s.series_uid] = f"only {s.n_files} images (< {MIN_SERIES_SLICES})"
        elif not s.is_axial:
            rejected[s.series_uid] = "not an axial acquisition"
        else:
            eligible.append(s)
    if not eligible:
        return SeriesSelection(None, "no eligible axial CT series found", rejected)
    eligible.sort(key=lambda s: (-s.n_files, s.slice_thickness or 99.0, s.series_uid))
    chosen = eligible[0]
    for other in eligible[1:]:
        rejected[other.series_uid] = "eligible but ranked lower (fewer images / thicker slices)"
    reason = (
        f"axial CT with {chosen.n_files} images, slice thickness "
        f"{chosen.slice_thickness if chosen.slice_thickness is not None else 'unknown'} mm; "
        f"{len(eligible)} eligible of {len(candidates)} series"
    )
    return SeriesSelection(chosen, reason, rejected)
