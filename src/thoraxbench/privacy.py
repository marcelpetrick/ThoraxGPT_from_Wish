# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""DICOM de-identification audit and output redaction (Vision §29).

The audit follows the idea of the DICOM PS3.15 *Basic Application Level Confidentiality
Profile*: it reads headers only and flags attributes that the profile removes or empties
when they are present with a non-empty value. It reports tag keywords, tag numbers,
categories and file counts. It never reports, stores or returns the header values.

The audit is a report, not a gate. Public research collections often keep pseudonymous
patient IDs, shifted dates or private tags on purpose. The split guards in
:mod:`thoraxbench.splits` stay the only access control.

The :class:`Redactor` replaces absolute file-system paths and caller-supplied identifier
values in strings and JSON-like objects before they reach logs, JSON results and reports.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydicom.dataelem import DataElement
from pydicom.dataset import Dataset

from thoraxbench.config import Settings
from thoraxbench.dicom.discovery import SeriesInfo
from thoraxbench.dicom.headers import read_header

AUDIT_VERSION = "1"
PROFILE = "DICOM PS3.15 Basic Application Level Confidentiality Profile (subset)"
Severity = Literal["fail", "review"]

# keyword -> (category, severity). "fail": a direct identifier the Basic Profile removes.
# "review": quasi-identifiers or attributes a curated research collection may keep on purpose.
RULES: dict[str, tuple[str, Severity]] = {
    # patient identity
    "PatientName": ("patient_identity", "fail"),
    "PatientBirthName": ("patient_identity", "fail"),
    "PatientMotherBirthName": ("patient_identity", "fail"),
    "OtherPatientIDs": ("patient_identity", "fail"),
    "OtherPatientIDsSequence": ("patient_identity", "fail"),
    "OtherPatientNames": ("patient_identity", "fail"),
    "PatientBirthDate": ("patient_identity", "fail"),
    "PatientBirthTime": ("patient_identity", "fail"),
    "PatientAddress": ("patient_identity", "fail"),
    "PatientTelephoneNumbers": ("patient_identity", "fail"),
    "MedicalRecordLocator": ("patient_identity", "fail"),
    "MilitaryRank": ("patient_identity", "fail"),
    "ReferencedPatientSequence": ("patient_identity", "fail"),
    "PatientInsurancePlanCodeSequence": ("patient_identity", "fail"),
    "IssuerOfPatientID": ("patient_identity", "review"),
    "EthnicGroup": ("patient_demographics", "review"),
    "Occupation": ("patient_demographics", "review"),
    "PatientReligiousPreference": ("patient_demographics", "review"),
    "PatientAge": ("patient_demographics", "review"),
    "PatientComments": ("free_text", "review"),
    "AdditionalPatientHistory": ("free_text", "review"),
    "ImageComments": ("free_text", "review"),
    "StudyComments": ("free_text", "review"),
    # institution and device
    "InstitutionName": ("institution", "fail"),
    "InstitutionAddress": ("institution", "fail"),
    "InstitutionalDepartmentName": ("institution", "fail"),
    "StationName": ("device", "review"),
    "DeviceSerialNumber": ("device", "review"),
    # personnel
    "ReferringPhysicianName": ("personnel", "fail"),
    "ReferringPhysicianAddress": ("personnel", "fail"),
    "ReferringPhysicianTelephoneNumbers": ("personnel", "fail"),
    "PhysiciansOfRecord": ("personnel", "fail"),
    "PerformingPhysicianName": ("personnel", "fail"),
    "NameOfPhysiciansReadingStudy": ("personnel", "fail"),
    "OperatorsName": ("personnel", "fail"),
    "RequestingPhysician": ("personnel", "fail"),
    # encounter
    "AccessionNumber": ("encounter", "fail"),
    "AdmissionID": ("encounter", "fail"),
    "RequestAttributesSequence": ("encounter", "review"),
    "StudyID": ("encounter", "review"),
    # dates may be shifted on purpose by curated collections
    "StudyDate": ("date", "review"),
    "SeriesDate": ("date", "review"),
    "AcquisitionDate": ("date", "review"),
    "ContentDate": ("date", "review"),
    "AcquisitionDateTime": ("date", "review"),
}
_REASONS = {
    "fail": "Basic Profile removes or empties this attribute; a value is present",
    "review": "quasi-identifier present; confirm the collection de-identified it",
}


class TagFinding(BaseModel):
    """One flagged attribute: keyword and counts only, never the value."""

    keyword: str
    tag: str
    category: str
    severity: Severity
    rule: str
    files: int


class DeidAudit(BaseModel):
    """Aggregated header audit of a set of DICOM files (values are never included)."""

    profile: str = PROFILE
    audit_version: str = AUDIT_VERSION
    files_scanned: int = 0
    files_skipped: int = 0
    private_tags: int = 0
    burned_in_annotation: dict[str, int] = Field(default_factory=dict)
    patient_identity_removed: dict[str, int] = Field(default_factory=dict)
    findings: list[TagFinding] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True when no attribute of severity ``fail`` was found."""
        return not any(f.severity == "fail" for f in self.findings)

    def summary(self) -> str:
        """Plain-text summary with keywords and counts only."""
        lines = [
            f"De-identification audit ({self.profile}, v{self.audit_version})",
            f"files scanned: {self.files_scanned}, skipped (not DICOM): {self.files_skipped}",
            f"result: {'PASS' if self.passed else 'FAIL'} "
            f"({sum(f.severity == 'fail' for f in self.findings)} fail, "
            f"{sum(f.severity == 'review' for f in self.findings)} review)",
        ]
        lines += [
            f"  {f.severity.upper():6} {f.category:20} {f.keyword} {f.tag} "
            f"in {f.files} file(s): {f.rule}"
            for f in self.findings
        ]
        return "\n".join(lines)


def _tag_text(elem: DataElement) -> str:
    return f"({elem.tag.group:04X},{elem.tag.element:04X})"


def _is_empty(elem: DataElement) -> bool:
    value = elem.value
    if elem.VR == "SQ":
        return value is None or len(value) == 0
    if elem.VM > 1:
        return all(not str(v).strip() for v in value)
    return value is None or not str(value).strip()


def _status(ds: Dataset, keyword: str) -> str:
    value = str(ds.get(keyword, "") or "").strip().upper()
    return value if value in {"YES", "NO"} else "absent"


Hit = tuple[str, str, str, Severity, str]


def audit_dataset(ds: Dataset, *, pseudonyms: Collection[str] | None = None) -> list[Hit]:
    """Flag identifying attributes of one header, including nested sequence items.

    Returns ``(keyword, tag, category, severity, rule)`` tuples without values. With
    *pseudonyms*, a ``PatientID`` outside that set fails; without, it needs review.
    """
    patient_id = str(ds.get("PatientID", "") or "").strip()
    id_ok = pseudonyms is not None and patient_id in pseudonyms
    hits: list[Hit] = []
    if patient_id and not id_ok:
        severity: Severity = "review" if pseudonyms is None else "fail"
        rule = (
            "not verified as a dataset pseudonym"
            if pseudonyms is None
            else "not one of the expected dataset pseudonyms"
        )
        hits.append(("PatientID", "(0010,0020)", "patient_identity", severity, rule))
    private_seen = False
    for elem in ds.iterall():
        if elem.tag.is_private:
            private_seen = True
            continue
        rule_entry = RULES.get(elem.keyword)
        if rule_entry is None or _is_empty(elem):
            continue
        if elem.keyword == "PatientName" and str(elem.value).strip() == patient_id:
            continue  # the name repeats the PatientID pseudonym (TCIA convention)
        category, severity = rule_entry
        hits.append((elem.keyword, _tag_text(elem), category, severity, _REASONS[severity]))
    if private_seen:
        hits.append(
            ("PrivateTags", "(odd group)", "private_tag", "review", "private attributes present")
        )
    burned = _status(ds, "BurnedInAnnotation")
    if burned == "YES":
        hits.append(
            (
                "BurnedInAnnotation",
                "(0028,0301)",
                "burned_in",
                "fail",
                "pixel data has burned-in text",
            )
        )
    elif burned == "absent":
        hits.append(
            ("BurnedInAnnotation", "(0028,0301)", "burned_in", "review", "not declared; unknown")
        )
    if _status(ds, "PatientIdentityRemoved") != "YES":
        hits.append(
            (
                "PatientIdentityRemoved",
                "(0012,0062)",
                "deid_marker",
                "review",
                "de-identification is not declared",
            )
        )
    return list(dict.fromkeys(hits))


def _read(path: Path) -> Dataset | None:
    return read_header(path)


def audit_files(paths: Iterable[Path], *, pseudonyms: Collection[str] | None = None) -> DeidAudit:
    """Audit the headers of *paths* (non-DICOM files are counted as skipped)."""
    audit = DeidAudit()
    counts: Counter[Hit] = Counter()
    private: set[int] = set()
    burned: Counter[str] = Counter()
    removed: Counter[str] = Counter()
    for path in paths:
        ds = _read(path)
        if ds is None:
            audit.files_skipped += 1
            continue
        audit.files_scanned += 1
        counts.update(audit_dataset(ds, pseudonyms=pseudonyms))
        private.update(int(e.tag) for e in ds.iterall() if e.tag.is_private)
        burned[_status(ds, "BurnedInAnnotation")] += 1
        removed[_status(ds, "PatientIdentityRemoved")] += 1
    audit.private_tags = len(private)
    audit.burned_in_annotation = dict(sorted(burned.items()))
    audit.patient_identity_removed = dict(sorted(removed.items()))
    order = {"fail": 0, "review": 1}
    audit.findings = sorted(
        (
            TagFinding(keyword=k, tag=t, category=c, severity=s, rule=r, files=n)
            for (k, t, c, s, r), n in counts.items()
        ),
        key=lambda f: (order[f.severity], f.category, f.keyword, f.rule),
    )
    return audit


def audit_series(series: SeriesInfo, *, pseudonyms: Collection[str] | None = None) -> DeidAudit:
    """Audit every file of one discovered series."""
    return audit_files(series.files, pseudonyms=pseudonyms)


def audit_study_dir(root: Path, *, pseudonyms: Collection[str] | None = None) -> DeidAudit:
    """Audit every file below *root* in sorted order.

    Callers must run the split guard (``guard_study_input``) on *root* first.
    """
    return audit_files(sorted(p for p in root.rglob("*") if p.is_file()), pseudonyms=pseudonyms)


def identifier_values(
    paths: Iterable[Path], *, keep: Collection[str] = (), severities: Collection[str] = ("fail",)
) -> frozenset[str]:
    """Collect identifying header values for a :class:`Redactor` (in memory only).

    Values in *keep* (dataset pseudonyms) are excluded so result keys stay intact.
    """
    values: set[str] = set()
    for path in paths:
        ds = _read(path)
        if ds is None:
            continue
        patient_id = str(ds.get("PatientID", "") or "").strip()
        for elem in ds.iterall():
            entry = RULES.get(elem.keyword)
            if entry is None or entry[1] not in severities or elem.VR == "SQ":
                continue
            if elem.keyword == "PatientName" and str(elem.value).strip() == patient_id:
                continue
            items = elem.value if elem.VM > 1 else [elem.value]
            values.update(str(v).strip() for v in items if v is not None and str(v).strip())
    return frozenset(values - set(keep))


_SEGMENT = r"[^\s/\"'<>|]+"
_BASENAME = r"[^\s/\"'<>|,;)\]]*"
_GENERIC_POSIX = re.compile(r"(?<![\w/:.~\]\-])/(?:" + _SEGMENT + r"/)+(" + _BASENAME + r")")
_GENERIC_WINDOWS = re.compile(r"\b[A-Za-z]:\\(?:[^\s\\\"'<>|]+\\)+([^\s\\\"'<>|,;)\]]*)")
MIN_IDENTIFIER_LENGTH = 3
PATH_PLACEHOLDER = "[path]"
ID_PLACEHOLDER = "[redacted]"


@dataclass(frozen=True)
class Root:
    """A known directory and its placeholder.

    With *keep_relative*, the remainder below the root stays visible (project-controlled
    layout such as ``[data]/raw/<dataset>/<pseudonym>``). Otherwise only the final path
    component survives (``[home]/<basename>``).
    """

    path: str
    label: str
    keep_relative: bool = True


@dataclass(frozen=True)
class Redactor:
    """Replace absolute paths and identifier values in output text.

    Known *roots* are replaced first, longest first. Any other absolute path keeps only its
    final component: ``[path]/<basename>``. *identifiers* (and their DICOM person-name
    components) become ``[redacted]``; values shorter than three characters are ignored so
    short pseudonyms cannot corrupt ordinary text.
    """

    roots: tuple[Root, ...] = ()
    identifiers: frozenset[str] = frozenset()
    _roots: tuple[tuple[re.Pattern[str], Root], ...] = field(
        default=(), init=False, repr=False, compare=False
    )
    _names: tuple[re.Pattern[str], ...] = field(default=(), init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        roots: list[tuple[re.Pattern[str], Root]] = []
        for root in sorted(self.roots, key=lambda r: -len(r.path)):
            stripped = root.path.rstrip("/\\")
            if len(stripped) > 1:
                tail = r"((?:/" + _SEGMENT + r")*)(?![\w.\-])"
                roots.append((re.compile(re.escape(stripped) + tail), root))
        names: set[str] = set()
        for value in self.identifiers:
            names |= {value, value.replace("^", " ").strip()}
            names |= {part for part in re.split(r"[\^\s]+", value) if part}
        patterns = [
            re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)")
            for name in sorted(names, key=lambda n: (-len(n), n))
            if len(name) >= MIN_IDENTIFIER_LENGTH
        ]
        object.__setattr__(self, "_roots", tuple(roots))
        object.__setattr__(self, "_names", tuple(patterns))

    @classmethod
    def for_roots(cls, roots: Iterable[Root], identifiers: Iterable[str] = ()) -> Redactor:
        """Build a redactor matching both the literal and the resolved form of each root."""
        expanded: dict[str, Root] = {}
        for root in roots:
            for form in (root.path, str(Path(root.path).resolve())):
                expanded.setdefault(form, Root(form, root.label, root.keep_relative))
        return cls(tuple(expanded.values()), frozenset(identifiers))

    def redact(self, text: str) -> str:
        """Return *text* with known roots, other absolute paths and identifiers replaced."""
        for pattern, root in self._roots:

            def replace(match: re.Match[str], root: Root = root) -> str:
                rest = match.group(1)
                if root.keep_relative or not rest:
                    return root.label + rest
                return f"{root.label}/{rest.rsplit('/', 1)[-1]}"

            text = pattern.sub(replace, text)
        text = _GENERIC_POSIX.sub(lambda m: f"{PATH_PLACEHOLDER}/{m.group(1)}", text)
        text = _GENERIC_WINDOWS.sub(lambda m: f"{PATH_PLACEHOLDER}/{m.group(1)}", text)
        for pattern in self._names:
            text = pattern.sub(ID_PLACEHOLDER, text)
        return text

    def redact_obj(self, obj: Any) -> Any:
        """Redact every string inside a JSON-like object (dict keys and values, lists)."""
        if isinstance(obj, str):
            return self.redact(obj)
        if isinstance(obj, dict):
            return {self.redact_obj(k): self.redact_obj(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self.redact_obj(v) for v in obj]
        return obj


def settings_redactor(settings: Settings, identifiers: Iterable[str] = ()) -> Redactor:
    """Redactor for the data directory, the repository and the user's home directory."""
    return Redactor.for_roots(
        [
            Root(str(settings.data_dir), "[data]"),
            Root(str(settings.repo_root), "[repo]"),
            Root(str(Path.home()), "[home]", keep_relative=False),
        ],
        identifiers,
    )
