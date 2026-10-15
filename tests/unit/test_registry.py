# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
from pathlib import Path

import pytest

from thoraxbench.registry import DatasetStatus, PolicyError, load_registry, require_acquirable

ENTRY = """
id: {id}
name: Demo
provider: TCIA
license: CC-BY-3.0
access: public
redistribution: allowed_with_attribution
source_url: https://example.org
raw_format: DICOM
status: {status}
"""


def _write(tmp: Path, ident: str, status: str, name: str | None = None) -> None:
    (tmp / f"{name or ident}.yaml").write_text(ENTRY.format(id=ident, status=status))


def test_load_and_gate(tmp_path: Path) -> None:
    _write(tmp_path, "open_set", "approved")
    _write(tmp_path, "gated_set", "pending_access")
    reg = load_registry(tmp_path)
    assert set(reg) == {"open_set", "gated_set"}
    require_acquirable(reg["open_set"])
    assert reg["open_set"].acquirable
    assert reg["gated_set"].status is DatasetStatus.PENDING_ACCESS
    with pytest.raises(PolicyError, match="pending_access"):
        require_acquirable(reg["gated_set"])


def test_id_must_match_filename(tmp_path: Path) -> None:
    _write(tmp_path, "abc", "approved", name="other")
    with pytest.raises(ValueError, match="does not match"):
        load_registry(tmp_path)
