# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Robust conversion of raw model output into :class:`~thoraxbench.schemas.FindingsReport`."""

from thoraxbench.parsing.findings import parse_findings
from thoraxbench.parsing.json_extract import extract_json

__all__ = ["extract_json", "parse_findings"]
