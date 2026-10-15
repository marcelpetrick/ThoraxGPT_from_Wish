# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""License-, budget-, split- and checksum-gated acquisition of approved TCIA collections.

Order of gates (Vision §6, §8, §23; AGENTS.md non-negotiables 2-4):

1. Registry status must be ``approved*`` (:func:`require_acquirable`) — before any request.
2. The registry entry must name its own NBIA collection and license URL; every series
   must carry that exact license URI and collection, so terms are never inherited.
3. A frozen patient split forbids new patients; resuming a frozen selection is allowed.
4. The plan (pending bytes plus one ZIP in flight) must fit the data budget; each
   transfer is re-checked against the actual ``data/`` usage while it streams.
5. Archives are CRC-checked, NBIA MD5 lists are honoured, DICOM counts must match and
   every placed file is SHA-256 hashed into ``_sha256.txt``.

Raw data lands in ``data/raw/<dataset>/<PatientID>/<SeriesInstanceUID>/`` only.
"""

from __future__ import annotations

import json
import math
import os
import platform
import random
import re
import shutil
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx

from thoraxbench import __version__
from thoraxbench.acquisition.manifest import AcquisitionManifest, load_manifest, write_manifest
from thoraxbench.acquisition.nbia import (
    NBIA_BASE,
    SERIES_LIST,
    TCIA_UPLOADS,
    AcquisitionError,
    BudgetError,
    NbiaClient,
    SeriesRecord,
    default_client,
    nbia_url,
    now_utc,
)
from thoraxbench.acquisition.storage import (
    dataset_files,
    dicom_count,
    extract_lidc_xml,
    read_sha256_manifest,
    safe_extract,
    series_complete,
    sha256_file,
    usage_bytes,
    write_sha256_manifest,
)
from thoraxbench.config import Settings
from thoraxbench.registry import DatasetEntry, PolicyError, load_registry, require_acquirable
from thoraxbench.splits.split import Phase, load_split, split_paths

DEFAULT_SEED = 20261015
#: A ZIP from ``getImage`` is about half the unzipped size; 0.6 leaves headroom.
ZIP_FACTOR = 0.6
TCIA_POLICY_URL = "https://www.cancerimagingarchive.net/data-usage-policies-and-restrictions/"
SELECTION_RULE = (
    "Generic thoraxbench acquire selection: whole patients with series of the requested "
    "modalities, in a seeded pseudorandom patient order, until the patient limit or the data "
    "budget is reached. No label or finding is used for selection."
)
_LABEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]*$")

State = Literal["complete", "pending", "incomplete"]
Echo = Callable[[str], None]


@dataclass(frozen=True)
class AcquireOptions:
    """User choices for one acquisition run."""

    modalities: tuple[str, ...] = ("CT",)
    patients: int | None = None
    seed: int = DEFAULT_SEED
    dry_run: bool = False
    verify: bool = False


@dataclass(frozen=True)
class PlanItem:
    """One series of the plan and its local state."""

    series: SeriesRecord
    state: State


@dataclass(frozen=True)
class AcquisitionPlan:
    """What an acquisition run would do, with its budget verdict."""

    dataset: str
    collection: str
    items: tuple[PlanItem, ...]
    frozen_selection: bool
    usage_bytes: int
    budget_bytes: int

    def by_state(self, state: State) -> list[SeriesRecord]:
        """Series of the plan in *state*."""
        return [item.series for item in self.items if item.state == state]

    @property
    def estimate_bytes(self) -> int:
        """Unzipped bytes still to fetch plus one ZIP in flight."""
        sizes = [s.file_size for s in self.by_state("pending")]
        return sum(sizes) + math.ceil(ZIP_FACTOR * max(sizes, default=0))

    @property
    def fits(self) -> bool:
        """Whether the estimate fits into the remaining data budget."""
        return self.usage_bytes + self.estimate_bytes <= self.budget_bytes

    def summary_lines(self) -> list[str]:
        """Human-readable plan (series UIDs and sizes only, no patient IDs)."""
        patients = {item.series.patient_id for item in self.items}
        lines = [
            f"[{self.dataset}] NBIA collection '{self.collection}'"
            f" ({'frozen selection' if self.frozen_selection else 'new selection'})",
            f"  plan: {len(patients)} patient(s), {len(self.items)} series: "
            f"{len(self.by_state('complete'))} complete, {len(self.by_state('pending'))} "
            f"pending, {len(self.by_state('incomplete'))} incomplete",
        ]
        lines += [
            f"  {item.state:10} {item.series.modality:4} {item.series.file_size:>13,} B "
            f"{item.series.series_uid}"
            for item in self.items
            if item.state != "complete"
        ]
        verdict = "fits" if self.fits else "REFUSED: exceeds the data budget"
        lines.append(
            f"  estimate {self.estimate_bytes / 1e9:.2f} GB; data/ uses "
            f"{self.usage_bytes / 1e9:.2f} GB of {self.budget_bytes / 1e9:.2f} GB; {verdict}"
        )
        return lines


@dataclass
class AcquisitionReport:
    """Outcome of :func:`acquire`."""

    plan: AcquisitionPlan
    results: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    checksum_failures: list[str] = field(default_factory=list)
    manifest: AcquisitionManifest | None = None

    @property
    def ok(self) -> bool:
        """True when nothing failed and the plan was not refused."""
        return (
            self.plan.fits
            and not self.plan.by_state("incomplete")
            and not self.errors
            and not self.checksum_failures
            and "skipped_budget" not in self.results.values()
        )


# --------------------------------------------------------------------------- gates
def _normalise_uri(uri: str) -> str:
    text = uri.strip().lower()
    text = re.sub(r"^https?://", "", text)
    return text.removeprefix("www.").rstrip("/")


def resolve_source(entry: DatasetEntry) -> tuple[str, str]:
    """Return ``(nbia_collection, license_url)`` after the registry license gate.

    Raises:
        PolicyError: if the entry is not approved, names no NBIA collection or no license URL.
    """
    require_acquirable(entry)
    collection = entry.acquisition.get("nbia_collection")
    if not isinstance(collection, str) or not collection.strip():
        msg = (
            f"dataset '{entry.id}' has no 'acquisition.nbia_collection' in its registry entry; "
            "add the verified NBIA collection name before acquiring"
        )
        raise PolicyError(msg)
    if not entry.license_url:
        msg = f"dataset '{entry.id}' has no license_url to verify series licenses against"
        raise PolicyError(msg)
    return collection, entry.license_url


def check_series_licenses(series: list[SeriesRecord], collection: str, license_url: str) -> None:
    """Refuse series from another collection or under another license (no inheritance).

    Raises:
        PolicyError: on the first series whose collection or license URI differs.
    """
    expected = _normalise_uri(license_url)
    for record in series:
        if record.collection is not None and record.collection != collection:
            msg = f"series {record.series_uid} belongs to '{record.collection}', not '{collection}'"
            raise PolicyError(msg)
        if record.license_uri is None or _normalise_uri(record.license_uri) != expected:
            msg = (
                f"series {record.series_uid} has license URI {record.license_uri!r}; the "
                f"registry approves only {license_url}"
            )
            raise PolicyError(msg)


def split_frozen(settings: Settings, dataset: str) -> bool:
    """Whether a patient split exists (checks the committed and development files only)."""
    paths = split_paths(settings.data_dir, settings.manifests_dir, dataset)
    return paths["manifest"].exists() or paths["development"].exists()


def dataset_dir(settings: Settings, dataset: str) -> Path:
    """``data/raw/<dataset>``, refusing anything that resolves outside ``data/raw``.

    Raises:
        PolicyError: if the directory escapes ``data/raw`` or points into ``data/sealed``.
    """
    raw = settings.data_path("raw").resolve()
    sealed = settings.data_path("sealed").resolve()
    target = settings.data_path("raw", dataset).resolve()
    if target.parent != raw or target.is_relative_to(sealed):
        msg = f"acquisition target {target} is outside {raw}"
        raise PolicyError(msg)
    return target


# --------------------------------------------------------------------------- selection
def load_selection(path: Path) -> list[SeriesRecord] | None:
    """Series of a frozen ``_selection.json``, or ``None`` if there is none."""
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return SERIES_LIST.validate_python(payload["series"])


def select_series(
    rows: list[SeriesRecord], *, patients: int, seed: int, headroom: int
) -> list[SeriesRecord]:
    """Pick whole patients in seeded pseudorandom order within *headroom* bytes."""
    by_patient: dict[str, list[SeriesRecord]] = {}
    for record in rows:
        by_patient.setdefault(record.patient_id, []).append(record)
    order = sorted(by_patient)
    random.Random(seed).shuffle(order)  # noqa: S311 - deterministic sampling, not security
    chosen: list[SeriesRecord] = []
    total = 0
    largest = 0
    taken = 0
    for patient in order:
        if taken >= patients:
            break
        group = by_patient[patient]
        size = sum(s.file_size for s in group)
        peak = max(largest, *(s.file_size for s in group))
        if total + size + math.ceil(ZIP_FACTOR * peak) > headroom:
            continue
        chosen.extend(group)
        total += size
        largest = peak
        taken += 1
    return sorted(chosen, key=lambda s: (s.patient_id, s.modality, s.series_uid))


def _write_selection(path: Path, series: list[SeriesRecord], seed: int) -> None:
    payload = {
        "created_at": now_utc(),
        "seed": seed,
        "rule": SELECTION_RULE,
        "series": [s.model_dump(by_alias=True, exclude_none=True) for s in series],
    }
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")


def build_plan(
    entry: DatasetEntry,
    settings: Settings,
    options: AcquireOptions,
    nbia: NbiaClient,
) -> AcquisitionPlan:
    """Apply every gate and return the plan; never downloads image data.

    Raises:
        PolicyError: for license, split or path violations.
        ValueError: if a new selection is needed but no patient limit was given.
    """
    collection, license_url = resolve_source(entry)
    ds_dir = dataset_dir(settings, entry.id)
    frozen_split = split_frozen(settings, entry.id)
    usage = _usage(settings)
    series = load_selection(ds_dir / "_selection.json")
    frozen_selection = series is not None
    if series is None:
        if frozen_split:
            msg = (
                f"dataset '{entry.id}' already has a frozen patient split but no frozen "
                "selection; new patients would bypass the sealed split"
            )
            raise PolicyError(msg)
        if options.patients is None:
            msg = "a new selection needs --patients N (the number of patients to acquire)"
            raise ValueError(msg)
        rows = [r for m in options.modalities for r in nbia.get_series(collection, m)]
        check_series_licenses(rows, collection, license_url)
        series = select_series(
            rows,
            patients=options.patients,
            seed=options.seed,
            headroom=settings.data_budget_bytes - usage,
        )
    check_series_licenses(series, collection, license_url)
    items: list[PlanItem] = []
    for record in series:
        target = ds_dir / record.patient_id / record.series_uid
        state: State = "pending"
        if series_complete(target, record.image_count):
            state = "complete"
        elif target.exists():
            state = "incomplete"
        elif frozen_split and not (ds_dir / record.patient_id).is_dir():
            msg = (
                f"patient of series {record.series_uid} is not part of the frozen split of "
                f"'{entry.id}'; adding patients after the split is refused"
            )
            raise PolicyError(msg)
        items.append(PlanItem(series=record, state=state))
    return AcquisitionPlan(
        dataset=entry.id,
        collection=collection,
        items=tuple(items),
        frozen_selection=frozen_selection,
        usage_bytes=usage,
        budget_bytes=settings.data_budget_bytes,
    )


def _usage(settings: Settings) -> int:
    return usage_bytes(settings.data_dir)


# --------------------------------------------------------------------------- download
def _fetch_series(
    nbia: NbiaClient, ds_dir: Path, record: SeriesRecord, settings: Settings
) -> dict[str, str]:
    target = ds_dir / record.patient_id / record.series_uid
    part = ds_dir / ".partial" / record.series_uid
    shutil.rmtree(part, ignore_errors=True)
    part.mkdir(parents=True)
    headroom = settings.data_budget_bytes - _usage(settings)
    if record.file_size + math.ceil(ZIP_FACTOR * record.file_size) > headroom:
        msg = f"series {record.series_uid} does not fit the remaining data budget"
        raise BudgetError(msg)
    archive = part / "series.zip"
    nbia.download(
        nbia_url("getImage", SeriesInstanceUID=record.series_uid),
        archive,
        max_bytes=headroom - record.file_size,
    )
    extracted = part / "x"
    safe_extract(archive, extracted, max_bytes=headroom - archive.stat().st_size)
    archive.unlink()
    found = dicom_count(extracted)
    if found != record.image_count:
        msg = (
            f"series {record.series_uid}: got {found} DICOM file(s), expected {record.image_count}"
        )
        raise AcquisitionError(msg)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(extracted, target)
    shutil.rmtree(part, ignore_errors=True)
    return {
        path.relative_to(ds_dir).as_posix(): sha256_file(path)
        for path in sorted(target.rglob("*"))
        if path.is_file()
    }


def _fetch_labels(
    nbia: NbiaClient, entry: DatasetEntry, ds_dir: Path, settings: Settings
) -> tuple[list[str], list[str]]:
    names = entry.acquisition.get("label_files", [])
    if not isinstance(names, list):
        return [], [f"acquisition.label_files of '{entry.id}' must be a list"]
    urls: list[str] = []
    errors: list[str] = []
    for name in names:
        if not isinstance(name, str) or not _LABEL_NAME.fullmatch(name):
            errors.append(f"refusing unsafe label file name {name!r}")
            continue
        url = f"{TCIA_UPLOADS}/{name}"
        urls.append(url)
        dest = ds_dir / "_labels" / name
        if dest.exists():
            continue
        partial = dest.with_name(dest.name + ".part")
        try:
            nbia.download(url, partial, max_bytes=settings.data_budget_bytes - _usage(settings))
        except (AcquisitionError, BudgetError, OSError) as exc:
            errors.append(f"label file {name}: {exc}")
            continue
        os.replace(partial, dest)
    return urls, errors


def _license_snapshot(entry: DatasetEntry, ds_dir: Path, license_url: str) -> Path:
    path = ds_dir / "_LICENSE_SNAPSHOT.txt"
    if path.exists():
        return path
    parts = [
        f"# License snapshot for {entry.name}",
        f"# fetched_at: {now_utc()}",
        f"# license: {entry.license}  {license_url}",
        f"# collection page: {entry.source_url}",
        f"# DOI: https://doi.org/{entry.doi}" if entry.doi else "# DOI: none",
        f"# TCIA data usage policy: {TCIA_POLICY_URL}",
        "",
    ]
    shipped = next(iter(sorted(ds_dir.glob("*/*/LICENSE"))), None)
    if shipped is not None:
        parts += [
            "===== LICENSE file shipped inside the NBIA getImage archive =====",
            shipped.read_text(encoding="utf-8", errors="ignore"),
        ]
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- checksums
def _development_patients(settings: Settings, dataset: str) -> frozenset[str] | None:
    """Development patient IDs of a frozen split, or ``None`` when no split exists.

    Only the development file is loaded; sealed IDs are never read.
    """
    if not split_frozen(settings, dataset):
        return None
    split = load_split(settings.data_dir, settings.manifests_dir, dataset, include_sealed=False)
    return frozenset(split.patient_of[c] for c in split.cases(Phase.DEVELOPMENT))


def _outside_scope(rel: str, scope: frozenset[str] | None) -> bool:
    """Report whether *rel* lies in a patient directory outside the development scope."""
    head, sep, _ = rel.partition("/")
    return scope is not None and bool(sep) and not head.startswith("_") and head not in scope


def _update_checksums(
    ds_dir: Path,
    new_hashes: dict[str, str],
    *,
    verify: bool,
    scope: frozenset[str] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Merge new hashes and optionally re-verify listed files.

    With a frozen split, *scope* holds the development patients; files of all other
    patients (the sealed holdout) are never opened for hashing or verification.
    """
    sha_path = ds_dir / "_sha256.txt"
    entries = read_sha256_manifest(sha_path)
    known = set(entries)
    entries.update(new_hashes)
    present = {p.relative_to(ds_dir).as_posix(): p for p in dataset_files(ds_dir)}
    failures = [f"missing listed file {rel}" for rel in sorted(set(entries) - set(present))]
    for rel, path in present.items():
        if rel not in new_hashes and _outside_scope(rel, scope):
            continue
        if rel not in entries:
            entries[rel] = sha256_file(path)
        elif (
            verify and rel in known and rel not in new_hashes and sha256_file(path) != entries[rel]
        ):
            failures.append(f"SHA-256 mismatch for {rel}")
    return entries, failures


def _build_manifest(
    entry: DatasetEntry,
    *,
    plan: AcquisitionPlan,
    ds_dir: Path,
    entries: dict[str, str],
    results: dict[str, str],
    label_urls: list[str],
    license_url: str,
) -> AcquisitionManifest:
    prev = load_manifest(ds_dir / "_acquisition.json")
    stamp = now_utc()
    counts = dict(sorted(Counter(results.values()).items()))
    series = [item.series for item in plan.items]
    selection = json.loads((ds_dir / "_selection.json").read_text(encoding="utf-8"))
    snapshot = ds_dir / "_LICENSE_SNAPSHOT.txt"
    api: dict[str, object] = dict(prev.api) if prev else {}
    api.setdefault(
        "endpoints_used",
        [
            *(
                nbia_url("getSeries", Collection=plan.collection, Modality=m)
                for m in sorted({s.modality for s in series})
            ),
            f"{NBIA_BASE}/getImage?SeriesInstanceUID=<uid>",
        ],
    )
    previous_labels = api.get("label_urls")
    old_labels = (
        [u for u in previous_labels if isinstance(u, str)]
        if isinstance(previous_labels, list)
        else []
    )
    api.update(
        base=NBIA_BASE,
        label_urls=sorted(set(old_labels) | set(label_urls)),
        series_urls=[nbia_url("getImage", SeriesInstanceUID=s.series_uid) for s in series],
        full_call_log="_api_log.jsonl",
    )
    run = f"{stamp} thoraxbench acquire: " + (
        ", ".join(f"{k}={v}" for k, v in counts.items()) or "nothing to do"
    )
    history = f"{prev.run_history}; {run}" if prev and prev.run_history else run
    text = snapshot.read_text(encoding="utf-8")
    return AcquisitionManifest(
        dataset=entry.id,
        collection=plan.collection,
        provider=prev.provider if prev else f"{entry.provider} via NBIA",
        source_url=entry.source_url,
        doi=prev.doi if prev else (f"https://doi.org/{entry.doi}" if entry.doi else None),
        source_version=(
            prev.source_version if prev else str(entry.acquisition.get("source_version", ""))
        ),
        downloaded_at=(stamp if prev is None or counts.get("downloaded") else prev.downloaded_at),
        verified_at=stamp,
        files=len(entries),
        total_bytes=sum((ds_dir / rel).stat().st_size for rel in entries),
        patients=len({s.patient_id for s in series}),
        series=len(series),
        series_by_modality=dict(sorted(Counter(s.modality for s in series).items())),
        sha256_manifest="_sha256.txt",
        sha256_manifest_sha256=sha256_file(ds_dir / "_sha256.txt"),
        license=entry.license,
        license_snapshot={
            "file": snapshot.name,
            "sha256": sha256_file(snapshot),
            "license_url": license_url,
            "policy_url": TCIA_POLICY_URL,
            "collection_page": entry.source_url,
            "text_excerpt": text[:3000],
        },
        tool_version=(
            f"thoraxbench {__version__} acquire; python {platform.python_version()}; "
            f"httpx {httpx.__version__}"
        ),
        selection={
            "file": "_selection.json",
            "seed": selection.get("seed"),
            "rule": selection.get("rule"),
        },
        api=api,
        previous_run_results=prev.run_results if prev else None,
        run_results=counts,
        run_history=history,
    )


# --------------------------------------------------------------------------- entry point
def acquire(
    dataset: str,
    settings: Settings,
    options: AcquireOptions,
    *,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
    echo: Echo = print,
) -> AcquisitionReport:
    """Plan and (unless ``dry_run``) acquire *dataset* into ``data/raw/<dataset>``.

    Raises:
        KeyError: for an unknown dataset id.
        PolicyError: when a license, split, path or (whole-plan) budget gate refuses.
        ValueError: if a new selection is needed but ``options.patients`` is missing.
    """
    registry = load_registry(settings.configs_dir / "datasets")
    if dataset not in registry:
        msg = f"unknown dataset '{dataset}'"
        raise KeyError(msg)
    entry = registry[dataset]
    _, license_url = resolve_source(entry)  # gate before any client is created
    ds_dir = dataset_dir(settings, dataset)
    owned = client is None
    http = default_client() if client is None else client
    try:
        log_path = ds_dir / "_api_log.jsonl"

        def log(record: dict[str, object]) -> None:
            ds_dir.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")

        nbia = NbiaClient(http, sleep=sleep, log=None if options.dry_run else log)
        plan = build_plan(entry, settings, options, nbia)
        for line in plan.summary_lines():
            echo(line)
        if plan.frozen_selection and options.patients is not None:
            echo("  note: frozen _selection.json reused; --patients is ignored")
        report = AcquisitionReport(plan=plan)
        if options.dry_run:
            return report
        if not plan.fits:
            msg = (
                f"plan for '{dataset}' needs {plan.estimate_bytes / 1e9:.2f} GB but only "
                f"{(plan.budget_bytes - plan.usage_bytes) / 1e9:.2f} GB of the data budget remain"
            )
            raise BudgetError(msg)
        _run(
            entry,
            plan=plan,
            settings=settings,
            options=options,
            nbia=nbia,
            ds_dir=ds_dir,
            license_url=license_url,
            report=report,
            echo=echo,
        )
        return report
    finally:
        if owned:
            http.close()


def _run(
    entry: DatasetEntry,
    *,
    plan: AcquisitionPlan,
    settings: Settings,
    options: AcquireOptions,
    nbia: NbiaClient,
    ds_dir: Path,
    license_url: str,
    report: AcquisitionReport,
    echo: Echo,
) -> None:
    ds_dir.mkdir(parents=True, exist_ok=True)
    (ds_dir / "_labels").mkdir(exist_ok=True)
    if not plan.frozen_selection:
        _write_selection(ds_dir / "_selection.json", [i.series for i in plan.items], options.seed)
    new_hashes: dict[str, str] = {}
    budget_stop = False
    for number, item in enumerate(plan.items, 1):
        uid = item.series.series_uid
        if item.state == "complete":
            status = "skipped_complete"
        elif item.state == "incomplete":
            status = "error"
            report.errors.append(
                f"series {uid} exists but is incomplete; raw data is immutable — remove "
                "that series directory manually and re-run"
            )
        elif budget_stop:
            status = "skipped_budget"
        else:
            try:
                new_hashes.update(_fetch_series(nbia, ds_dir, item.series, settings))
                status = "downloaded"
            except BudgetError as exc:
                status, budget_stop = "skipped_budget", True
                report.errors.append(str(exc))
            except (AcquisitionError, OSError) as exc:
                status = "error"
                report.errors.append(f"series {uid}: {exc}")
        report.results[uid] = status
        if item.state != "complete":
            echo(f"  [{number}/{len(plan.items)}] {item.series.modality} {uid} {status}")
    shutil.rmtree(ds_dir / ".partial", ignore_errors=True)
    label_urls, label_errors = _fetch_labels(nbia, entry, ds_dir, settings)
    report.errors.extend(label_errors)
    archive = entry.acquisition.get("lidc_xml_archive")
    if isinstance(archive, str) and (ds_dir / "_labels" / archive).is_file():
        complete = {
            s.series_uid
            for s in (i.series for i in plan.items)
            if series_complete(ds_dir / s.patient_id / s.series_uid, s.image_count)
        }
        matched, written = extract_lidc_xml(ds_dir, archive, complete)
        new_hashes.update({p.relative_to(ds_dir).as_posix(): sha256_file(p) for p in written})
        echo(f"  reader XML matched for {len(matched)}/{len(complete)} complete series")
    _license_snapshot(entry, ds_dir, license_url)
    entries, failures = _update_checksums(
        ds_dir,
        new_hashes,
        verify=options.verify,
        scope=_development_patients(settings, entry.id),
    )
    report.checksum_failures.extend(failures)
    if failures:
        echo("  checksum verification FAILED; manifests left unchanged")
        return
    write_sha256_manifest(ds_dir / "_sha256.txt", entries)
    manifest = _build_manifest(
        entry,
        plan=plan,
        ds_dir=ds_dir,
        entries=entries,
        results=report.results,
        label_urls=label_urls,
        license_url=license_url,
    )
    write_manifest(
        manifest,
        ds_dir / "_acquisition.json",
        settings.manifests_dir / "datasets" / f"{entry.id}.json",
    )
    report.manifest = manifest
    echo(
        f"[{entry.id}] manifest: {manifest.files} file(s), {manifest.total_bytes / 1e9:.2f} GB; "
        f"sha256 manifest {manifest.sha256_manifest_sha256[:12]}"
    )
