# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Post-hoc calibration fitted on development data only (Vision §14, §20).

Every ``fit`` accepts a ``phase`` argument and refuses ``"sealed"``: thresholds and
calibration maps must never be fitted on the sealed validation split.
"""

from thoraxbench.calibration.calibrators import (
    AbstentionRule,
    Calibrator,
    IsotonicCalibrator,
    PlattCalibrator,
    TemperatureScaler,
    calibrator_from_dict,
    check_phase,
    fit_thresholds,
)

__all__ = [
    "AbstentionRule",
    "Calibrator",
    "IsotonicCalibrator",
    "PlattCalibrator",
    "TemperatureScaler",
    "calibrator_from_dict",
    "check_phase",
    "fit_thresholds",
]
