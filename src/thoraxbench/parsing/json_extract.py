# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Extract one JSON value from free model text.

Generative models wrap JSON in code fences, prepend prose, leave trailing commas, use
single quotes or stop mid-object when they hit the token limit. :func:`extract_json` tries
increasingly forgiving repairs and reports every repair it applied, so that a repaired
output stays auditable.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")
_MAX_TRIM_STEPS = 50


def _loads(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _close_truncated(text: str) -> str:
    """Close open strings/brackets of a truncated JSON document."""
    stack: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
    out = text + ('"' if in_string else "")
    out = out.rstrip()
    if out.endswith(":"):
        out += " null"
    out = out.rstrip(",").rstrip()
    return out + "".join(reversed(stack))


def _repair_truncated(text: str) -> Any | None:
    candidate = text
    for _ in range(_MAX_TRIM_STEPS):
        value = _loads(_TRAILING_COMMA.sub(r"\1", _close_truncated(candidate)))
        if value is not None:
            return value
        cut = max(candidate.rfind(","), candidate.rfind("{", 0, len(candidate) - 1))
        if cut <= 0:
            return None
        candidate = candidate[:cut]
    return None  # pragma: no cover - needs > _MAX_TRIM_STEPS broken elements


def extract_json(text: str) -> tuple[Any | None, list[str]]:  # noqa: PLR0911 - repair ladder
    """Return ``(value, repairs)`` for the first JSON object/array in *text*.

    ``value`` is ``None`` when nothing usable was found. ``repairs`` lists the repairs
    applied (empty for clean JSON).
    """
    repairs: list[str] = []
    body = text.strip()
    if not body:
        return None, ["empty output"]
    fence = _FENCE.search(body)
    if fence:
        body = fence.group(1).strip()
        repairs.append("removed code fence")
    elif "```" in body:
        body = body.replace("```json", "").replace("```", "").strip()
        repairs.append("removed unterminated code fence")
    starts = [i for i in (body.find("{"), body.find("[")) if i >= 0]
    if not starts:
        return None, [*repairs, "no JSON object found"]
    start = min(starts)
    if start > 0:
        repairs.append("dropped leading prose")
    body = body[start:]
    end = max(body.rfind("}"), body.rfind("]"))
    complete = body[: end + 1] if end >= 0 else body

    value = _loads(complete)
    if value is not None:
        if len(complete) < len(body.rstrip()):
            repairs.append("dropped trailing prose")
        return value, repairs
    fixed = _TRAILING_COMMA.sub(r"\1", complete)
    value = _loads(fixed)
    if value is not None:
        return value, [*repairs, "removed trailing commas"]
    if '"' not in fixed and "'" in fixed:
        value = _loads(fixed.replace("'", '"'))
        if value is not None:
            return value, [*repairs, "converted single quotes"]
    value = _repair_truncated(body)
    if value is not None:
        return value, [*repairs, "closed truncated JSON"]
    return None, [*repairs, "unparseable JSON"]
