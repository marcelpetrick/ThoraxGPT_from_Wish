# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Threshold fitting, temperature/Platt/isotonic calibration and abstention rules."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt
from scipy.optimize import minimize_scalar
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_curve

FloatArray = npt.NDArray[np.float64]
EPS = 1e-6
SEALED = "sealed"


def check_phase(phase: str | None) -> None:
    """Raise ``ValueError`` when asked to fit on the sealed split."""
    if phase == SEALED:
        msg = "calibration must never be fitted on the sealed validation split"
        raise ValueError(msg)


def _arrays(y: Sequence[int | bool], p: Sequence[float]) -> tuple[FloatArray, FloatArray]:
    ya = np.asarray(y, dtype=np.float64)
    pa = np.asarray(p, dtype=np.float64)
    if ya.shape != pa.shape or ya.size == 0:
        msg = "y and p must be non-empty and of equal length"
        raise ValueError(msg)
    return ya, pa


def _logit(p: FloatArray) -> FloatArray:
    q = np.clip(p, EPS, 1 - EPS)
    return np.asarray(np.log(q / (1 - q)), dtype=np.float64)


def _sigmoid(z: FloatArray) -> FloatArray:
    return np.asarray(1.0 / (1.0 + np.exp(-z)), dtype=np.float64)


def _nll(y: FloatArray, p: FloatArray) -> float:
    q = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))


def fit_thresholds(
    y_true: dict[str, Sequence[int | bool]],
    y_score: dict[str, Sequence[float]],
    *,
    method: str = "youden",
    target_sensitivity: float = 0.9,
    phase: str | None = None,
    default: float = 0.5,
) -> dict[str, float]:
    """Fit one decision threshold per label.

    ``method="youden"`` maximises ``sensitivity + specificity - 1``;
    ``method="sensitivity"`` picks the highest threshold reaching *target_sensitivity*.
    Labels with a single reference class fall back to *default*.
    """
    check_phase(phase)
    if method not in {"youden", "sensitivity"}:
        msg = f"unknown threshold method {method}"
        raise ValueError(msg)
    out: dict[str, float] = {}
    for label, ys in y_true.items():
        y, p = _arrays(ys, y_score[label])
        if len(np.unique(y)) < 2:
            out[label] = default
            continue
        fpr, tpr, thr = roc_curve(y, p)
        finite = np.isfinite(thr)
        fpr, tpr, thr = fpr[finite], tpr[finite], thr[finite]
        if method == "youden":
            out[label] = float(thr[int(np.argmax(tpr - fpr))])
        else:
            ok = np.flatnonzero(tpr >= target_sensitivity)
            out[label] = float(thr[ok[0]]) if ok.size else float(thr[-1])
    return out


class Calibrator(Protocol):
    """Common interface of every calibrator."""

    kind: str

    def fit(
        self, y: Sequence[int | bool], p: Sequence[float], *, phase: str | None = None
    ) -> Calibrator:
        """Fit on development data."""
        ...

    def transform(self, p: Sequence[float]) -> FloatArray:
        """Map raw probabilities to calibrated probabilities."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Return serialisable parameters."""
        ...


@dataclass
class TemperatureScaler:
    """Single-temperature scaling of logits: ``sigmoid(logit(p) / T)``."""

    temperature: float = 1.0
    kind: str = "temperature"

    def fit(
        self, y: Sequence[int | bool], p: Sequence[float], *, phase: str | None = None
    ) -> TemperatureScaler:
        """Fit ``T`` by minimising the negative log-likelihood (bounded to [0.05, 20])."""
        check_phase(phase)
        ya, pa = _arrays(y, p)
        z = _logit(pa)
        res = minimize_scalar(
            lambda t: _nll(ya, _sigmoid(z / t)), bounds=(0.05, 20.0), method="bounded"
        )
        self.temperature = float(res.x)
        return self

    def transform(self, p: Sequence[float]) -> FloatArray:
        """Apply the fitted temperature."""
        return _sigmoid(_logit(np.asarray(p, dtype=np.float64)) / self.temperature)

    def to_dict(self) -> dict[str, Any]:
        """Return serialisable parameters."""
        return {"kind": self.kind, "temperature": self.temperature}


@dataclass
class PlattCalibrator:
    """Platt scaling on logits: ``sigmoid(a * logit(p) + b)``."""

    a: float = 1.0
    b: float = 0.0
    kind: str = "platt"

    def fit(
        self, y: Sequence[int | bool], p: Sequence[float], *, phase: str | None = None
    ) -> PlattCalibrator:
        """Fit ``a, b`` with unregularised logistic regression on the logit."""
        from sklearn.linear_model import LogisticRegression  # noqa: PLC0415 - heavy import

        check_phase(phase)
        ya, pa = _arrays(y, p)
        if len(np.unique(ya)) < 2:
            msg = "Platt scaling needs both classes"
            raise ValueError(msg)
        lr = LogisticRegression(C=1e6)
        lr.fit(_logit(pa).reshape(-1, 1), ya.astype(int))
        self.a = float(lr.coef_[0][0])
        self.b = float(lr.intercept_[0])
        return self

    def transform(self, p: Sequence[float]) -> FloatArray:
        """Apply the fitted affine map on the logit."""
        return _sigmoid(self.a * _logit(np.asarray(p, dtype=np.float64)) + self.b)

    def to_dict(self) -> dict[str, Any]:
        """Return serialisable parameters."""
        return {"kind": self.kind, "a": self.a, "b": self.b}


@dataclass
class IsotonicCalibrator:
    """Monotone, piecewise-linear isotonic regression calibration."""

    x: list[float] = field(default_factory=list)
    y: list[float] = field(default_factory=list)
    kind: str = "isotonic"

    def fit(
        self, y: Sequence[int | bool], p: Sequence[float], *, phase: str | None = None
    ) -> IsotonicCalibrator:
        """Fit the isotonic map and keep its breakpoints for serialisation."""
        check_phase(phase)
        ya, pa = _arrays(y, p)
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        iso.fit(pa, ya)
        self.x = [float(v) for v in iso.X_thresholds_]
        self.y = [float(v) for v in iso.y_thresholds_]
        return self

    def transform(self, p: Sequence[float]) -> FloatArray:
        """Interpolate the fitted breakpoints (identity when unfitted)."""
        pa = np.asarray(p, dtype=np.float64)
        if not self.x:
            return pa
        return np.asarray(np.interp(pa, self.x, self.y), dtype=np.float64)

    def to_dict(self) -> dict[str, Any]:
        """Return serialisable parameters."""
        return {"kind": self.kind, "x": self.x, "y": self.y}


def calibrator_from_dict(data: dict[str, Any]) -> Calibrator:
    """Rebuild a calibrator from :meth:`to_dict` output."""
    kind = data.get("kind")
    if kind == "temperature":
        return TemperatureScaler(temperature=float(data["temperature"]))
    if kind == "platt":
        return PlattCalibrator(a=float(data["a"]), b=float(data["b"]))
    if kind == "isotonic":
        return IsotonicCalibrator(x=list(data["x"]), y=list(data["y"]))
    msg = f"unknown calibrator kind {kind}"
    raise ValueError(msg)


@dataclass
class AbstentionRule:
    """Abstain when the calibrated probability lies inside ``[low, high]``."""

    low: float = 0.35
    high: float = 0.65

    def __post_init__(self) -> None:
        if not 0.0 <= self.low <= self.high <= 1.0:
            msg = "need 0 <= low <= high <= 1"
            raise ValueError(msg)

    def abstains(self, p: float) -> bool:
        """Whether a decision with probability *p* should be withheld."""
        return self.low <= p <= self.high

    def decide(self, p: float, threshold: float = 0.5) -> bool | None:
        """``True``/``False`` decision, or ``None`` when abstaining."""
        return None if self.abstains(p) else p >= threshold

    def to_dict(self) -> dict[str, Any]:
        """Return serialisable parameters."""
        return {"low": self.low, "high": self.high}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AbstentionRule:
        """Rebuild from :meth:`to_dict` output."""
        return cls(low=float(data["low"]), high=float(data["high"]))
