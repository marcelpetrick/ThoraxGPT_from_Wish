# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Inspect one local DICOM file without printing identifying values or image bytes."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import logging
import math
import platform
import sys
import time
import warnings
from collections import Counter
from pathlib import Path
from typing import Any, Never

try:
    import pydicom
    from pydicom.datadict import dictionary_keyword, dictionary_VR
    from pydicom.dataelem import RawDataElement
    from pydicom.dataset import Dataset
    from pydicom.tag import BaseTag
except ModuleNotFoundError:
    sys.stderr.write(
        "Missing dependencies. Run: uv run --no-sync python scripts/dcom_evaluator.py --help\n"
    )
    raise SystemExit(2) from None

from thoraxbench import __version__
from thoraxbench.api.local_studies import SourceChangedError, source_signature
from thoraxbench.config import get_settings
from thoraxbench.dicom.volume import (
    MAX_ADEQUATE_GAP_MM,
    MIN_ADEQUATE_COVERAGE_MM,
    MIN_ADEQUATE_SLICES,
    MIN_LUNG_FRACTION,
    QCReport,
)
from thoraxbench.splits import SealedAccessError
from thoraxbench.study import StudyLoadError, load_study_dir
from thoraxbench.study_access import (
    StudyPathGuard,
    guard_patient_identity,
    guard_study_input,
    guard_study_path,
    public_split_manifests,
)

DISCLAIMER = (
    "Research use only. Self-made experimental diagnostic helper; not medical advice or "
    "a diagnosis. No identifying values are intentionally printed. Review output before sharing; "
    "this is not an anonymization guarantee."
)
MAX_ELEMENTS = 20000
MAX_DEPTH = 8
TECHNICAL_NUMBERS = (
    "Rows",
    "Columns",
    "NumberOfFrames",
    "SamplesPerPixel",
    "PlanarConfiguration",
    "BitsAllocated",
    "BitsStored",
    "HighBit",
    "PixelRepresentation",
    "PixelSpacing",
    "SliceThickness",
    "SpacingBetweenSlices",
    "RescaleSlope",
    "RescaleIntercept",
    "ImageOrientationPatient",
)


def numeric(value: Any) -> int | float | list[int | float] | None:
    """Only bounded finite numbers; never serialize arbitrary header text."""
    if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
        if len(value) > 16:
            return None
        items = [numeric(item) for item in value]
        if any(item is None or isinstance(item, list) for item in items):
            return None
        return [item for item in items if isinstance(item, (int, float))]
    try:
        number = float(value)
    except TypeError, ValueError, OverflowError:
        return None
    return number if math.isfinite(number) else None


def raw_context(header: Dataset, tag: BaseTag) -> dict[str, Any]:
    """Describe representation and lengths without converting or printing values."""
    raw = header.get_item(tag, keep_deferred=True)
    context: dict[str, Any] = {"tag": f"({tag.group:04X},{tag.element:04X})"}
    # Dictionary names are standard metadata; never echo private creator names.
    if not tag.is_private:
        try:
            context["keyword"] = dictionary_keyword(tag)
            context["dictionary_vr"] = dictionary_VR(tag)
        except KeyError:
            context["keyword"] = ""
    if isinstance(raw, RawDataElement):
        context["vr"] = raw.VR
        context["declared_length"] = raw.length
        multiples = {
            "US": 2,
            "SS": 2,
            "OW": 2,
            "UL": 4,
            "SL": 4,
            "FL": 4,
            "AT": 4,
            "OL": 4,
            "OF": 4,
            "FD": 8,
            "SV": 8,
            "UV": 8,
            "OD": 8,
            "OV": 8,
        }
        if raw.VR in multiples:
            context["required_byte_multiple"] = multiples[raw.VR]
        if isinstance(raw.value, bytes):
            context["available_value_bytes"] = len(raw.value)
    return context


def inspect_header(dataset: Dataset) -> dict[str, Any]:
    """Convert elements individually, retaining tag/VR/length rather than bad values."""
    errors: list[dict[str, Any]] = []
    counts = {"elements_checked": 0, "private_elements": 0, "errors": 0}
    truncated = False

    def walk(header: Dataset, depth: int) -> None:
        nonlocal truncated
        if depth > MAX_DEPTH:
            truncated = True
            return
        for tag in sorted(header.keys()):
            if int(tag) in {0x7FE00008, 0x7FE00009, 0x7FE00010}:
                continue
            if counts["elements_checked"] >= MAX_ELEMENTS:
                truncated = True
                return
            counts["elements_checked"] += 1
            counts["private_elements"] += int(tag.is_private)
            context = raw_context(header, tag)
            try:
                element = header[tag]
                if element.VR == "SQ":
                    for item in element.value:
                        walk(item, depth + 1)
            except Exception as error:
                counts["errors"] += 1
                if len(errors) < 100:
                    errors.append(context | {"exception_type": type(error).__name__})

    walk(dataset, 0)
    if getattr(dataset, "file_meta", None) is not None:
        walk(dataset.file_meta, 0)
    return counts | {"conversion_errors": errors, "truncated": truncated}


def technical_metadata(dataset: Dataset) -> dict[str, Any]:
    """Read an explicit technical allowlist; omit identifiers, dates and free text."""
    result: dict[str, Any] = {}
    for key in TECHNICAL_NUMBERS:
        try:
            numeric_value = numeric(dataset.get(key))
            if numeric_value is not None:
                result[key] = numeric_value
        except Exception:
            result[f"{key}_unreadable"] = True
    for key, allowed in (
        ("Modality", {"CT", "MR", "CR", "DX", "PT", "US", "OT"}),
        (
            "PhotometricInterpretation",
            {"MONOCHROME1", "MONOCHROME2", "RGB", "YBR_FULL", "YBR_FULL_422", "PALETTE COLOR"},
        ),
    ):
        try:
            value = str(dataset.get(key, ""))
            if value in allowed:
                result[key] = value
        except Exception:
            result[f"{key}_unreadable"] = True
    try:
        syntax = dataset.file_meta.TransferSyntaxUID
        if syntax.is_transfer_syntax and syntax.is_valid:
            result["transfer_syntax_uid"] = str(syntax)
            result["transfer_syntax_name"] = syntax.name
            result["compressed"] = syntax.is_compressed
    except Exception:
        result["transfer_syntax_available"] = False
    # Presence flags explain redaction; the original values never leave memory.
    result["identifier_values_omitted"] = True
    return result


def runtime_report(*, check_pixels: bool = False) -> dict[str, Any]:
    """Collect software identity once per invocation, independent of file count."""
    result: dict[str, Any] = {
        "tool": "dcom_evaluator",
        "schema_version": 1,
        "disclaimer": DISCLAIMER,
        "runtime": {
            "python": platform.python_version(),
            "pydicom": pydicom.__version__,
            "thoraxbench": __version__,
        },
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "pixels_requested": check_pixels,
        "decoder_packages": {},
    }
    for package in (
        "pillow",
        "pylibjpeg",
        "pylibjpeg-libjpeg",
        "pylibjpeg-openjpeg",
        "pyjpegls",
        "gdcm",
    ):
        try:
            result["decoder_packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result["decoder_packages"][package] = None
    return result


def evaluate(path: Path, *, check_pixels: bool = False) -> dict[str, Any]:
    """Read exactly one operator-selected file; never traverse its parent folder."""
    result = runtime_report(check_pixels=check_pixels)
    logger = logging.getLogger("pydicom")
    previous = logger.disabled
    logger.disabled = True
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            settings = get_settings()
            identity = guard_study_path(path, settings)
            result["file_size_bytes"] = path.stat().st_size
            with path.open("rb") as stream:
                result["dicm_marker_present"] = stream.read(132)[128:132] == b"DICM"
            dataset = pydicom.dcmread(path, stop_before_pixels=True, force=False)
            result["header"] = inspect_header(dataset)
            try:
                patient = str(dataset.get("PatientID", ""))
            except Exception:
                result["split_identity_checked"] = False
            else:
                guard_patient_identity(patient, identity, public_split_manifests(settings))
                result["split_identity_checked"] = True
            result["technical"] = technical_metadata(dataset)
            result["status"] = (
                "header_errors"
                if result["header"]["errors"]
                else "header_incomplete"
                if result["header"]["truncated"]
                else "header_readable"
            )
            if check_pixels and result["status"] != "header_readable":
                result["pixels"] = {"decoded": False, "exception_type": "HeaderValidationError"}
            if check_pixels and result["status"] == "header_readable":
                try:
                    # Explicit opt-in: decode locally, print shape/type only, never pixels.
                    pixels = pydicom.dcmread(path, force=False).pixel_array
                    result["pixels"] = {
                        "decoded": True,
                        "shape": list(pixels.shape),
                        "dtype": str(pixels.dtype),
                    }
                except Exception as error:
                    result["pixels"] = {"decoded": False, "exception_type": type(error).__name__}
                    result["status"] = "pixel_error"
        except Exception as error:
            result["status"] = "read_error"
            result["error"] = {"exception_type": type(error).__name__}
        finally:
            logger.disabled = previous
        result["warning_categories"] = sorted({type(item.message).__name__ for item in caught})
        result["warning_count"] = len(caught)
    return result


def orientation_name(dataset: Dataset) -> str:
    """Classify only geometric plane direction; never return header strings."""
    values = numeric(dataset.get("ImageOrientationPatient"))
    if not isinstance(values, list) or len(values) != 6:
        return "unknown"
    row, column = values[:3], values[3:]
    normal = [
        row[1] * column[2] - row[2] * column[1],
        row[2] * column[0] - row[0] * column[2],
        row[0] * column[1] - row[1] * column[0],
    ]
    length = math.sqrt(sum(value * value for value in normal))
    if not length:
        return "unknown"
    axis = max(range(3), key=lambda index: abs(normal[index]))
    return (
        ("sagittal", "coronal", "axial")[axis] if abs(normal[axis]) / length >= 0.9 else "oblique"
    )


def scan_headers(  # noqa: PLR0912, PLR0915 - bounded guarded traversal owns one scan lifecycle
    folder: Path,
    *,
    max_files: int = 10000,
    max_seconds: float = 300,
    progress: bool = False,
) -> dict[str, Any]:
    """Scan operator-selected headers with bounded anonymous error/series aggregates."""
    result = runtime_report()
    counts = {
        "scanned": 0,
        "readable": 0,
        "header_errors": 0,
        "read_errors": 0,
        "non_dicom": 0,
        "symlinks_skipped": 0,
        "protected_paths": 0,
    }
    groups: Counter[str] = Counter()
    series: dict[tuple[str, str, str], dict[str, Any]] = {}
    series_ids: dict[str, int] = {}
    other_errors: Counter[str] = Counter()
    start = time.monotonic()
    result.update(mode="scan_headers", counts=counts, status="scan_complete", truncated=False)
    if max_files < 1 or not math.isfinite(max_seconds) or max_seconds <= 0:
        result.update(status="read_error", error={"exception_type": "InvalidScanLimit"})
        return result
    logger = logging.getLogger("pydicom")
    previous = logger.disabled
    logger.disabled = True
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            settings = get_settings()
            access = StudyPathGuard(settings)
            access.check(folder)
            if folder.is_symlink():
                counts["symlinks_skipped"] += 1
            elif not folder.is_dir():
                raise NotADirectoryError
            else:
                manifests = public_split_manifests(settings)
                pending = [folder]
                stopped = False
                while pending and not stopped:
                    directory = pending.pop()
                    access.check(directory)
                    for path in sorted(directory.iterdir()):
                        if (
                            counts["scanned"] >= max_files
                            or time.monotonic() - start >= max_seconds
                        ):
                            result.update(truncated=True, status="scan_truncated")
                            stopped = True
                            break
                        identity = access.check(path)
                        if path.is_symlink():
                            counts["symlinks_skipped"] += 1
                            continue
                        if path.is_dir():
                            pending.append(path)
                            continue
                        if not path.is_file():
                            continue
                        counts["scanned"] += 1
                        try:
                            dataset = pydicom.dcmread(path, stop_before_pixels=True, force=False)
                            # Check copied sealed identity before inspecting additional values.
                            try:
                                patient = str(dataset.get("PatientID", ""))
                            except Exception:
                                patient = None
                            if patient is not None:
                                guard_patient_identity(patient, identity, manifests)
                            header = inspect_header(dataset)
                            if header["errors"] or header["truncated"]:
                                counts["header_errors"] += 1
                                for error in header["conversion_errors"]:
                                    group_key = json.dumps(error, sort_keys=True)
                                    if group_key in groups or len(groups) < 1000:
                                        groups[group_key] += 1
                                    else:
                                        other_errors["ErrorGroupLimit"] += 1
                                if header["truncated"]:
                                    other_errors["HeaderInspectionLimit"] += 1
                            else:
                                counts["readable"] += 1
                                modality = str(dataset.get("Modality", ""))
                                modality = (
                                    modality
                                    if modality in {"CT", "MR", "CR", "DX", "PT", "US", "OT", "SEG"}
                                    else "unknown"
                                )
                                plane = orientation_name(dataset)
                                key = (str(dataset.get("SeriesInstanceUID", "")), modality, plane)
                                if key not in series:
                                    series[key] = {
                                        "series": (
                                            series_ids.setdefault(key[0], len(series_ids) + 1)
                                            if key[0]
                                            else None
                                        ),
                                        "modality": modality,
                                        "orientation": plane,
                                        "readable_files": 0,
                                    }
                                series[key]["readable_files"] += 1
                        except pydicom.errors.InvalidDicomError:
                            counts["non_dicom"] += 1
                        except PermissionError:
                            raise
                        except Exception as error:
                            counts["read_errors"] += 1
                            other_errors[type(error).__name__] += 1
                        if progress and counts["scanned"] % 100 == 0:
                            print(
                                json.dumps(
                                    {
                                        "event": "header_scan",
                                        **counts,
                                        "elapsed_s": round(time.monotonic() - start, 3),
                                    }
                                ),
                                file=sys.stderr,
                            )
        except Exception as error:
            if isinstance(error, PermissionError):
                counts["protected_paths"] += 1
            result.update(status="read_error", error={"exception_type": type(error).__name__})
        finally:
            logger.disabled = previous
        result["warning_categories"] = sorted({type(item.message).__name__ for item in caught})
        result["warning_count"] = len(caught)
    result["error_groups"] = [
        json.loads(key) | {"count": count} for key, count in groups.most_common(100)
    ]
    result["error_groups_truncated"] = len(groups) > 100 or bool(other_errors["ErrorGroupLimit"])
    result["other_error_types"] = [
        {"exception_type": key, "count": count} for key, count in other_errors.most_common(10)
    ]
    result["series"] = list(series.values())
    result["elapsed_s"] = round(time.monotonic() - start, 3)
    return result


def qc_limitation_codes(qc: QCReport) -> list[str]:
    """Use the engine thresholds but report fixed codes instead of header-derived text."""
    conditions = [
        (qc.n_slices < MIN_ADEQUATE_SLICES, "too_few_axial_slices"),
        (qc.axial_coverage_mm < MIN_ADEQUATE_COVERAGE_MM, "limited_axial_coverage"),
        (max(qc.gaps_mm, default=0.0) > MAX_ADEQUATE_GAP_MM, "large_slice_gap"),
        (qc.lung_voxel_fraction < MIN_LUNG_FRACTION, "little_aerated_lung"),
        (bool(qc.warnings), "input_qc_warnings"),
    ]
    return [name for condition, name in conditions if condition]


def evaluate_import(folder: Path, *, progress: bool = False) -> dict[str, Any]:
    """Explicitly exercise app import/geometry/QC, without models, renders or exports."""
    result: dict[str, Any] = {"status": "failed", "stage": "folder_check"}
    started = time.monotonic()

    def stage(name: str) -> None:
        result["stage"] = name
        if progress:
            print(json.dumps({"event": "import_stage", "stage": name}), file=sys.stderr)

    stage("folder_check")
    logger = logging.getLogger("pydicom")
    previous = logger.disabled
    logger.disabled = True
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            settings = get_settings()
            identity = guard_study_input(folder, settings)
            signature = source_signature(folder, settings)
            stage("study")
            study = load_study_dir(folder, dataset=identity[0], case_id=identity[1])
            stage("source_recheck")
            guard_study_input(folder, settings)
            if source_signature(folder, settings) != signature:
                raise SourceChangedError("source changed while loading")
            qc = study.qc
            limitations = qc_limitation_codes(qc)
            result.update(
                status="succeeded",
                selected_slices=study.volume.shape[0],
                spacing_mm=numeric(study.volume.spacing_mm),
                qc_adequate=qc.adequate,
                limitations=limitations,
                discovery={
                    key: value
                    for key, value in study.selection.get("discovery", {}).items()
                    if key
                    in {
                        "files_scanned",
                        "headers_readable",
                        "headers_unreadable",
                        "non_dicom_files",
                    }
                    and type(value) is int
                    and value >= 0
                },
            )
            stage("done")
        except Exception as error:
            code = "import_error"
            if isinstance(error, SealedAccessError):
                code = "sealed_input"
            elif isinstance(error, SourceChangedError):
                code = "source_changed"
            elif isinstance(error, StudyLoadError):
                code = "no_eligible_ct"
            elif getattr(error, "code", None) == "dicom_read_error":
                code = "dicom_read_error"
            result["error"] = {"exception_type": type(error).__name__, "code": code}
        finally:
            logger.disabled = previous
        result["warning_count"] = len(caught)
        result["warning_categories"] = sorted({type(item.message).__name__ for item in caught})
    result["elapsed_s"] = round(time.monotonic() - started, 3)
    if progress:
        print(json.dumps({"event": "import_finished", **result}), file=sys.stderr)
    return result


class SafeArgumentParser(argparse.ArgumentParser):
    """Keep accidentally unquoted identifying filenames out of parser errors."""

    def error(self, message: str) -> Never:
        """Use fixed text instead of echoing any command-line argument."""
        self.exit(2, "Argument error: provide exactly one quoted file path. Use --help.\n")


def main() -> int:
    """Print one privacy-bounded JSON document and a useful exit status."""
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument(
        "file", type=Path, help="One file, or a folder with --scan-headers; suffixes optional."
    )
    parser.add_argument(
        "--scan-headers", action="store_true", help="Scan folder headers only; no pixels."
    )
    parser.add_argument(
        "--max-files", type=int, default=10000, help="Maximum files scanned (default 10000)."
    )
    parser.add_argument("--max-seconds", type=float, default=300, help="Maximum scan wall seconds.")
    parser.add_argument(
        "--progress", action="store_true", help="Aggregate scan counters on stderr."
    )
    parser.add_argument(
        "--check-pixels",
        action="store_true",
        help="Opt in to local pixel decoding; print shape/type only.",
    )
    parser.add_argument(
        "--check-import",
        action="store_true",
        help="With --scan-headers, explicitly load local pixels and run app import/QC; no model.",
    )
    args = parser.parse_args()
    if args.check_import and not args.scan_headers:
        parser.error("check-import requires scan-headers")
    if args.scan_headers and args.check_pixels:
        parser.error("incompatible options")
    result = (
        scan_headers(
            args.file,
            max_files=args.max_files,
            max_seconds=args.max_seconds,
            progress=args.progress,
        )
        if args.scan_headers
        else evaluate(args.file, check_pixels=args.check_pixels)
    )
    if args.check_import:
        result["pixels_requested"] = True
        result["import"] = (
            evaluate_import(args.file, progress=args.progress)
            if result["status"] == "scan_complete"
            else {"status": "not_run", "reason": "scan_not_complete"}
        )
        if result["import"]["status"] == "failed":
            result["status"] = "import_failed"
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["status"] in {"header_readable", "scan_complete"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
