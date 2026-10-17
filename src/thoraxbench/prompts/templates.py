# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Prompt templates are versioned artifacts loaded from ``configs/prompts/<id>.yaml``.

Templates use :class:`string.Template` placeholders, so literal JSON braces in the text
need no escaping:

* ``$labels`` — bullet list of the requested canonical labels (``- id: name``)
* ``$label_ids`` — comma-separated label ids
* ``$n_images`` — number of images supplied
* ``$captions`` — numbered image captions (window, plane, slab, position); authoritative
* ``$caption_lines`` — the captions verbatim, one per line (they carry their own number)
* ``$context`` — deterministic HU measurements ("evidence"), or a "none available" sentence
* ``$regions`` — the fixed radiologist search order (:data:`REGION_ORDER`)
* ``$schema`` — the JSON schema of the expected output
* ``$first_pass`` — (second pass of two-pass prompts only) the first-pass output
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any

import yaml

from thoraxbench.ontology import Ontology, load_ontology
from thoraxbench.prompts.schema import findings_json_schema, strict_findings_json_schema

PROMPT_IDS = ("P0", "P1", "P2", "P3", "P4", "P5", "P6")
SCHEMA_VERSIONS = ("1", "2")
NO_CONTEXT = "No deterministic measurements are available for this study."

#: Fixed checklist order matching radiologist search patterns (docs/reading_practice.md §4.1).
REGION_ORDER = (
    "technique and image quality",
    "lines, tubes and devices",
    "airways (trachea, main and lobar bronchi)",
    "lungs, lobe by lobe (right upper, middle, lower; left upper incl. lingula, lower)",
    "pleura (effusion, pneumothorax, thickening)",
    "mediastinum and hila (lymph nodes, masses)",
    "heart and pericardium",
    "great vessels (aorta, pulmonary arteries)",
    "chest wall and soft tissues",
    "bones (ribs, spine, sternum, shoulder girdle)",
    "upper abdomen (liver, adrenals, stomach/hiatus)",
)


@dataclass(frozen=True)
class RenderedPrompt:
    """A fully rendered system + user message pair."""

    system: str
    user: str


@dataclass(frozen=True)
class PromptTemplate:
    """One versioned prompt (Vision §19).

    Attributes:
        id: ``P0`` … ``P5``.
        version: version of the prompt text; bump on any wording change.
        title: short human-readable name.
        system: system message template.
        user: user message template (first pass).
        second_pass: optional user template of a second call (two-pass prompt P4).
        label_constrained: whether findings are restricted to the requested labels.
        sha256: hash of the canonical template content (recorded in run provenance).
        schema_version: ``1`` = original findings schema; ``2`` = strict fixed-length
            schema (:func:`~thoraxbench.prompts.schema.strict_findings_json_schema`),
            label-constrained single-pass prompts only.
    """

    id: str
    version: str
    title: str
    system: str
    user: str
    second_pass: str | None
    label_constrained: bool
    sha256: str
    schema_version: str = "1"

    @property
    def two_pass(self) -> bool:
        """Whether this prompt needs two model calls."""
        return self.second_pass is not None

    def schema(self, labels: list[str], *, n_images: int | None = None) -> dict[str, Any]:
        """Output JSON schema; label-constrained prompts restrict ``findings[].label``."""
        if self.schema_version == "2":
            return strict_findings_json_schema(labels, n_images=n_images or 0)
        return findings_json_schema(labels if self.label_constrained else None, n_images=n_images)

    def _values(
        self,
        labels: list[str],
        n_images: int,
        captions: list[str],
        context: str,
        ontology: Ontology,
    ) -> dict[str, str]:
        names = {lb.id: lb.name for lb in ontology.labels}
        return {
            "labels": "\n".join(f"- {lid}: {names.get(lid, lid)}" for lid in labels),
            "label_ids": ", ".join(labels),
            "n_images": str(n_images),
            "captions": "\n".join(f"image {i}: {c}" for i, c in enumerate(captions, start=1))
            or "(no captions supplied)",
            "caption_lines": "\n".join(captions) or "(no captions supplied)",
            "context": context.strip() or NO_CONTEXT,
            "regions": "\n".join(f"{i}. {r}" for i, r in enumerate(REGION_ORDER, start=1)),
            "schema": json.dumps(self.schema(labels, n_images=n_images), sort_keys=True),
        }

    def render(
        self,
        labels: list[str],
        n_images: int,
        captions: list[str] | None = None,
        context: str = "",
        ontology: Ontology | None = None,
    ) -> RenderedPrompt:
        """Render the first-pass messages."""
        values = self._values(
            labels, n_images, captions or [], context, ontology or load_ontology()
        )
        return RenderedPrompt(
            system=Template(self.system).substitute(values),
            user=Template(self.user).substitute(values),
        )

    def render_second_pass(
        self,
        first_pass: str,
        labels: list[str],
        n_images: int,
        *,
        captions: list[str] | None = None,
        context: str = "",
        ontology: Ontology | None = None,
    ) -> RenderedPrompt:
        """Render the second-pass messages of a two-pass prompt.

        Raises:
            ValueError: if the prompt is single-pass.
        """
        if self.second_pass is None:
            msg = f"prompt {self.id} is single-pass"
            raise ValueError(msg)
        values = self._values(
            labels, n_images, captions or [], context, ontology or load_ontology()
        )
        values["first_pass"] = first_pass
        return RenderedPrompt(
            system=Template(self.system).substitute(values),
            user=Template(self.second_pass).substitute(values),
        )


def load_prompt(prompt_id: str, prompts_dir: Path) -> PromptTemplate:
    """Load ``<prompts_dir>/<prompt_id>.yaml``.

    Raises:
        FileNotFoundError: if the prompt does not exist.
        ValueError: if the file id does not match *prompt_id*.
    """
    path = prompts_dir / f"{prompt_id}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("id") != prompt_id:
        msg = f"{path.name}: id '{data.get('id')}' does not match '{prompt_id}'"
        raise ValueError(msg)
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    schema_version = str(data.get("schema_version", "1"))
    if schema_version not in SCHEMA_VERSIONS:
        msg = f"{path.name}: unknown schema_version '{schema_version}'"
        raise ValueError(msg)
    constrained = bool(data.get("label_constrained", False))
    if schema_version == "2" and (not constrained or data.get("second_pass")):
        msg = f"{path.name}: schema_version 2 needs a label-constrained single-pass prompt"
        raise ValueError(msg)
    return PromptTemplate(
        id=str(data["id"]),
        version=str(data["version"]),
        title=str(data["title"]),
        system=str(data["system"]),
        user=str(data["user"]),
        second_pass=str(data["second_pass"]) if data.get("second_pass") else None,
        label_constrained=constrained,
        sha256=hashlib.sha256(canonical).hexdigest(),
        schema_version=schema_version,
    )
