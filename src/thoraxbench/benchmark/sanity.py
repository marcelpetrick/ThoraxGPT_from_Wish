# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""``thoraxbench sanity``: check whether a local VLM sees and uses the attached images.

Readiness diagnostics before any further prompt or adaptation work. Each diagnostic is one
hashed YAML file under ``configs/experiments/sanity/``:

* ``image_dependence`` (S1): the same question with real prepared images, uniform grey,
  noise, shuffled order and no images. Identical answers fail readiness; they do not
  establish by themselves that the image path is ignored.
* ``obvious_target`` (S2): synthetic phantom with a large nodule vs the same phantom
  without, single image or multi-image.
* ``description`` (S3): free-text description of one image, recorded verbatim.
* ``position_binding`` (T2): which of four images shows a bright disk? Compares one message
  with all images against one message per image (image followed by its caption).
* ``paired_slab`` (S4): one lesion-centred LIDC calibration slab and one matched control
  slab per reference nodule, one yes/no question per image, slice-level AUROC with a
  patient-level bootstrap.

Only calibration-phase entries are read; synthetic phantoms need no data. Each invocation
gets its own ``data/results/benchmark/<id>/<timestamp>-<hash>-<uuid>/`` folder with an
immutable identity manifest, one checkpointed artifact per request (request without image
bytes, raw response including logprobs) and final JSON/Markdown. Results are diagnostics,
not accuracy.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from string import Template
from typing import Any, Literal
from uuid import uuid4

import httpx
import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from thoraxbench.adapters.base import ModelConfig, load_model_config
from thoraxbench.adapters.factory import require_local_endpoint
from thoraxbench.adapters.ollama import _provider_error
from thoraxbench.analysis import DISCLAIMER
from thoraxbench.benchmark import sanity_inputs as si
from thoraxbench.benchmark.checkpoint import BenchmarkStore, runtime_identity
from thoraxbench.benchmark.coverage import phase_entries
from thoraxbench.config import Settings
from thoraxbench.index import IndexEntry, index_path, open_study
from thoraxbench.parsing.json_extract import extract_json
from thoraxbench.provenance import git_state, sha256_of_file, sha256_of_obj
from thoraxbench.scoring.classification import auroc_auprc, bootstrap_ci
from thoraxbench.splits import Phase
from thoraxbench.splits.guard import config_sha256

SANITY_VERSION = "3"
SAFE_ID = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"
FRAMING = (
    "Readiness diagnostic on synthetic phantoms and calibration-phase cases only. It tests "
    "whether the model's answers depend on the images; it is not an accuracy benchmark, "
    "not an internal-test or sealed result and says nothing about clinical use."
)
NEUTRAL_CAPTION = "attached image"
CONFIDENCE_STEPS = [round(0.05 * k, 2) for k in range(21)]
Kind = Literal["yes_no", "choice", "free_text"]
Test = Literal[
    "image_dependence", "obvious_target", "description", "position_binding", "paired_slab"
]
Window = Literal["lung", "medgemma"]
Layout = Literal["single", "interleaved"]
Condition = Literal["real", "gray", "noise", "shuffled", "none"]


class Question(BaseModel):
    """The text asked with every input; ``$n_images`` is substituted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Kind
    text: str = Field(min_length=1)
    system: str = ""
    answer_key: str = Field(default="nodule", pattern=r"^[a-z_]+$")
    num_predict: int = Field(default=48, ge=1, le=2048)


class PhantomRef(BaseModel):
    """One synthetic phantom (nodule diameter 0 = none)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seed: int = 0
    side: Literal["right", "left"] = "right"
    diameter_mm: float = Field(default=0.0, ge=0.0, le=60.0)


class SyntheticBlock(BaseModel):
    """Synthetic inputs (no patient data)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phantoms: list[PhantomRef] = Field(default_factory=list)
    seeds: list[int] = Field(default_factory=list)
    sides: list[Literal["right", "left"]] = Field(
        default_factory=lambda: list[Literal["right", "left"]](["right"])
    )
    diameters_mm: list[float] = Field(default_factory=list)
    permutations: int = Field(default=20, ge=1, le=200)


class LidcBlock(BaseModel):
    """Calibration-phase LIDC inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset: Literal["lidc_idri"] = "lidc_idri"
    positive_studies: int = Field(default=0, ge=0, le=40)
    negative_studies: int = Field(default=0, ge=0, le=40)
    levels: list[float] = Field(default_factory=lambda: [0.15, 0.5, 0.85])
    min_diameter_mm: float = Field(default=3.0, ge=0.0)
    max_lesions: int = Field(default=40, ge=1, le=200)
    control_distance_mm: float = Field(default=30.0, ge=0.0)


class SanityConfig(BaseModel):
    """Schema of ``configs/experiments/sanity/*.yaml``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=SAFE_ID)
    test: Test
    title: str = ""
    description: str = ""
    vision_ref: str = ""
    phases: list[Literal["calibration"]] = Field(
        default_factory=lambda: list[Literal["calibration"]](["calibration"]), min_length=1
    )
    models: list[str] = Field(min_length=1)
    question: Question
    windows: list[Window] = Field(default_factory=lambda: list[Window](["lung"]), min_length=1)
    layouts: list[Layout] = Field(default_factory=lambda: list[Layout](["single"]), min_length=1)
    conditions: list[Condition] = Field(
        default_factory=lambda: list[Condition](["real"]), min_length=1
    )
    image_mode: Literal["single", "multi"] = "single"
    n_images: int = Field(default=1, ge=1, le=32)
    size: int = Field(default=896, ge=64, le=1024)
    slab_mm: float = Field(default=5.0, ge=0.0, le=20.0)
    num_ctx: int = Field(default=8192, ge=1024, le=32768)
    top_logprobs: int = Field(default=10, ge=0, le=20)
    seed: int = 0
    n_boot: int = Field(default=1000, ge=0)
    #: Replace every caption with a neutral label so the text reveals nothing about the image.
    neutral_captions: bool = False
    synthetic: SyntheticBlock | None = None
    lidc: LidcBlock | None = None

    @model_validator(mode="after")
    def _check(self) -> SanityConfig:
        if len(set(self.models)) != len(self.models):
            raise ValueError("models must be unique")
        if self.synthetic is None and self.lidc is None:
            raise ValueError("a sanity test needs synthetic or lidc inputs")
        if self.test == "paired_slab" and (self.lidc is None or self.question.kind != "yes_no"):
            raise ValueError("paired_slab needs an lidc block and a yes_no question")
        if self.test == "position_binding" and (
            self.synthetic is None or self.question.kind != "choice" or self.n_images < 2
        ):
            raise ValueError(
                "position_binding needs synthetic inputs, a choice question and n_images >= 2"
            )
        if self.test == "description" and self.question.kind != "free_text":
            raise ValueError("description needs a free_text question")
        if self.test in {"image_dependence", "obvious_target"} and self.question.kind != "yes_no":
            raise ValueError(f"{self.test} needs a yes_no question")
        return self


@dataclass(frozen=True)
class LoadedSanity:
    """A parsed sanity configuration with its file hash."""

    config: SanityConfig
    path: Path
    file_sha256: str


def load_sanity(path: Path) -> LoadedSanity:
    """Read and validate a sanity YAML file (ValueError if invalid)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"sanity config {path.name} must be a YAML mapping")
    return LoadedSanity(SanityConfig.model_validate(data), path, config_sha256(path))


# -- inputs -----------------------------------------------------------------------------


def _phantoms(block: SyntheticBlock) -> list[PhantomRef]:
    refs = list(block.phantoms)
    for seed in block.seeds:
        for side in block.sides:
            refs.extend(
                PhantomRef(seed=seed, side=side, diameter_mm=d) for d in [0.0, *block.diameters_mm]
            )
    return refs


def _phantom_name(ref: PhantomRef) -> str:
    return f"phantom-s{ref.seed}-{ref.side}"


def _phantom_condition(ref: PhantomRef) -> str:
    return f"nodule{ref.diameter_mm:g}mm" if ref.diameter_mm > 0 else "none"


def _load_phantom(ref: PhantomRef) -> si.Phantom:
    spec = si.phantom_spec(ref.seed, ref.side, ref.diameter_mm)
    return si.load_phantom(spec, f"SANITY-{ref.seed}-{ref.side}-{ref.diameter_mm:g}")


def _lidc_studies(cfg: SanityConfig, settings: Settings) -> list[IndexEntry]:
    assert cfg.lidc is not None  # noqa: S101 - checked by caller
    entries = phase_entries(cfg.lidc.dataset, settings, Phase.CALIBRATION)
    positive = [e for e in entries if e.reference.labels.get("pulmonary_nodule")]
    negative = [e for e in entries if e.reference.labels.get("pulmonary_nodule") is False]
    return positive[: cfg.lidc.positive_studies] + negative[: cfg.lidc.negative_studies]


def _perturbed(item: si.SanityItem, condition: str, rng: np.random.Generator) -> si.SanityItem:
    images = item.images
    meta = dict(item.meta)
    if condition == "gray":
        images = [si.gray_like(img) for img in images]
    elif condition == "noise":
        images = [si.noise_like(img, rng) for img in images]
    elif condition == "shuffled":
        order = si.derangement(len(images), rng)
        images = [images[k] for k in order]
        meta["order"] = order
    elif condition == "none":
        images = []
    return si.SanityItem(
        key=f"{item.key}-{condition}",
        group=item.group,
        condition=condition,
        images=images,
        captions=list(item.captions),
        truth=item.truth,
        patient=item.patient,
        meta=meta,
    )


def _source_items(
    cfg: SanityConfig, settings: Settings, open_case: si.OpenStudy, window: str
) -> list[si.SanityItem]:
    """Real-image items for image_dependence and obvious_target (synthetic first)."""
    items: list[si.SanityItem] = []
    if cfg.synthetic is not None:
        for ref in _phantoms(cfg.synthetic):
            phantom = _load_phantom(ref)
            meta: dict[str, Any] = {
                "window": window,
                "diameter_mm": ref.diameter_mm,
                "source": "synthetic",
            }
            if cfg.image_mode == "single":
                png, caption = si.phantom_single(phantom, window, cfg.size, cfg.slab_mm)
                images, captions = [png], [caption]
                meta["nodule_level_sampled"] = ref.diameter_mm > 0
            else:
                images, captions, indices = si.view_images(
                    phantom.study, window, cfg.n_images, cfg.size, cfg.slab_mm
                )
                meta["nodule_level_sampled"] = _nodule_sampled(phantom, ref, indices, cfg.slab_mm)
            items.append(
                si.SanityItem(
                    key=f"{_phantom_name(ref)}-{_phantom_condition(ref)}-{window}",
                    group=_phantom_name(ref),
                    condition=_phantom_condition(ref),
                    images=images,
                    captions=captions,
                    truth=int(ref.diameter_mm > 0),
                    patient=_phantom_name(ref),
                    meta=meta,
                )
            )
    if cfg.lidc is not None:
        for entry in _lidc_studies(cfg, settings):
            study = open_case(entry, settings)
            images, captions, _ = si.view_images(study, window, cfg.n_images, cfg.size, cfg.slab_mm)
            truth = entry.reference.labels.get("pulmonary_nodule")
            items.append(
                si.SanityItem(
                    key=f"{entry.case_id}-study-{window}",
                    group=entry.case_id,
                    condition="study",
                    images=images,
                    captions=captions,
                    truth=None if truth is None else int(truth),
                    patient=f"{entry.dataset}:{entry.patient_id}",
                    meta={"window": window, "source": "lidc_calibration", "case_id": entry.case_id},
                )
            )
    return items


def _nodule_sampled(
    phantom: si.Phantom, ref: PhantomRef, indices: Sequence[int], slab_mm: float
) -> bool:
    if ref.diameter_mm <= 0:
        return False
    dz = phantom.study.volume.spacing_mm[0]
    reach = ref.diameter_mm / 2 + max(slab_mm, dz) / 2
    return any(abs(i - phantom.nodule_index) * dz <= reach for i in indices)


def _description_items(
    cfg: SanityConfig, settings: Settings, open_case: si.OpenStudy, window: str
) -> list[si.SanityItem]:
    items: list[si.SanityItem] = []
    if cfg.synthetic is not None:
        for ref in _phantoms(cfg.synthetic):
            png, caption = si.phantom_single(_load_phantom(ref), window, cfg.size, cfg.slab_mm)
            items.append(
                si.SanityItem(
                    key=f"{_phantom_name(ref)}-{_phantom_condition(ref)}-{window}",
                    group=_phantom_name(ref),
                    condition=_phantom_condition(ref),
                    images=[png],
                    captions=[caption],
                    truth=None,
                    patient=_phantom_name(ref),
                    meta={"window": window, "source": "synthetic", "diameter_mm": ref.diameter_mm},
                )
            )
    if cfg.lidc is not None:
        for entry in _lidc_studies(cfg, settings):
            study = open_case(entry, settings)
            vol = study.volume
            lo, hi = entry.cues.lung_z_extent or (0, vol.shape[0] - 1)
            for level in cfg.lidc.levels:
                idx = min(max(round(lo + level * (hi - lo)), 0), vol.shape[0] - 1)
                dz = vol.spacing_mm[0]
                png = si.render_axial(vol.hu, idx, cfg.slab_mm, dz, window=window, size=cfg.size)
                items.append(
                    si.SanityItem(
                        key=f"{entry.case_id}-level{level:g}-{window}",
                        group=entry.case_id,
                        condition=f"lung_level_{level:g}",
                        images=[png],
                        captions=[
                            si.axial_caption(
                                window, si.rendered_thickness_mm(vol.shape[0], idx, cfg.slab_mm, dz)
                            )
                        ],
                        truth=None,
                        patient=f"{entry.dataset}:{entry.patient_id}",
                        meta={
                            "window": window,
                            "source": "lidc_calibration",
                            "case_id": entry.case_id,
                            "lung_level": level,
                        },
                    )
                )
    return items


def _binding_items(cfg: SanityConfig, window: str) -> list[si.SanityItem]:
    assert cfg.synthetic is not None  # noqa: S101 - validated
    ref = (_phantoms(cfg.synthetic) or [PhantomRef()])[0]
    phantom = _load_phantom(ref)
    vol = phantom.study.volume
    lo, hi = phantom.study.cues.lung_z_extent or (0, vol.shape[0] - 1)
    n = cfg.n_images
    dz = vol.spacing_mm[0]
    levels = [round(lo + (k + 0.5) * (hi - lo) / n) for k in range(n)]
    base = [
        si.render_axial(vol.hu, idx, cfg.slab_mm, dz, window=window, size=cfg.size)
        for idx in levels
    ]
    caption = si.axial_caption(
        window, si.rendered_thickness_mm(vol.shape[0], levels[0], cfg.slab_mm, dz)
    )
    disk = si.disk_image(cfg.size)
    rng = np.random.default_rng(cfg.seed)
    items: list[si.SanityItem] = []
    for perm in range(cfg.synthetic.permutations):
        position = perm % n
        others = [base[k] for k in rng.permutation(n)][: n - 1]
        images = [*others[:position], disk, *others[position:]]
        captions = [caption] * n  # identical captions: the text must not reveal the disk
        items.append(
            si.SanityItem(
                key=f"perm{perm:02d}-{window}",
                group=f"perm{perm:02d}",
                condition=f"disk_at_{position + 1}",
                images=images,
                captions=captions,
                truth=position + 1,
                patient=f"perm{perm:02d}",
                meta={"window": window, "source": "synthetic"},
            )
        )
    return items


def build_items(
    cfg: SanityConfig, settings: Settings, open_case: si.OpenStudy = open_study
) -> tuple[list[si.SanityItem], dict[str, Any]]:
    """All inputs of *cfg*, per window, plus selection counts."""
    items: list[si.SanityItem] = []
    counts: dict[str, Any] = {}
    rng = np.random.default_rng(cfg.seed)
    for window in cfg.windows:
        if cfg.test == "paired_slab":
            assert cfg.lidc is not None  # noqa: S101 - validated
            entries = phase_entries(cfg.lidc.dataset, settings, Phase.CALIBRATION)
            pairs, counts = si.select_pairs(
                entries,
                min_diameter_mm=cfg.lidc.min_diameter_mm,
                max_lesions=cfg.lidc.max_lesions,
                min_distance_mm=cfg.lidc.control_distance_mm,
                slab_mm=cfg.slab_mm,
            )
            counts = counts | {
                "patients": len({p.entry.case_id for p in pairs}),
                "calibration_studies": len(entries),
            }
            items.extend(
                si.pair_items(
                    pairs, settings, open_case, window=window, size=cfg.size, slab_mm=cfg.slab_mm
                )
            )
        elif cfg.test == "description":
            items.extend(_description_items(cfg, settings, open_case, window))
        elif cfg.test == "position_binding":
            items.extend(_binding_items(cfg, window))
        else:
            for source in _source_items(cfg, settings, open_case, window):
                if cfg.test == "obvious_target":
                    items.append(source)
                    continue
                items.extend(_perturbed(source, condition, rng) for condition in cfg.conditions)
    if cfg.neutral_captions:
        items = [replace(item, captions=[NEUTRAL_CAPTION] * len(item.captions)) for item in items]
    return items, counts


def limit_groups(items: Sequence[si.SanityItem], limit: int | None) -> list[si.SanityItem]:
    """Keep every item of the first *limit* groups (pairs and conditions stay together)."""
    if limit is None:
        return list(items)
    keep: list[str] = []
    for item in items:
        if item.group not in keep:
            keep.append(item.group)
    allowed = set(keep[:limit])
    return [item for item in items if item.group in allowed]


# -- requests ---------------------------------------------------------------------------


def _b64(image: bytes) -> str:
    return base64.b64encode(image).decode("ascii")


def build_messages(item: si.SanityItem, layout: str, question: Question) -> list[dict[str, Any]]:
    """Chat messages for *item* in one of the two image layouts.

    ``single``: one user message carrying every image (Ollama 0.40.4 places all image
    tokens before the text) and the caption list in its text. ``interleaved``: one user
    message per image whose text is that image's caption, so each image is directly
    followed by its ``IMAGE k`` label (MedGemma ``SLICE k`` style), then the question.
    """
    n = len(item.captions)
    text = Template(question.text).safe_substitute(n_images=n)
    messages: list[dict[str, Any]] = []
    if question.system:
        messages.append({"role": "system", "content": question.system})
    if layout == "interleaved" and len(item.images) > 1:
        for k, (image, caption) in enumerate(zip(item.images, item.captions, strict=True)):
            messages.append(
                {"role": "user", "content": f"IMAGE {k + 1}: {caption}", "images": [_b64(image)]}
            )
        messages.append({"role": "user", "content": text})
        return messages
    header = (
        f"The {n} attached images are IMAGE 1 to IMAGE {n} in attachment order."
        if n > 1
        else "The attached image is IMAGE 1."
    )
    lines = "\n".join(f"IMAGE {k + 1}: {caption}" for k, caption in enumerate(item.captions))
    message: dict[str, Any] = {"role": "user", "content": f"{header}\n{lines}\n\n{text}"}
    if item.images:
        message["images"] = [_b64(image) for image in item.images]
    messages.append(message)
    return messages


def answer_schema(question: Question, n_images: int) -> dict[str, Any] | None:
    """Grammar-enforced JSON schema (enums only; Ollama ignores number maxima)."""
    if question.kind == "yes_no":
        return {
            "type": "object",
            "properties": {
                question.answer_key: {"enum": ["yes", "no"]},
                "confidence": {"enum": CONFIDENCE_STEPS},
            },
            "required": [question.answer_key, "confidence"],
        }
    if question.kind == "choice":
        return {
            "type": "object",
            "properties": {"image": {"enum": list(range(1, max(n_images, 1) + 1))}},
            "required": ["image"],
        }
    return None


def build_payload(
    item: si.SanityItem, layout: str, cfg: SanityConfig, model: ModelConfig
) -> dict[str, Any]:
    """Build the ``/api/chat`` request body (images base64-encoded)."""
    question = cfg.question
    messages = build_messages(item, layout, question)
    prefill = model.options.get("assistant_prefill")
    if isinstance(prefill, str) and prefill:
        messages.append({"role": "assistant", "content": prefill})
    options: dict[str, Any] = {"temperature": 0, "seed": 0}
    options.update(model.options.get("ollama", {}))
    options.update({"num_ctx": cfg.num_ctx, "num_predict": question.num_predict})
    payload: dict[str, Any] = {
        "model": model.tag,
        "messages": messages,
        "stream": False,
        "options": options,
        "keep_alive": model.options.get("keep_alive", "10m"),
    }
    schema = answer_schema(question, len(item.captions))
    if schema is not None:
        payload["format"] = schema
        if cfg.top_logprobs:
            payload["logprobs"] = True
            payload["top_logprobs"] = cfg.top_logprobs
    if "think" in model.options:
        payload["think"] = model.options["think"]
    return payload


def redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the request as persisted: image bytes replaced by their SHA-256 digests."""
    messages = []
    for message in payload["messages"]:
        copy = {k: v for k, v in message.items() if k != "images"}
        if "images" in message:
            copy["image_sha256"] = [
                hashlib.sha256(base64.b64decode(i)).hexdigest() for i in message["images"]
            ]
            copy["image_bytes_omitted"] = True
        messages.append(copy)
    return payload | {"messages": messages}


def post_chat(
    client: httpx.Client, base_url: str, payload: dict[str, Any], timeout_s: float
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """POST one chat request; return ``(body, diagnostic)`` without raising on HTTP errors."""
    start = time.perf_counter()
    try:
        resp = client.post(f"{base_url.rstrip('/')}/api/chat", json=payload, timeout=timeout_s)
    except httpx.HTTPError as exc:
        return None, {
            "error": f"http error: {type(exc).__name__}",
            "latency_s": time.perf_counter() - start,
        }
    diagnostic: dict[str, Any] = {
        "http_status": resp.status_code,
        "latency_s": time.perf_counter() - start,
    }
    if resp.status_code != httpx.codes.OK:
        return None, diagnostic | {
            "error": f"ollama HTTP {resp.status_code}",
            "body_text": resp.text[:300],
        }
    try:
        data = resp.json()
    except ValueError:
        return None, diagnostic | {
            "error": "ollama returned non-JSON response",
            "body_text": resp.text[:300],
        }
    if not isinstance(data, dict):
        return None, diagnostic | {"error": "ollama returned a non-object JSON response"}
    problem = _provider_error(data)
    if problem:
        return None, diagnostic | {"error": problem, "body": data}
    return data, diagnostic | {"body": data}


# -- parsing ----------------------------------------------------------------------------


def _norm(token: object) -> str:
    return str(token).strip().strip('"').strip().lower()


def _top(entry: dict[str, Any]) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for alt in entry.get("top_logprobs") or []:
        if isinstance(alt, dict) and isinstance(alt.get("logprob"), int | float):
            out.append((_norm(alt.get("token", "")), float(alt["logprob"])))
    return out


def yes_probability(logprobs: object) -> float | None:
    """P(yes) / (P(yes) + P(no)) at the first generated yes/no token (raw distribution)."""
    if not isinstance(logprobs, list):
        return None
    for entry in logprobs:
        if isinstance(entry, dict) and _norm(entry.get("token", "")) in {"yes", "no"}:
            mass = {"yes": 0.0, "no": 0.0}
            for token, logprob in _top(entry):
                if token in mass:
                    mass[token] += math.exp(logprob)
            total = mass["yes"] + mass["no"]
            return mass["yes"] / total if total > 0 else None
    return None


def choice_probabilities(logprobs: object, n: int) -> dict[int, float] | None:
    """Renormalised probabilities of the digits ``1..n`` at the first digit token."""
    if not isinstance(logprobs, list):
        return None
    valid = {str(k) for k in range(1, n + 1)}
    for entry in logprobs:
        if isinstance(entry, dict) and _norm(entry.get("token", "")) in valid:
            mass = dict.fromkeys(range(1, n + 1), 0.0)
            for token, logprob in _top(entry):
                if token in valid:
                    mass[int(token)] += math.exp(logprob)
            total = sum(mass.values())
            return {k: v / total for k, v in mass.items()} if total > 0 else None
    return None


def parse_answer(question: Question, body: dict[str, Any] | None, n_images: int) -> dict[str, Any]:
    """Parse the answer fields of one response (``answer`` is ``None`` when unusable)."""
    if body is None:
        return {"answer": None, "parse": "no response"}
    message = body.get("message") if isinstance(body.get("message"), dict) else {}
    content = str(message.get("content", "")) if isinstance(message, dict) else ""
    out: dict[str, Any] = {
        "done_reason": body.get("done_reason"),
        "prompt_tokens": body.get("prompt_eval_count"),
        "generated_tokens": body.get("eval_count"),
        "thinking_chars": len(str(message.get("thinking", ""))) if isinstance(message, dict) else 0,
    }
    if question.kind == "free_text":
        return out | {
            "answer": content,
            "parse": "free text" if content.strip() else "empty output",
        }
    if body.get("done_reason") == "length":
        return out | {"answer": None, "parse": "generation token limit reached"}
    value, repairs = extract_json(content)
    out["parse"] = "; ".join(repairs) or "ok"
    if not isinstance(value, dict):
        return out | {"answer": None}
    if question.kind == "choice":
        choice = value.get("image")
        valid = type(choice) is int and 1 <= choice <= n_images
        return out | {
            "answer": choice if valid else None,
            "choice_probabilities": choice_probabilities(body.get("logprobs"), n_images),
        }
    answer = value.get(question.answer_key)
    confidence = value.get("confidence")
    conf = (
        float(confidence)
        if isinstance(confidence, int | float) and not isinstance(confidence, bool)
        else None
    )
    conf = None if conf is None or not 0.0 <= conf <= 1.0 else conf
    valid_answer = answer if isinstance(answer, str) and answer in {"yes", "no"} else None
    stated = None
    if valid_answer is not None and conf is not None:
        stated = conf if valid_answer == "yes" else 1.0 - conf
    return out | {
        "answer": valid_answer,
        "confidence": conf,
        "stated_p_yes": stated,
        "p_yes": yes_probability(body.get("logprobs")),
    }


# -- metrics ----------------------------------------------------------------------------


def _auroc(y: np.ndarray[Any, Any], s: np.ndarray[Any, Any]) -> float | None:
    return auroc_auprc(y, s)[0]


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def _rate(num: int, den: int) -> float | None:
    return num / den if den else None


def binary_metrics(records: Sequence[dict[str, Any]], *, n_boot: int, seed: int) -> dict[str, Any]:
    """Slice-level AUROC (logprob and stated scores) with patient bootstrap, rates, counts."""
    usable = [r for r in records if r["truth"] in {0, 1}]
    out: dict[str, Any] = {
        "n": len(usable),
        "n_positive": sum(1 for r in usable if r["truth"] == 1),
        "n_negative": sum(1 for r in usable if r["truth"] == 0),
        "unparsed": sum(1 for r in usable if r.get("answer") is None),
        "patients": len({r["patient"] for r in usable}),
    }
    for score in ("p_yes", "stated_p_yes"):
        rows = [r for r in usable if r.get(score) is not None]
        y = np.asarray([r["truth"] for r in rows], dtype=np.int_)
        s = np.asarray([r[score] for r in rows], dtype=np.float64)
        ci = (
            bootstrap_ci(y, s, [r["patient"] for r in rows], _auroc, n_boot=n_boot, seed=seed)
            if n_boot
            else None
        )
        out[f"auroc_{score}"] = _round(_auroc(y, s))
        out[f"auroc_{score}_ci95"] = [round(ci[0], 3), round(ci[1], 3)] if ci else None
        out[f"n_{score}"] = len(rows)
        out[f"distinct_{score}"] = len({round(float(v), 4) for v in s})
    answered = [r for r in usable if r.get("answer") in {"yes", "no"}]
    pos = [r for r in answered if r["truth"] == 1]
    neg = [r for r in answered if r["truth"] == 0]
    out["sensitivity"] = _round(_rate(sum(r["answer"] == "yes" for r in pos), len(pos)))
    out["specificity"] = _round(_rate(sum(r["answer"] == "no" for r in neg), len(neg)))
    out["yes_rate_negatives"] = _round(_rate(sum(r["answer"] == "yes" for r in neg), len(neg)))
    out["yes_rate_positives"] = _round(_rate(sum(r["answer"] == "yes" for r in pos), len(pos)))
    out["mean_p_yes_positives"] = _round(_mean([r.get("p_yes") for r in usable if r["truth"] == 1]))
    out["mean_p_yes_negatives"] = _round(_mean([r.get("p_yes") for r in usable if r["truth"] == 0]))
    return out


def _mean(values: Sequence[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None


def paired_win_rate(
    records: Sequence[dict[str, Any]], positive: str, negative: str
) -> dict[str, Any]:
    """Fraction of groups where P(yes) of *positive* exceeds *negative* (ties count 0.5)."""
    by_group: dict[str, dict[str, float]] = defaultdict(dict)
    for r in records:
        if r.get("p_yes") is not None:
            by_group[r["group"]][r["condition"]] = r["p_yes"]
    wins = []
    for values in by_group.values():
        if positive in values and negative in values:
            diff = values[positive] - values[negative]
            wins.append(1.0 if diff > 0 else 0.5 if diff == 0 else 0.0)
    return {"pairs": len(wins), "win_rate": _round(_mean(wins))}


def _split(
    records: Sequence[dict[str, Any]], *keys: str
) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    out: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        out[tuple(r.get(k) for k in keys)].append(r)
    return dict(sorted(out.items(), key=lambda kv: [str(v) for v in kv[0]]))


def image_dependence_metrics(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per model/window/layout/source: answer and P(yes) per condition plus deltas to real."""
    rows: list[dict[str, Any]] = []
    # Group is a patient/phantom pair identifier; it can contain both sphere and control.
    # Compare perturbations of the same source image set, never overwrite another source.
    sources = [
        r | {"source_key": str(r.get("key", r["group"])).removesuffix(f"-{r['condition']}")}
        for r in records
    ]
    for (model, window, layout, group), recs in _split(
        sources, "model", "window", "layout", "source_key"
    ).items():
        by = {r["condition"]: r for r in recs}
        real = by.get("real", {})
        row: dict[str, Any] = {
            "model": model,
            "window": window,
            "layout": layout,
            "source": group,
            "truth": real.get("truth"),
        }
        for condition, r in by.items():
            row[condition] = {
                "answer": r.get("answer"),
                "confidence": r.get("confidence"),
                "p_yes": _round(r.get("p_yes"), 4),
                "prompt_tokens": r.get("prompt_tokens"),
            }
            if condition != "real" and real.get("p_yes") is not None and r.get("p_yes") is not None:
                row[f"delta_p_yes_{condition}"] = _round(real["p_yes"] - r["p_yes"], 4)
        answers = {c: r.get("answer") for c, r in by.items()}
        row["same_answer_real_gray_noise"] = (
            len({answers.get(c) for c in ("real", "gray", "noise") if c in answers}) == 1
        )
        rows.append(row)
    return rows


def obvious_target_metrics(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per model/window/layout/condition: yes-rate and mean P(yes); paired wins vs none."""
    rows: list[dict[str, Any]] = []
    for (model, window, layout), recs in _split(records, "model", "window", "layout").items():
        for (condition,), cond in _split(recs, "condition").items():
            answered = [r for r in cond if r.get("answer") in {"yes", "no"}]
            row: dict[str, Any] = {
                "model": model,
                "window": window,
                "layout": layout,
                "condition": condition,
                "n": len(cond),
                "yes": sum(r["answer"] == "yes" for r in answered),
                "unparsed": len(cond) - len(answered),
                "mean_p_yes": _round(_mean([r.get("p_yes") for r in cond]), 4),
                "nodule_level_sampled": sum(bool(r.get("nodule_level_sampled")) for r in cond),
            }
            if condition != "none":
                row |= paired_win_rate(recs, condition, "none")
                sub = [
                    r
                    for r in recs
                    if r["condition"] in {condition, "none"} and r.get("p_yes") is not None
                ]
                row["auroc_vs_none"] = _round(
                    _auroc(
                        np.asarray([r["truth"] for r in sub]), np.asarray([r["p_yes"] for r in sub])
                    )
                )
            rows.append(row)
    return rows


def binding_metrics(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per model/window/layout: correct choices (criterion >= 90 %), answer histogram."""
    rows: list[dict[str, Any]] = []
    for (model, window, layout), recs in _split(records, "model", "window", "layout").items():
        p_truth = [
            (r.get("choice_probabilities") or {}).get(r["truth"])
            if r.get("choice_probabilities")
            else None
            for r in recs
        ]
        correct = sum(r.get("answer") == r["truth"] for r in recs)
        rows.append(
            {
                "model": model,
                "window": window,
                "layout": layout,
                "n": len(recs),
                "correct": correct,
                "chance": round(len(recs) / max(len(recs[0]["captions"]), 1), 1),
                "passes_90pct": correct >= math.ceil(0.9 * len(recs)),
                "mean_p_correct": _round(_mean(p_truth), 3),
                "answers": dict(sorted(Counter(str(r.get("answer")) for r in recs).items())),
            }
        )
    return rows


def paired_slab_metrics(
    records: Sequence[dict[str, Any]], *, n_boot: int, seed: int
) -> list[dict[str, Any]]:
    """Per model/window: binary metrics, paired win rate and sensitivity by size bin."""
    rows: list[dict[str, Any]] = []
    for (model, window), recs in _split(records, "model", "window").items():
        row: dict[str, Any] = {"model": model, "window": window}
        row |= binary_metrics(recs, n_boot=n_boot, seed=seed)
        row |= {f"paired_{k}": v for k, v in paired_win_rate(recs, "lesion", "control").items()}
        bins: dict[str, Any] = {}
        for (size,), group in _split([r for r in recs if r["truth"] == 1], "size_bin").items():
            answered = [r for r in group if r.get("answer") in {"yes", "no"}]
            bins[str(size)] = {
                "n": len(group),
                "yes": sum(r["answer"] == "yes" for r in answered),
                "mean_p_yes": _round(_mean([r.get("p_yes") for r in group]), 3),
            }
        row["by_size"] = bins
        rows.append(row)
    return rows


def compute_metrics(cfg: SanityConfig, records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Test-specific aggregate tables."""
    if cfg.test == "image_dependence":
        return {"rows": image_dependence_metrics(records)}
    if cfg.test == "obvious_target":
        return {
            "rows": obvious_target_metrics(records),
            "overall": [
                {"model": m, "window": w, "layout": lay}
                | binary_metrics(recs, n_boot=0, seed=cfg.seed)
                for (m, w, lay), recs in _split(records, "model", "window", "layout").items()
            ],
        }
    if cfg.test == "position_binding":
        return {"rows": binding_metrics(records)}
    if cfg.test == "paired_slab":
        return {"rows": paired_slab_metrics(records, n_boot=cfg.n_boot, seed=cfg.seed)}
    return {
        "rows": [
            {"model": r["model"], "key": r["key"], "chars": len(r.get("answer") or "")}
            for r in records
        ]
    }


# -- run --------------------------------------------------------------------------------


@dataclass
class SanityRun:
    """Result of one invocation."""

    folder: Path
    result: dict[str, Any]
    markdown: str


def _source_hash() -> str:
    package = Path(__file__).resolve().parents[1]
    return sha256_of_obj(
        {
            str(path.relative_to(package)): sha256_of_file(path)
            for path in sorted(package.rglob("*"))
            if path.is_file() and path.suffix in {".py", ".yaml"}
        }
    )


def _data_identity(cfg: SanityConfig, settings: Settings) -> dict[str, Any]:
    if cfg.lidc is None:
        return {}
    dataset = cfg.lidc.dataset
    split = settings.data_path("splits", f"{dataset}.json")
    manifest = settings.manifests_dir / "splits" / f"{dataset}.json"
    return {
        "index": sha256_of_file(index_path(settings, dataset)),
        "split": sha256_of_file(split) if split.is_file() else None,
        "split_manifest": sha256_of_file(manifest) if manifest.is_file() else None,
    }


def _units(
    cfg: SanityConfig, models: Sequence[str], items: Sequence[si.SanityItem]
) -> list[tuple[str, si.SanityItem, str]]:
    """(model, item, layout) per model in config order; seeded random order within a model."""
    units: list[tuple[str, si.SanityItem, str]] = []
    for number, model in enumerate(models):
        mine = [
            (model, item, layout)
            for item in items
            for layout in (cfg.layouts if len(item.images) > 1 else cfg.layouts[:1])
        ]
        order = np.random.default_rng(cfg.seed + number).permutation(len(mine))
        units.extend(mine[int(k)] for k in order)
    return units


def _record(model: str, item: si.SanityItem, layout: str, parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": model,
        "key": item.key,
        "group": item.group,
        "condition": item.condition,
        "layout": layout,
        "truth": item.truth,
        "patient": item.patient,
        "window": item.meta.get("window"),
        "size_bin": item.meta.get("size_bin"),
        "nodule_level_sampled": item.meta.get("nodule_level_sampled"),
        "n_images": len(item.images),
        "captions": list(item.captions),
    } | parsed


def run_sanity(  # noqa: PLR0915 - one ordered build/persist/aggregate transaction
    loaded: LoadedSanity,
    settings: Settings,
    *,
    limit: int | None = None,
    progress: Callable[[str], None] = lambda _msg: None,
    client: httpx.Client | None = None,
    open_case: si.OpenStudy = open_study,
) -> SanityRun:
    """Build inputs, run every request once, persist artifacts and aggregate metrics.

    Raises:
        ValueError: on a changed config file, a non-Ollama or unavailable model, or a
            results path outside ``data/results``.
        thoraxbench.splits.SealedAccessError: if a case fails the calibration guard.
    """
    from thoraxbench.reports.html_report import require_results_path  # noqa: PLC0415

    started = time.perf_counter()
    cfg = loaded.config
    if sha256_of_file(loaded.path) != loaded.file_sha256:
        raise ValueError("Sanity config changed after loading")
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    require_local_endpoint(settings.ollama_url)
    base = settings.data_path("results", "benchmark", cfg.id)
    require_results_path(base / "preflight", settings)
    models: dict[str, ModelConfig] = {}
    runtime: dict[str, Any] = {}
    for model_id in cfg.models:
        model = load_model_config(model_id, settings.configs_dir / "models")
        if model.adapter != "ollama" or not model.tag:
            raise ValueError(f"sanity tests need an Ollama model; {model_id} is {model.adapter}")
        runtime[model_id] = runtime_identity(model, settings)
        if runtime[model_id].get("digest") is None:
            raise ValueError(
                f"model {model_id} ({model.tag}) is not available at the local endpoint"
            )
        models[model_id] = model
    items, counts = build_items(cfg, settings, open_case)
    items = limit_groups(items, limit)
    if not items:
        raise ValueError("no sanity inputs were selected")
    identity = {
        "schema_version": 1,
        "sanity_version": SANITY_VERSION,
        "config_file": loaded.file_sha256,
        "config": cfg.model_dump(mode="json"),
        "limit": limit,
        "models": {
            m: {
                "model": c.model_dump(mode="json"),
                "model_file": sha256_of_file(settings.configs_dir / "models" / f"{m}.yaml"),
            }
            for m, c in models.items()
        },
        "runtime_models": runtime,
        "source_hash": _source_hash(),
        "git_commit": git_state(settings.repo_root)[0],
        "data": _data_identity(cfg, settings),
        "selection": counts,
        "items": [item.describe() for item in items],
    }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    folder = base / f"{stamp}-{loaded.file_sha256[:12]}-{uuid4().hex}"
    require_results_path(folder / "manifest.json", settings)
    folder.mkdir(parents=True, exist_ok=False)
    store = BenchmarkStore(folder, settings)
    own_client = client is None
    http = client or httpx.Client(trust_env=False, follow_redirects=False)
    records: list[dict[str, Any]] = []
    try:
        with store.locked():
            store.initialize(identity, resume=False)
            progress(f"Invocation: {folder}")
            units = _units(cfg, list(models), items)
            for number, (model_id, item, layout) in enumerate(units, start=1):
                model = models[model_id]
                payload = build_payload(item, layout, cfg, model)
                body, diagnostic = post_chat(http, settings.ollama_url, payload, model.timeout_s)
                parsed = parse_answer(cfg.question, body, len(item.captions))
                record = _record(model_id, item, layout, parsed) | {
                    "latency_s": round(float(diagnostic.get("latency_s", 0.0)), 3),
                    "error": diagnostic.get("error"),
                }
                key = sha256_of_obj([model_id, item.key, layout])
                store.save_unit(
                    key,
                    {
                        "schema_version": 1,
                        "unit": key,
                        "item": item.describe(),
                        "request": redact_payload(payload),
                        "response": diagnostic,
                        "record": record,
                    },
                    float(diagnostic.get("latency_s", 0.0)),
                )
                records.append(record)
                progress(
                    f"[{number}/{len(units)}] {model_id} {item.key} {layout}: "
                    f"{str(record.get('answer'))[:40]!r} p_yes={record.get('p_yes')}"
                )
            metrics = compute_metrics(cfg, records)
            result = {
                "experiment_id": cfg.id,
                "test": cfg.test,
                "title": cfg.title,
                "config_path": loaded.path.name,
                "config_sha256": loaded.file_sha256,
                "config": cfg.model_dump(mode="json"),
                "started_at": store.state.started_at,
                "runtime_s": round(time.perf_counter() - started, 1),
                "limit": limit,
                "runtime_models": runtime,
                "selection": counts,
                "n_items": len(items),
                "n_requests": len(records),
                "metrics": metrics,
                "records": records,
                "framing": FRAMING,
                "disclaimer": DISCLAIMER,
            }
            markdown = render_markdown(result)
            store.state.active_runtime_s = time.perf_counter() - started
            store.finish(json.dumps(result, indent=1) + "\n", markdown)
    finally:
        if own_client:
            http.close()
    return SanityRun(folder, result, markdown)


# -- report -----------------------------------------------------------------------------


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, list):
        return "[" + ", ".join(_fmt(v) for v in value) + "]"
    return str(value).replace("|", "\\|")


def _table(rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> list[str]:
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines.extend("| " + " | ".join(_fmt(row.get(c)) for c in columns) + " |" for row in rows)
    return lines


def _cell(value: object) -> str:
    if not isinstance(value, dict):
        return "n/a"
    return (
        f"{value.get('answer')} {_fmt(value.get('confidence'))} / P(yes) {_fmt(value.get('p_yes'))}"
    )


def render_markdown(result: dict[str, Any]) -> str:
    """Aggregate Markdown report; free text is JSON-escaped inside code spans."""
    test = result["test"]
    rows = result["metrics"]["rows"]
    lines = [
        f"# {result['experiment_id']} — {result['title'] or test}",
        "",
        result["framing"],
        "",
        f"Config SHA-256 `{result['config_sha256']}`; {result['n_items']} inputs, "
        f"{result['n_requests']} requests, {result['runtime_s']} s.",
        "",
    ]
    if test == "image_dependence":
        conditions = result["config"]["conditions"]
        view = [
            {k: v for k, v in row.items() if k in {"model", "window", "layout", "source", "truth"}}
            | {c: _cell(row.get(c)) for c in conditions}
            | {"same answer real/gray/noise": row["same_answer_real_gray_noise"]}
            for row in rows
        ]
        lines += _table(
            view,
            [
                "model",
                "window",
                "layout",
                "source",
                "truth",
                *conditions,
                "same answer real/gray/noise",
            ],
        )
    elif test == "obvious_target":
        lines += _table(
            rows,
            [
                "model",
                "window",
                "layout",
                "condition",
                "n",
                "yes",
                "unparsed",
                "mean_p_yes",
                "win_rate",
                "auroc_vs_none",
                "nodule_level_sampled",
            ],
        )
    elif test == "position_binding":
        view = [row | {"answers": json.dumps(row["answers"])} for row in rows]
        lines += _table(
            view,
            [
                "model",
                "window",
                "layout",
                "n",
                "correct",
                "chance",
                "passes_90pct",
                "mean_p_correct",
                "answers",
            ],
        )
    elif test == "paired_slab":
        lines += _table(
            rows,
            [
                "model",
                "window",
                "n_positive",
                "n_negative",
                "patients",
                "unparsed",
                "auroc_p_yes",
                "auroc_p_yes_ci95",
                "auroc_stated_p_yes",
                "auroc_stated_p_yes_ci95",
                "distinct_p_yes",
                "sensitivity",
                "specificity",
                "yes_rate_negatives",
                "paired_win_rate",
            ],
        )
        lines.append("")
        for row in rows:
            lines.append(
                f"- {row['model']} / {row['window']} by size: `{json.dumps(row['by_size'])}`"
            )
    else:
        for record in result["records"]:
            lines.append(
                f"- **{record['model']}** `{record['key']}`: `{json.dumps(record.get('answer'))}`"
            )
    lines += ["", result["disclaimer"], ""]
    return "\n".join(lines)
