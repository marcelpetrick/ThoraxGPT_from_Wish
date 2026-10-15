# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""LIDC-IDRI reader XML → study-level labels and lesion annotations.

Each LIDC series was read by up to four radiologists (Armato et al. 2011). Every reader marks
*nodules >= 3 mm* with contours, *nodules < 3 mm* with a centroid, and *non-nodules >= 3 mm*.
This module:

1. parses every reader's nodule marks (contour points in pixel coordinates + z position);
2. converts them to the canonical volume grid in millimetres (``z = slice_index * dz``,
   ``y = row * dy``, ``x = col * dx``, slice index 0 cranial);
3. clusters marks of different readers that refer to the same nodule (centre distance
   <= max(radius, 5 mm), at most one mark per reader per cluster);
4. derives study labels: ``pulmonary_nodule`` = any cluster 3-30 mm, ``pulmonary_mass`` = any
   cluster >= 30 mm (LIDC marks lesions up to 30 mm, so masses are rare). All other ontology
   labels are *unknown* (``None``) — LIDC does not annotate them.

Diameter = longest in-plane extent of the contour over all its slices (an approximation of the
long-axis diameter radiologists measure).
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from thoraxbench.dicom import Volume
from thoraxbench.schemas import LesionAnnotation, ReferenceLabels

NS = {"l": "http://www.nih.gov"}
SMALL_NODULE_MM = 3.0
MASS_MM = 30.0
MIN_MATCH_MM = 5.0


@dataclass
class ReaderNodule:
    """One reader's mark of one nodule."""

    reader: int
    nodule_id: str
    points_xyz: list[tuple[float, float, float]] = field(default_factory=list)
    malignancy: int | None = None
    small: bool = False


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def parse_lidc_xml(path: Path) -> list[ReaderNodule]:
    """Parse every reader's nodule marks (non-nodules are ignored)."""
    root = ET.parse(path).getroot()  # noqa: S314 - trusted local file
    nodules: list[ReaderNodule] = []
    for reader, session in enumerate(root.findall("l:readingSession", NS)):
        for node in session.findall("l:unblindedReadNodule", NS):
            mark = ReaderNodule(reader=reader, nodule_id=_text(node.find("l:noduleID", NS)))
            malignancy = _text(node.find("l:characteristics/l:malignancy", NS))
            mark.malignancy = int(malignancy) if malignancy.isdigit() else None
            for roi in node.findall("l:roi", NS):
                if _text(roi.find("l:inclusion", NS)).upper() == "FALSE":
                    continue
                z = float(_text(roi.find("l:imageZposition", NS)))
                for edge in roi.findall("l:edgeMap", NS):
                    x = float(_text(edge.find("l:xCoord", NS)))
                    y = float(_text(edge.find("l:yCoord", NS)))
                    mark.points_xyz.append((x, y, z))
            mark.small = len({(p[0], p[1]) for p in mark.points_xyz}) <= 1
            if mark.points_xyz:
                nodules.append(mark)
    return nodules


def _slice_index(volume: Volume, z_mm: float) -> int:
    return min(
        range(len(volume.z_positions_mm)), key=lambda i: abs(volume.z_positions_mm[i] - z_mm)
    )


def _geometry(mark: ReaderNodule, volume: Volume) -> tuple[tuple[float, float, float], float]:
    dz, dy, dx = volume.spacing_mm
    xs = [p[0] for p in mark.points_xyz]
    ys = [p[1] for p in mark.points_xyz]
    zs = [_slice_index(volume, p[2]) * dz for p in mark.points_xyz]
    center = (sum(zs) / len(zs), sum(ys) / len(ys) * dy, sum(xs) / len(xs) * dx)
    if mark.small:
        return center, 2.0  # "< 3 mm" by definition
    by_slice: dict[float, list[tuple[float, float]]] = {}
    for x, y, z in mark.points_xyz:
        by_slice.setdefault(z, []).append((x * dx, y * dy))
    diameter = 0.0
    for pts in by_slice.values():
        for i, (ax, ay) in enumerate(pts):
            for bx, by in pts[i + 1 :]:
                diameter = max(diameter, math.hypot(ax - bx, ay - by))
    return center, max(diameter, SMALL_NODULE_MM)


@dataclass
class _Cluster:
    marks: list[tuple[tuple[float, float, float], float, int | None]]
    readers: set[int]

    @property
    def center(self) -> tuple[float, float, float]:
        n = len(self.marks)
        z, y, x = (sum(m[0][k] for m in self.marks) / n for k in range(3))
        return z, y, x

    @property
    def diameter(self) -> float:
        return sum(m[1] for m in self.marks) / len(self.marks)


def cluster_nodules(marks: list[ReaderNodule], volume: Volume) -> list[LesionAnnotation]:
    """Merge reader marks of the same nodule into consensus lesions (>= 3 mm only)."""
    clusters: list[_Cluster] = []
    for mark in marks:
        if mark.small:
            continue
        center, diameter = _geometry(mark, volume)
        match = next(
            (
                cl
                for cl in clusters
                if mark.reader not in cl.readers
                and math.dist(center, cl.center) <= max(diameter / 2, cl.diameter / 2, MIN_MATCH_MM)
            ),
            None,
        )
        if match is None:
            clusters.append(_Cluster([(center, diameter, mark.malignancy)], {mark.reader}))
        else:
            match.marks.append((center, diameter, mark.malignancy))
            match.readers.add(mark.reader)
    lesions: list[LesionAnnotation] = []
    for cl in clusters:
        mal = [m[2] for m in cl.marks if m[2] is not None]
        lesions.append(
            LesionAnnotation(
                label="pulmonary_mass" if cl.diameter >= MASS_MM else "pulmonary_nodule",
                center_zyx=cl.center,
                diameter_mm=round(cl.diameter, 1),
                readers=len(cl.readers),
                malignancy=round(sum(mal) / len(mal), 2) if mal else None,
                native_term="LIDC unblindedReadNodule >= 3 mm",
            )
        )
    return sorted(lesions, key=lambda les: les.center_zyx)


def lidc_reference(xml_path: Path, volume: Volume, case_id: str) -> ReferenceLabels:
    """Study-level reference labels and lesions for one LIDC series."""
    lesions = cluster_nodules(parse_lidc_xml(xml_path), volume)
    nodules = [les for les in lesions if les.label == "pulmonary_nodule"]
    masses = [les for les in lesions if les.label == "pulmonary_mass"]
    return ReferenceLabels(
        dataset="lidc_idri",
        patient_id=volume.patient_id,
        study_uid=case_id,
        labels={"pulmonary_nodule": bool(nodules), "pulmonary_mass": bool(masses)},
        lesions=lesions,
        native_labels={"source": xml_path.name, "readers_rule": ">= 1 of up to 4 readers"},
    )
