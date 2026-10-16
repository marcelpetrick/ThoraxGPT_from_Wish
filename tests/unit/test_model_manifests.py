# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Offline snapshot integrity, completeness and explicitly unknown provenance claims."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from thoraxbench.adapters.base import list_model_configs
from thoraxbench.model_manifests import ModelManifest, load_model_manifests

REPOSITORY = Path(__file__).resolve().parents[2]


@pytest.fixture
def snapshot_repo(tmp_path: Path) -> Path:
    for relative in ("configs/models", "manifests/models"):
        shutil.copytree(REPOSITORY / relative, tmp_path / relative)
    (tmp_path / "docs").mkdir()
    shutil.copyfile(REPOSITORY / "docs/results.md", tmp_path / "docs/results.md")
    return tmp_path


def change_snapshot(root: Path, **changes: Any) -> None:
    path = root / "manifests/models/medgemma1.5-q4.json"
    value = json.loads(path.read_text())
    value.update(changes)
    path.write_text(json.dumps(value))


def test_repo_snapshots_are_complete_and_evidence_is_dated() -> None:
    manifests = load_model_manifests(REPOSITORY)
    assert set(manifests) == {
        model.id for model in list_model_configs(REPOSITORY / "configs/models")
    }
    known = {key for key, value in manifests.items() if value.recorded_digest is not None}
    assert known == {"medgemma1.5-q4", "medgemma1.5-q8"}
    for snapshot in manifests.values():
        assert snapshot.current_availability == "unknown"
        assert snapshot.terms_acceptance == "unknown"
        assert snapshot.possible_training_overlap == "unknown"
        assert snapshot.overlap_rationale
        for reference in snapshot.references:
            if not reference.startswith("https://"):
                assert (REPOSITORY / reference).is_file()


def test_generated_schema_matches_the_public_validator() -> None:
    saved = json.loads((REPOSITORY / "manifests/models/schema.json").read_text())
    assert saved == ModelManifest.model_json_schema()


def test_no_configs_cannot_validate_as_an_empty_inventory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No model configurations"):
        load_model_manifests(tmp_path)


def test_missing_snapshot_is_refused(snapshot_repo: Path) -> None:
    (snapshot_repo / "manifests/models/heuristic-hu.json").unlink()
    with pytest.raises(ValueError, match="Missing model manifests: heuristic-hu"):
        load_model_manifests(snapshot_repo)


def test_unconfigured_snapshot_is_refused(snapshot_repo: Path) -> None:
    source = snapshot_repo / "manifests/models/heuristic-hu.json"
    data = json.loads(source.read_text())
    data["model_id"] = "unconfigured"
    (source.parent / "unconfigured.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Unconfigured model manifest"):
        load_model_manifests(snapshot_repo)


def test_filename_identity_is_checked(snapshot_repo: Path) -> None:
    source = snapshot_repo / "manifests/models/heuristic-hu.json"
    source.rename(source.with_name("wrong-name.json"))
    with pytest.raises(ValueError, match="filename/identity mismatch"):
        load_model_manifests(snapshot_repo)


def test_config_byte_drift_requires_a_reviewed_snapshot_update(snapshot_repo: Path) -> None:
    config = snapshot_repo / "configs/models/heuristic-hu.yaml"
    config.write_text(config.read_text() + "\n# reviewed source change\n")
    with pytest.raises(ValueError, match="Stale model configuration snapshot"):
        load_model_manifests(snapshot_repo)


@pytest.mark.parametrize("source", ["configs/models/other.yaml", "../../not-a-model.yaml"])
def test_snapshot_cannot_redirect_the_config_read(snapshot_repo: Path, source: str) -> None:
    change_snapshot(snapshot_repo, source_config=source)
    with pytest.raises(ValueError, match="Stale model configuration snapshot"):
        load_model_manifests(snapshot_repo)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("adapter", "heuristic"),
        ("family", "wrong-family"),
        ("tag", "other:latest"),
        ("service", "ct_clip"),
        ("quantization", "BF16"),
        ("declared_license", "invented license"),
    ],
)
def test_copied_fields_must_match_the_hashed_source(
    snapshot_repo: Path, field: str, value: str
) -> None:
    change_snapshot(snapshot_repo, **{field: value})
    with pytest.raises(ValueError, match="configuration fields differ"):
        load_model_manifests(snapshot_repo)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 2),
        ("snapshot_version", 0),
        ("source_config_sha256", "not-a-sha256"),
        ("recorded_digest", "too-short"),
        ("model_id", "../unsafe"),
        ("current_availability", "available"),
        ("terms_acceptance", "accepted"),
        ("possible_training_overlap", "no"),
        ("overlap_rationale", ""),
        ("references", []),
        ("unreviewed_field", True),
    ],
)
def test_schema_does_not_upgrade_unknown_claims(
    snapshot_repo: Path, field: str, value: object
) -> None:
    change_snapshot(snapshot_repo, **{field: value})
    with pytest.raises(ValidationError):
        load_model_manifests(snapshot_repo)


@pytest.mark.parametrize("changes", [{"recorded_digest": None}, {"digest_evidence": None}])
def test_digest_and_evidence_are_required_together(
    snapshot_repo: Path, changes: dict[str, object]
) -> None:
    change_snapshot(snapshot_repo, **changes)
    with pytest.raises(ValidationError, match="supplied together"):
        load_model_manifests(snapshot_repo)


def test_uncited_digest_does_not_validate(snapshot_repo: Path) -> None:
    change_snapshot(snapshot_repo, recorded_digest="0" * 64)
    with pytest.raises(ValueError, match="digest evidence row missing"):
        load_model_manifests(snapshot_repo)


def test_evidence_must_match_the_cited_section(snapshot_repo: Path) -> None:
    path = snapshot_repo / "manifests/models/medgemma1.5-q4.json"
    data = json.loads(path.read_text())
    data["digest_evidence"]["source_section"] = "No such result section"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="digest evidence section missing"):
        load_model_manifests(snapshot_repo)


def test_evidence_cannot_name_an_arbitrary_file(snapshot_repo: Path) -> None:
    path = snapshot_repo / "manifests/models/medgemma1.5-q4.json"
    data = json.loads(path.read_text())
    data["digest_evidence"]["source_file"] = "data/not-an-evidence-file.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError):
        load_model_manifests(snapshot_repo)
