#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Explicitly fetch the pinned MONAI lung_nodule_ct_detection bundle (weights + terms).

Usage (repository root):

    uv run python scripts/fetch_monai_bundle.py            # print terms, download nothing
    uv run python scripts/fetch_monai_bundle.py --accept-terms
    uv run python scripts/fetch_monai_bundle.py --verify   # check local files only

Downloads only revision-pinned files with a known size and SHA-256 into
``$THORAXBENCH_DATA_DIR/models/monai/lung_nodule_ct_detection/<revision>/`` (git-ignored).
Without ``--accept-terms`` it prints the terms and exits with status 2. Nothing in
ThoraxBench downloads these weights automatically.
"""

from __future__ import annotations

import argparse
import sys

import httpx

from thoraxbench.analysis import DISCLAIMER
from thoraxbench.config import get_settings
from thoraxbench.detectors.bundle import (
    BUNDLE_LICENSE,
    BUNDLE_REPO,
    BUNDLE_REVISION,
    BUNDLE_VERSION,
    BundleIntegrityError,
    bundle_dir,
    fetch_bundle,
    verify_bundle,
)

TERMS = f"""MONAI bundle {BUNDLE_REPO} v{BUNDLE_VERSION} @ {BUNDLE_REVISION}
License of code and weights: {BUNDLE_LICENSE} (bundle LICENSE file).
Training data (bundle docs/data_license.txt): LUNA16 (CC BY 4.0), derived from LIDC-IDRI
(CC BY 3.0). Upstream intended use: "This is an example, not to be used for diagnostic
purposes". ThoraxBench uses it as a research reference baseline only. LUNA16 is drawn from
LIDC-IDRI, so results on LIDC-IDRI carry possible_training_overlap = yes."""


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch the pinned MONAI nodule bundle.")
    parser.add_argument("--accept-terms", action="store_true", help="acknowledge the terms")
    parser.add_argument("--verify", action="store_true", help="only verify local files")
    args = parser.parse_args()
    settings = get_settings()
    print(DISCLAIMER)
    print(TERMS)
    print(f"Target: {bundle_dir(settings)}")
    try:
        if args.verify:
            hashes = verify_bundle(settings)
        elif not args.accept_terms:
            print("Not downloading: pass --accept-terms after reading the terms.")
            return 2
        else:
            hashes = fetch_bundle(settings, acknowledge_license=True, progress=print)
    except (BundleIntegrityError, OSError, httpx.HTTPError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    for path, digest in hashes.items():
        print(f"{digest}  {path}")
    print("bundle verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
