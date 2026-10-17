# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Installed runtime dependency versions and declared license metadata."""

import re
from importlib import metadata


def runtime_libraries() -> list[dict[str, str]]:
    """Follow installed runtime requirements without reading source or license bodies."""
    pending = ["thoraxbench", "monai", "torch", "torchvision"]
    seen: set[str] = set()
    libraries: list[dict[str, str]] = []
    while pending:
        name = pending.pop()
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            package = metadata.metadata(name)
        except metadata.PackageNotFoundError:
            continue
        if key != "thoraxbench":
            expression = package.get("License-Expression")
            if not expression:
                classifiers = package.get_all("Classifier", [])
                declared = [
                    c.rsplit(" :: ", 1)[-1] for c in classifiers if c.startswith("License ::")
                ]
                expression = next((c for c in declared if c != "OSI Approved"), None)
            libraries.append(
                {
                    "name": package.get("Name", name),
                    "version": package.get("Version", "unknown"),
                    "license": expression or "See distribution license files",
                }
            )
        for requirement in package.get_all("Requires-Dist", []):
            # Optional extras are not part of the default runtime dependency tree.
            if "extra" in requirement.partition(";")[2]:
                continue
            match = re.match(r"[A-Za-z0-9_.-]+", requirement)
            if match:
                pending.append(match.group())
    return sorted(libraries, key=lambda item: item["name"].lower())
