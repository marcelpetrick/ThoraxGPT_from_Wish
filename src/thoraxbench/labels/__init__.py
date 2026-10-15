# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Reference labels per dataset (ground truth for scoring)."""

from thoraxbench.labels.lidc import ReaderNodule, cluster_nodules, lidc_reference, parse_lidc_xml
from thoraxbench.labels.nsclc import find_seg, nsclc_reference, seg_lesion

__all__ = [
    "ReaderNodule",
    "cluster_nodules",
    "find_seg",
    "lidc_reference",
    "nsclc_reference",
    "parse_lidc_xml",
    "seg_lesion",
]
