# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Loading and querying the canonical label ontology."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from functools import cache
from importlib import resources

import yaml

CATEGORIES = (
    "lung_parenchyma",
    "pleura",
    "mediastinum",
    "cardiovascular",
    "upper_abdomen",
    "skeletal_chest_wall",
    "devices",
)


@dataclass(frozen=True)
class Label:
    """One canonical label."""

    id: str
    name: str
    category: str
    core: bool
    scored: bool = True
    native: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Ontology:
    """The full ontology plus helpers for normalising free-text label names."""

    version: str
    labels: tuple[Label, ...]
    sha256: str

    def ids(self, *, core_only: bool = False) -> list[str]:
        """Label ids, optionally only the core benchmark set."""
        return [lb.id for lb in self.labels if lb.core or not core_only]

    def get(self, label_id: str) -> Label:
        """Return the label with *label_id* (KeyError if unknown)."""
        for lb in self.labels:
            if lb.id == label_id:
                return lb
        raise KeyError(label_id)

    def native_to_canonical(self, dataset: str) -> dict[str, list[str]]:
        """Map native terms of *dataset* to canonical ids (one term may map to several)."""
        out: dict[str, list[str]] = {}
        for lb in self.labels:
            term = lb.native.get(dataset)
            if term:
                out.setdefault(term, []).append(lb.id)
        return out

    def normalise(self, text: str) -> str | None:
        """Map a model-produced label string to a canonical id, or ``None``."""
        return _aliases(self).get(_key(text))


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


_EXTRA_ALIASES = {
    "nodule": "pulmonary_nodule",
    "lung_nodule": "pulmonary_nodule",
    "nodules": "pulmonary_nodule",
    "mass": "pulmonary_mass",
    "lung_mass": "pulmonary_mass",
    "ggo": "ground_glass_opacity",
    "ground_glass": "ground_glass_opacity",
    "effusion": "pleural_effusion",
    "fibrosis": "fibrosis_interstitial",
    "interstitial_lung_disease": "fibrosis_interstitial",
    "pulmonary_fibrotic_sequela": "fibrosis_interstitial",
    "lymph_node_enlargement": "lymphadenopathy",
    "coronary_artery_calcification": "coronary_calcification",
    "coronary_artery_wall_calcification": "coronary_calcification",
    "enlarged_heart": "cardiomegaly",
    "medical_material": "medical_device",
    "device": "medical_device",
    "rib_fracture": "fracture",
    "mosaic_attenuation_pattern": "mosaic_attenuation",
}


def _aliases(onto: Ontology) -> dict[str, str]:
    table: dict[str, str] = dict(_EXTRA_ALIASES)
    for lb in onto.labels:
        table[_key(lb.id)] = lb.id
        table[_key(lb.name)] = lb.id
    return table


@cache
def load_ontology() -> Ontology:
    """Load the packaged ontology (cached)."""
    raw = resources.files("thoraxbench.ontology").joinpath("labels.yaml").read_bytes()
    data = yaml.safe_load(raw)
    labels = tuple(
        Label(
            id=item["id"],
            name=item["name"],
            category=item["category"],
            core=bool(item["core"]),
            scored=bool(item.get("scored", True)),
            native=dict(item.get("native") or {}),
        )
        for item in data["labels"]
    )
    for lb in labels:
        if lb.category not in CATEGORIES:  # pragma: no cover - guarded by tests on the file
            msg = f"unknown category {lb.category} for {lb.id}"
            raise ValueError(msg)
    return Ontology(str(data["version"]), labels, hashlib.sha256(raw).hexdigest())
