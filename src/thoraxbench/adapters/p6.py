# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""P6: one condition on one prepared image, reasoning then a short binary answer.

This is a local official-style adaptation, not Hugging Face/runtime parity. The final
call uses no images: it classifies the preserved reasoning from the first visual call.
Scores therefore reflect that two-stage procedure, not an independent visual judgement.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Any

from thoraxbench.adapters.ollama import NS_PER_S, OllamaModel, _total
from thoraxbench.schemas import AnalysisRequest, Finding, FindingsReport, PreparedInput, RawOutput

P6_PROTOCOL_VERSION = "2"
P6_REASONING_TOKENS = 192
P6_ANSWER_TOKENS = 16
P6_TOP_LOGPROBS = 20


def binary_answer_probability(data: dict[str, Any]) -> float | None:
    """P(yes) within visible yes/no alternatives of the short answer call only.

    Require both alternatives. A truncated top list does not prove zero probability.
    Ignore non-finite/provider-invalid numbers and reasoning tokens. String enum output
    can have separate quote tokens; locate its sole yes/no token and normalize there.
    """
    logprobs = data.get("logprobs")
    if not isinstance(logprobs, list):
        return None
    for entry in logprobs:
        if not isinstance(entry, dict):
            continue
        token = str(entry.get("token", "")).strip().strip('"').lower()
        if token not in {"yes", "no"}:
            continue
        alternatives = entry.get("top_logprobs")
        if not isinstance(alternatives, list):
            return None
        logs: dict[str, list[float]] = {"yes": [], "no": []}
        for alternative in alternatives:
            if not isinstance(alternative, dict):
                continue
            word = str(alternative.get("token", "")).strip().strip('"').lower()
            value = alternative.get("logprob")
            if (
                word in logs
                and isinstance(value, int | float)
                and not isinstance(value, bool)
                and math.isfinite(value)
            ):
                logs[word].append(float(value))
        if not all(logs.values()):
            return None
        maximum = max(value for values in logs.values() for value in values)
        mass = {
            word: sum(math.exp(value - maximum) for value in values)
            for word, values in logs.items()
        }
        return mass["yes"] / (mass["yes"] + mass["no"])
    return None


def nonconstant_readiness(rows: Sequence[tuple[bool, bool | None, float | None]]) -> dict[str, Any]:
    """Separate categorical nonconstancy from score discrimination on calibration only.

    This descriptive gate needs both reference classes and complete probability coverage.
    A nonconstant score alone does not pass the categorical gate. No tuning is performed.
    """
    complete = [
        (truth, answer, score)
        for truth, answer, score in rows
        if answer is not None and score is not None
    ]
    both_classes = {truth for truth, _, _ in complete} == {False, True}
    nonconstant_answers = len({answer for _, answer, _ in complete}) > 1
    positives = [score for truth, _, score in complete if truth]
    negatives = [score for truth, _, score in complete if not truth]
    comparisons = [
        float(pos > neg) + 0.5 * float(pos == neg) for pos in positives for neg in negatives
    ]
    auroc = sum(comparisons) / len(comparisons) if comparisons else None
    return {
        "n": len(rows),
        "scored": len(complete),
        "both_reference_classes": both_classes,
        "nonconstant_answers": nonconstant_answers,
        "score_auroc": auroc,
        "passes": bool(rows)
        and len(complete) == len(rows)
        and both_classes
        and nonconstant_answers
        and auroc is not None
        and auroc > 0.5,
        "framing": "Calibration readiness only; no accuracy or held-out claim.",
    }


def _extract_binary(
    second: dict[str, Any], expected: str
) -> tuple[bool | None, float | None, str | None]:
    content = second.get("message", {}).get("content", "").strip()
    if second.get("done_reason") == "length":
        return None, None, "answer generation token limit reached"
    if content not in {'"yes"', '"no"'}:
        return None, None, "invalid constrained binary answer"
    if content.strip('"').lower() != expected.lower():
        return None, None, "binary extraction contradicts the visual final answer"
    probability = binary_answer_probability(second)
    reason = None if probability is not None else "both yes/no answer-token logprobs unavailable"
    return content == '"yes"', probability, reason


class P6OllamaModel(OllamaModel):
    """Single-image fallback protocol; no unsupported multi-image citations or fallback."""

    def _query_label(
        self,
        label: str,
        prepared: PreparedInput,
        limits: dict[str, Any],
        *,
        requests: list[dict[str, Any]],
        responses: list[dict[str, Any]],
    ) -> tuple[bool | None, float | None, str | None, float, list[dict[str, Any]]]:
        latency = 0.0
        calls: list[dict[str, Any]] = []
        rendered = self.prompt.render([label], 1, prepared.image_captions, "")
        first, error, elapsed = self._chat(
            rendered.system,
            rendered.user,
            prepared.images,
            None,
            request_log=requests,
            response_log=responses,
            option_overrides={"num_predict": limits["reasoning_tokens"]},
        )
        latency += elapsed
        if first is not None:
            calls.append(first)
        answer: bool | None = None
        probability: float | None = None
        reason = error
        if first is not None and error is None:
            reasoning = first.get("message", {}).get("content", "")
            if first.get("done_reason") == "length":
                reason = "reasoning generation token limit reached"
            elif not reasoning.strip():
                reason = "empty reasoning"
            elif not (
                final_match := re.search(
                    r"Final Answer:\s*(yes|no)[.!]?\s*$", reasoning, re.IGNORECASE
                )
            ):
                reason = "reasoning missing explicit final answer"
            else:
                second_prompt = self.prompt.render_second_pass(reasoning, [label], 1, context="")
                second, error, elapsed = self._chat(
                    second_prompt.system,
                    second_prompt.user,
                    [],
                    {"type": "string", "enum": ["yes", "no"]},
                    request_log=requests,
                    response_log=responses,
                    option_overrides={"num_predict": limits["answer_tokens"]},
                    top_logprobs=limits["top_logprobs"],
                )
                latency += elapsed
                if second is not None:
                    calls.append(second)
                reason = error
                if second is not None and error is None:
                    answer, probability, reason = _extract_binary(second, final_match[1])
        return answer, probability, reason, latency, calls

    def infer(self, prepared: PreparedInput, request: AnalysisRequest) -> RawOutput:
        """Run one independent two-stage request per canonical condition on one image."""
        configured = self.config.options.get("p6", {})
        if not isinstance(configured, dict) or set(configured) - {
            "reasoning_tokens",
            "answer_tokens",
            "top_logprobs",
        }:
            return RawOutput(error="invalid P6 protocol options")
        limits = {
            "reasoning_tokens": P6_REASONING_TOKENS,
            "answer_tokens": P6_ANSWER_TOKENS,
            "top_logprobs": P6_TOP_LOGPROBS,
        } | configured
        maxima = {"reasoning_tokens": 512, "answer_tokens": 32, "top_logprobs": 20}
        if any(
            type(value) is not int or not 1 <= value <= maxima[key] for key, value in limits.items()
        ):
            return RawOutput(error="invalid P6 protocol token/logprob limits")
        if len(prepared.images) != 1:
            return RawOutput(
                error="P6 requires exactly one prepared image; image binding is unverified"
            )
        labels = self._labels(request)
        if len(set(labels)) != len(labels) or set(labels) - set(self.ontology.ids()):
            return RawOutput(error="P6 requires unique canonical label identifiers")
        requests: list[dict[str, Any]] = []
        responses: list[dict[str, Any]] = []
        calls: list[dict[str, Any]] = []
        findings: list[Finding] = []
        diagnostics: list[dict[str, Any]] = []
        latency = 0.0
        for label in labels:
            answer, probability, reason, elapsed, label_calls = self._query_label(
                label,
                prepared,
                limits,
                requests=requests,
                responses=responses,
            )
            latency += elapsed
            calls.extend(label_calls)
            # P6 scores by the logprob P(yes); it sets the direction, the text answer stays
            # in the diagnostics. The confidence is the strength of that direction.
            present, confidence = answer, None
            if probability is not None and answer is not None:
                present, confidence = probability >= 0.5, max(probability, 1.0 - probability)
            findings.append(
                Finding(
                    label=label,
                    present=present,
                    confidence=confidence,
                    source="model",
                    description="P6 single-image answer; no model-localized image citation.",
                )
            )
            diagnostics.append(
                {"label": label, "answer": answer, "p_yes": probability, "reason": reason}
            )
        report = FindingsReport(
            findings=findings,
            abstain=not any(f.confidence is not None for f in findings),
            parse_warnings=[f"{d['label']}: {d['reason']}" for d in diagnostics if d["reason"]],
            uncertainty="Uncalibrated P6 conditional answer-token scores; no image localization.",
        )
        meta: dict[str, Any] = {
            "model": self.tag,
            "prompt_id": "P6",
            "prompt_sha256": self.prompt.sha256,
            "protocol_version": P6_PROTOCOL_VERSION,
            "requests": requests,
            "responses": responses,
            "label_diagnostics": diagnostics,
            "calls": len(calls),
            "protocol_options": limits,
            "image_association": "sole prepared input; no model-returned citation",
        }
        for field in ("load_duration", "eval_duration", "total_duration"):
            value = _total(calls, field)
            meta[f"{field}_s"] = value / NS_PER_S if value is not None else None
        generated, tokens = _total(calls, "eval_count"), _total(calls, "prompt_eval_count")
        return RawOutput(
            text=report.model_dump_json(),
            latency_s=latency,
            meta=meta,
            tokens_generated=int(generated) if generated is not None else None,
            prompt_tokens=int(tokens) if tokens is not None else None,
        )

    def parse(self, raw: RawOutput) -> FindingsReport:
        """Read the canonical synthesized report; preserve provider failures as abstention."""
        if raw.error:
            return FindingsReport(abstain=True, parse_warnings=[raw.error])
        return FindingsReport.model_validate_json(raw.text)
