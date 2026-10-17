# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""``thoraxbench sanity`` end to end with mocked Ollama HTTP and synthetic studies only."""

import json
import math
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
import yaml
from typer.testing import CliRunner

from thoraxbench.adapters.base import ModelUnavailableError
from thoraxbench.benchmark import sanity as sn
from thoraxbench.benchmark import sanity_inputs as si
from thoraxbench.cli.main import app
from thoraxbench.config import REPO_ROOT, Settings
from thoraxbench.index import IndexEntry
from thoraxbench.preprocess import HUCues
from thoraxbench.schemas import LesionAnnotation, ReferenceLabels
from thoraxbench.splits import (
    CaseRecord,
    Phase,
    SealedAccessError,
    load_split,
    make_split,
    save_split,
)
from thoraxbench.study import Study

pytestmark = pytest.mark.integration
TAGS = {
    "models": [
        {"name": "medgemma1.5:4b-it-q4_K_M", "digest": "sha256:q4"},
        {"name": "qwen3-vl:4b", "digest": "sha256:qwen"},
    ]
}
SYSTEM = "research only"


def _entry(case_id: str, lesions: list[tuple[float, float]]) -> IndexEntry:
    les = [LesionAnnotation(center_zyx=(z, 1.0, 1.0), diameter_mm=d) for z, d in lesions]
    return IndexEntry(
        dataset="lidc_idri",
        case_id=case_id,
        patient_id=case_id,
        series_uid=f"1.2.{case_id}",
        path=f"raw/lidc_idri/{case_id}",
        stratum="nodule" if les else "negative",
        n_slices=64,
        spacing_mm=(5.0, 2.5, 2.5),
        qc_adequate=True,
        qc_limitations=[],
        reference=ReferenceLabels(
            dataset="lidc_idri",
            patient_id=case_id,
            study_uid=case_id,
            labels={"pulmonary_nodule": bool(les)},
            lesions=les,
        ),
        cues=HUCues(lung_z_extent=(6, 55)),
    )


def _settings(root: Path) -> Settings:
    entries = [_entry(f"P{i}", [(100.0, 10.0), (200.0, 5.0)] if i % 2 else []) for i in range(12)]
    repo = root / "repo"
    repo.mkdir()
    (repo / "configs").symlink_to(REPO_ROOT / "configs", target_is_directory=True)
    records = [
        CaseRecord(dataset="lidc_idri", patient_id=e.case_id, case_id=e.case_id) for e in entries
    ]
    for seed in range(500):
        split = make_split(records, "lidc_idri", salt=f"san-{seed}")
        calibration = set(split.cases(Phase.CALIBRATION))
        positives = [e for e in entries if e.case_id in calibration and e.reference.lesions]
        if split.cases(Phase.SEALED) and len(positives) >= 2 and len(calibration) > len(positives):
            break
    save_split(split, root, repo / "manifests")
    index = root / "index" / "lidc_idri.json"
    index.parent.mkdir(parents=True)
    index.write_text(json.dumps([e.model_dump(mode="json") for e in entries]), encoding="utf-8")
    return Settings(repo_root=repo, data_dir=root, ollama_url="http://127.0.0.1:11434")


def _open_case(entry: IndexEntry, settings: Settings) -> Study:
    phantom = si.load_phantom(si.phantom_spec(1, "right", 12.0), entry.case_id)
    phantom.study.attach_cues(entry.cues)
    return phantom.study


def _write(root: Path, **cfg: Any) -> Path:
    path = root / f"{cfg['id']}.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _lp(token: str, p_yes: float) -> list[dict[str, Any]]:
    alts = [
        {"token": "yes", "logprob": math.log(p_yes)},
        {"token": "no", "logprob": math.log(1 - p_yes)},
    ]
    return [{"token": token, "logprob": -0.1, "top_logprobs": alts}]


def _reply(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    images = sum(len(m.get("images", [])) for m in body["messages"])
    fmt = body.get("format")
    if fmt is None:
        content = f"A synthetic image with {images} image(s)."
        logprobs = None
    elif "image" in fmt["properties"]:
        content = json.dumps({"image": 1})
        logprobs = [
            {"token": "1", "logprob": -0.2, "top_logprobs": [{"token": "1", "logprob": -0.2}]}
        ]
    else:
        answer = "yes" if images else "no"
        content = json.dumps({"nodule": answer, "confidence": 0.9})
        logprobs = _lp(answer, 0.8 if images else 0.3)
    return httpx.Response(
        200,
        json={
            "message": {"role": "assistant", "content": content},
            "done_reason": "stop",
            "prompt_eval_count": 40 + 256 * images,
            "eval_count": 12,
            "logprobs": logprobs,
        },
    )


def _mock(router: respx.Router) -> respx.Route:
    router.get("http://127.0.0.1:11434/api/tags").mock(return_value=httpx.Response(200, json=TAGS))
    return router.post("http://127.0.0.1:11434/api/chat").mock(side_effect=_reply)


YES_NO = {
    "kind": "yes_no",
    "system": SYSTEM,
    "text": "Nodule in any of $n_images?",
}


@respx.mock
def test_image_dependence_synthetic_and_calibration(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    chat = _mock(respx.mock)
    path = _write(
        tmp_path,
        id="T-s1",
        test="image_dependence",
        models=["medgemma1.5-q4", "qwen3-vl-4b-nothink"],
        question=YES_NO,
        windows=["medgemma"],
        layouts=["single", "interleaved"],
        conditions=["real", "gray", "noise", "shuffled", "none"],
        image_mode="multi",
        n_images=3,
        size=64,
        n_boot=0,
        synthetic={"phantoms": [{"diameter_mm": 20}]},
        lidc={"positive_studies": 1, "negative_studies": 1},
    )
    run = sn.run_sanity(sn.load_sanity(path), settings, open_case=_open_case)
    # 3 sources x (4 image conditions x 2 layouts + none x 1) x 2 models
    assert chat.call_count == 3 * 9 * 2
    rows = run.result["metrics"]["rows"]
    assert len(rows) == 3 * 2 * 2
    single = next(r for r in rows if r["layout"] == "single" and r["model"] == "medgemma1.5-q4")
    assert single["real"]["answer"] == "yes"
    assert single["none"]["answer"] == "no"
    assert single["delta_p_yes_none"] == pytest.approx(0.5)
    assert single["real"]["prompt_tokens"] == 40 + 256 * 3
    assert "| real | gray | noise | shuffled | none |" in run.markdown
    qwen = [r for r in run.result["records"] if r["model"] == "qwen3-vl-4b-nothink"]
    assert qwen
    folder = run.folder
    assert folder.parent == settings.data_path("results", "benchmark", "T-s1")
    assert (folder / "result.json").is_file()
    assert (folder / "report.md").is_file()
    manifest = json.loads((folder / "manifest.json").read_text())["payload"]
    assert manifest["config_file"] == sn.load_sanity(path).file_sha256
    assert manifest["runtime_models"]["medgemma1.5-q4"]["digest"] == "sha256:q4"
    case = json.loads(next((folder / "cases").glob("*.json")).read_text())
    blob = json.dumps(case["request"])
    assert '"images"' not in blob
    assert "image_sha256" in blob
    assert case["response"]["body"]["message"]["content"]
    split = load_split(tmp_path, settings.manifests_dir, "lidc_idri", include_sealed=False)
    calibration = set(split.cases(Phase.CALIBRATION))
    lidc_groups = {r["group"] for r in run.result["records"] if r["group"].startswith("P")}
    assert lidc_groups
    assert lidc_groups <= calibration


@respx.mock
def test_obvious_target_binding_and_description(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _mock(respx.mock)
    target = _write(
        tmp_path,
        id="T-s2",
        test="obvious_target",
        models=["medgemma1.5-q4"],
        question=YES_NO,
        windows=["lung", "medgemma"],
        image_mode="multi",
        n_images=4,
        size=64,
        synthetic={"seeds": [0], "sides": ["right", "left"], "diameters_mm": [30]},
    )
    run = sn.run_sanity(sn.load_sanity(target), settings, limit=1)
    assert run.result["n_items"] == 4  # first group only: none + 30 mm, two windows
    rows = run.result["metrics"]["rows"]
    assert {r["condition"] for r in rows} == {"none", "nodule30mm"}
    assert any(r["nodule_level_sampled"] for r in rows if r["condition"] == "nodule30mm")
    assert run.result["metrics"]["overall"][0]["n"] == 2
    binding = _write(
        tmp_path,
        id="T-t2",
        test="position_binding",
        models=["medgemma1.5-q4"],
        question={"kind": "choice", "text": "Which of $n_images shows the disk?"},
        layouts=["single", "interleaved"],
        image_mode="multi",
        n_images=4,
        size=64,
        neutral_captions=True,
        synthetic={"permutations": 8},
    )
    brun = sn.run_sanity(sn.load_sanity(binding), settings)
    brows = brun.result["metrics"]["rows"]
    assert [(r["layout"], r["correct"], r["n"]) for r in brows] == [
        ("interleaved", 2, 8),
        ("single", 2, 8),
    ]
    assert all(c == "attached image" for r in brun.result["records"] for c in r["captions"])
    assert "passes_90pct" in brun.markdown
    describe = _write(
        tmp_path,
        id="T-s3",
        test="description",
        models=["medgemma1.5-q4"],
        question={"kind": "free_text", "text": "Describe IMAGE 1."},
        size=64,
        top_logprobs=0,
        neutral_captions=True,
        synthetic={"phantoms": [{"diameter_mm": 30}]},
        lidc={"positive_studies": 1, "negative_studies": 0, "levels": [0.5]},
    )
    drun = sn.run_sanity(sn.load_sanity(describe), settings, open_case=_open_case)
    assert drun.result["n_requests"] == 2
    assert '"A synthetic image with 1 image(s)."' in drun.markdown


@respx.mock
def test_paired_slab_run_reports_auroc(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    chat = _mock(respx.mock)
    path = _write(
        tmp_path,
        id="T-s4",
        test="paired_slab",
        models=["medgemma1.5-q4"],
        question=YES_NO,
        size=64,
        n_boot=20,
        lidc={"min_diameter_mm": 3.0, "max_lesions": 3, "control_distance_mm": 30.0},
    )
    run = sn.run_sanity(sn.load_sanity(path), settings, open_case=_open_case)
    selection = run.result["selection"]
    assert selection["selected"] == len(run.result["records"]) // 2
    assert selection["calibration_studies"] >= 2
    assert chat.call_count == len(run.result["records"])
    row = run.result["metrics"]["rows"][0]
    assert row["n_positive"] == row["n_negative"] == selection["selected"]
    assert row["yes_rate_negatives"] == 1.0  # the mock always answers yes with an image
    assert row["auroc_p_yes"] == 0.5
    assert "by size" in run.markdown


@respx.mock
def test_run_refusals_and_http_failures(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    respx.get("http://127.0.0.1:11434/api/tags").mock(return_value=httpx.Response(200, json=TAGS))
    base = {
        "test": "obvious_target",
        "question": YES_NO,
        "size": 64,
        "synthetic": {"phantoms": [{"diameter_mm": 20}]},
    }
    missing = sn.load_sanity(_write(tmp_path, id="T-x", models=["minicpm-v"], **base))
    with pytest.raises(ValueError, match="not available"):
        sn.run_sanity(missing, settings)
    heuristic = sn.load_sanity(_write(tmp_path, id="T-h", models=["heuristic-hu"], **base))
    with pytest.raises(ValueError, match="Ollama model"):
        sn.run_sanity(heuristic, settings)
    good = sn.load_sanity(_write(tmp_path, id="T-g", models=["medgemma1.5-q4"], **base))
    with pytest.raises(ValueError, match="positive"):
        sn.run_sanity(good, settings, limit=0)
    remote = Settings(repo_root=settings.repo_root, data_dir=tmp_path, ollama_url="http://10.0.0.1")
    with pytest.raises(ModelUnavailableError, match="loopback"):
        sn.run_sanity(good, remote)
    good.path.write_text(good.path.read_text() + "\n# changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        sn.run_sanity(good, settings)
    statuses = iter(
        [
            httpx.Response(500, text="boom"),
            httpx.Response(200, text="not json"),
            httpx.Response(200, json=[1]),
            httpx.Response(200, json={"error": "model failed"}),
        ]
    )
    respx.post("http://127.0.0.1:11434/api/chat").mock(side_effect=lambda _r: next(statuses))
    fresh = sn.load_sanity(
        _write(
            tmp_path,
            id="T-f",
            models=["medgemma1.5-q4"],
            **base | {"synthetic": {"seeds": [0, 1], "diameters_mm": [20]}},
        )
    )
    run = sn.run_sanity(fresh, settings)
    errors = sorted(str(r["error"]) for r in run.result["records"])
    assert errors == [
        "ollama HTTP 500",
        "ollama provider error: model failed",
        "ollama returned a non-object JSON response",
        "ollama returned non-JSON response",
    ]
    assert all(r["answer"] is None for r in run.result["records"])
    respx.post("http://127.0.0.1:11434/api/chat").mock(side_effect=httpx.ConnectError("down"))
    again = sn.load_sanity(_write(tmp_path, id="T-c", models=["medgemma1.5-q4"], **base))
    down = sn.run_sanity(again, settings, limit=1)
    assert down.result["records"][0]["error"] == "http error: ConnectError"


def test_empty_selection_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(sn, "runtime_identity", lambda *_a: {"digest": "d"})
    path = _write(
        tmp_path,
        id="T-e",
        test="obvious_target",
        models=["medgemma1.5-q4"],
        question=YES_NO,
        lidc={"positive_studies": 0, "negative_studies": 0},
    )
    with pytest.raises(ValueError, match="no sanity inputs"):
        sn.run_sanity(sn.load_sanity(path), settings)


@respx.mock
def test_cli_sanity_dry_run_run_and_refusals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    _mock(respx.mock)
    monkeypatch.setattr("thoraxbench.cli.sanity.get_settings", lambda: settings)
    path = _write(
        tmp_path,
        id="T-cli",
        test="obvious_target",
        models=["medgemma1.5-q4"],
        question=YES_NO,
        size=64,
        synthetic={"seeds": [0, 1], "diameters_mm": [30]},
    )
    dry = CliRunner().invoke(app, ["sanity", str(path), "--dry-run", "--limit", "1"])
    assert dry.exit_code == 0, dry.output
    assert "T-cli: 2 inputs, 2 images, 1 model(s)" in dry.output
    ran = CliRunner().invoke(app, ["sanity", str(path)])
    assert ran.exit_code == 0, ran.output
    assert "Artifacts:" in ran.output
    assert "nodule30mm" in ran.output
    bad = CliRunner().invoke(app, ["sanity", str(tmp_path / "missing.yaml")])
    assert bad.exit_code == 1
    assert "Sanity check failed" in bad.output

    def sealed(*_a: Any, **_k: Any) -> None:
        raise SealedAccessError("sealed case requested")

    monkeypatch.setattr("thoraxbench.benchmark.sanity.run_sanity", sealed)
    refused = CliRunner().invoke(app, ["sanity", str(path)])
    assert refused.exit_code == 2
    assert "Refused" in refused.output
