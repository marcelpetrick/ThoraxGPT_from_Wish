# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Task E: clinical factuality of generated reports, plus secondary text-overlap metrics.

Factuality compares available implied-presence decisions against known reference labels.
Missing predictions count as omissions, never as agreements. BLEU-1 and ROUGE-L are
descriptive only (Vision §13 Task E).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from thoraxbench.schemas import FindingsReport
from thoraxbench.scoring.classification import safe_div
from thoraxbench.scoring.records import CaseRecord


def asserted_labels(report: FindingsReport) -> dict[str, bool]:
    """Labels the report commits to: ``True`` present, ``False`` explicitly absent."""
    labels = {f.label for f in report.findings} | set(report.negative_findings)
    return {
        label: probability >= 0.5
        for label in labels
        if (probability := report.label_probability(label)) is not None
    }


@dataclass
class FactualityCounts:
    """Per-study or aggregated factuality counts."""

    agreements: int = 0
    contradictions: int = 0
    omissions: int = 0
    hallucinated_positives: int = 0
    reference_labels: int = 0
    available_predictions: int = 0

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation including the agreement rate."""
        data: dict[str, Any] = dict(vars(self))
        data["label_agreement"] = safe_div(self.agreements, self.reference_labels)
        data["prediction_coverage"] = safe_div(self.available_predictions, self.reference_labels)
        return data


def factuality(report: FindingsReport, reference: dict[str, bool | None]) -> FactualityCounts:
    """Compare asserted labels with known reference labels.

    * agreement: asserted value equals the reference;
    * contradiction: asserted value differs (a hallucinated positive is also counted here
      when the reference is negative);
    * omission: a known reference label has no available model prediction;
    * hallucinated positive: asserted present while reference is negative.
    """
    asserted = asserted_labels(report)
    c = FactualityCounts()
    for label, ref in reference.items():
        if ref is None:
            continue
        c.reference_labels += 1
        said = asserted.get(label)
        if said is None:
            c.omissions += 1
            continue
        c.available_predictions += 1
        if said == ref:
            c.agreements += 1
        else:
            c.contradictions += 1
            c.hallucinated_positives += int(said and not ref)
    return c


def task_e(cases: Sequence[CaseRecord]) -> FactualityCounts:
    """Aggregate factuality counts over all cases that have a report."""
    total = FactualityCounts()
    for case in cases:
        if case.report is None or case.report.abstain:
            continue
        c = factuality(case.report, case.y_true)
        total.agreements += c.agreements
        total.contradictions += c.contradictions
        total.omissions += c.omissions
        total.hallucinated_positives += c.hallucinated_positives
        total.reference_labels += c.reference_labels
        total.available_predictions += c.available_predictions
    return total


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def bleu1(candidate: str, reference: str) -> float:
    """Unigram BLEU with brevity penalty."""
    cand, ref = _tokens(candidate), _tokens(reference)
    if not cand or not ref:
        return 0.0
    ref_counts = Counter(ref)
    clipped = sum(min(n, ref_counts[w]) for w, n in Counter(cand).items())
    precision = clipped / len(cand)
    bp = 1.0 if len(cand) > len(ref) else math.exp(1 - len(ref) / len(cand))
    return bp * precision


def rouge_l(candidate: str, reference: str) -> float:
    """ROUGE-L F1 based on the longest common subsequence of tokens."""
    cand, ref = _tokens(candidate), _tokens(reference)
    if not cand or not ref:
        return 0.0
    prev = [0] * (len(ref) + 1)
    for a in cand:
        cur = [0]
        for j, b in enumerate(ref, start=1):
            cur.append(prev[j - 1] + 1 if a == b else max(prev[j], cur[j - 1]))
        prev = cur
    lcs = prev[-1]
    if lcs == 0:
        return 0.0
    p, r = lcs / len(cand), lcs / len(ref)
    return 2 * p * r / (p + r)
