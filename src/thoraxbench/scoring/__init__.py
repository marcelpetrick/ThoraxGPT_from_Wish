# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Benchmark scoring for Vision §13 tasks A-G."""

from thoraxbench.scoring.calibration_metrics import task_b
from thoraxbench.scoring.classification import bootstrap_ci, task_a
from thoraxbench.scoring.lesions import task_c
from thoraxbench.scoring.overlap import (
    combine_overlaps,
    normalize_family,
    possible_training_overlap,
)
from thoraxbench.scoring.records import CaseRecord, PredictedLesion
from thoraxbench.scoring.report import bleu1, factuality, rouge_l, task_e
from thoraxbench.scoring.safety import task_g
from thoraxbench.scoring.segmentation import box_iou, center_distance, dice, hausdorff, iou
from thoraxbench.scoring.vqa import VqaItem, score_vqa

__all__ = [
    "CaseRecord",
    "PredictedLesion",
    "VqaItem",
    "bleu1",
    "bootstrap_ci",
    "box_iou",
    "center_distance",
    "combine_overlaps",
    "dice",
    "factuality",
    "hausdorff",
    "iou",
    "normalize_family",
    "possible_training_overlap",
    "rouge_l",
    "score_vqa",
    "task_a",
    "task_b",
    "task_c",
    "task_e",
    "task_g",
]
