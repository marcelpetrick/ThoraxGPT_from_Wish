# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Model adapters behind one interface (Vision §17).

* :class:`OllamaModel` — VLMs served by the local Ollama server (MedGemma 1.5, controls)
* :class:`HttpServiceModel` — 3D/PyTorch models as local HTTP services (CT-CLIP, M3D-LaMed,
  CT-CHAT, RadFM, HuatuoGPT-Vision)
* :class:`HeuristicModel` — deterministic HU-rule baseline
"""

from thoraxbench.adapters.base import (
    ModelConfig,
    ModelUnavailableError,
    ThoraxModel,
    ViewBuilderLike,
    default_view_resolver,
    list_model_configs,
    load_model_config,
)
from thoraxbench.adapters.factory import load_model
from thoraxbench.adapters.heuristic import HeuristicModel, HUCuesLike, heuristic_findings
from thoraxbench.adapters.http_service import HttpServiceModel
from thoraxbench.adapters.ollama import OllamaModel

__all__ = [
    "HUCuesLike",
    "HeuristicModel",
    "HttpServiceModel",
    "ModelConfig",
    "ModelUnavailableError",
    "OllamaModel",
    "ThoraxModel",
    "ViewBuilderLike",
    "default_view_resolver",
    "heuristic_findings",
    "list_model_configs",
    "load_model",
    "load_model_config",
]
