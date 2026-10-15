# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""The committed registry must load and gate exactly as documented in docs/datasets.md."""

import pytest

from thoraxbench.config import get_settings
from thoraxbench.registry import PolicyError, load_registry, require_acquirable


def test_repo_registry_gates() -> None:
    reg = load_registry(get_settings().configs_dir / "datasets")
    assert reg["lidc_idri"].acquirable
    assert reg["lidc_idri"].license == "CC-BY-3.0"
    assert reg["nsclc_radiogenomics"].role == "external_test"
    assert reg["radgenome_chestct"].parent_datasets == ["ct_rate"]
    for blocked in ("ct_rate", "radgenome_chestct", "deeplesion", "mosmeddata_covid19_1110"):
        with pytest.raises(PolicyError):
            require_acquirable(reg[blocked])
    assert all(e.citation or not e.citation_required for e in reg.values() if e.acquirable)
