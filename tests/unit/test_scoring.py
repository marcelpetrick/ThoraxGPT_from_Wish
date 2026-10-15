# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
import numpy as np
import pytest

from thoraxbench.schemas import Finding, FindingsReport, LesionAnnotation
from thoraxbench.scoring import (
    CaseRecord,
    PredictedLesion,
    VqaItem,
    bleu1,
    box_iou,
    center_distance,
    dice,
    factuality,
    hausdorff,
    iou,
    possible_training_overlap,
    rouge_l,
    score_vqa,
    task_a,
    task_b,
    task_c,
    task_e,
    task_g,
)
from thoraxbench.scoring.calibration_metrics import ece
from thoraxbench.scoring.classification import ConfusionCounts, bootstrap_ci, score_label
from thoraxbench.scoring.segmentation import hit_rate
from thoraxbench.scoring.vqa import normalise_answer


def _cases() -> list[CaseRecord]:
    rng = np.random.default_rng(0)
    out = []
    for i in range(40):
        truth = i % 2 == 0
        p = float(np.clip((0.7 if truth else 0.3) + rng.normal(0, 0.15), 0, 1))
        out.append(
            CaseRecord(
                case_id=f"c{i}",
                patient_id=f"p{i // 2}",
                y_true={"nodule": truth, "effusion": False, "unk": None},
                y_score={"nodule": p, "effusion": 0.2, "unk": 0.4},
            )
        )
    return out


def test_task_a_metrics_and_ci() -> None:
    res = task_a(_cases(), ["nodule", "effusion", "unk"], n_boot=50)
    nod = res.per_label["nodule"]
    assert nod.auroc is not None
    assert nod.auroc > 0.8
    assert nod.ci["auroc"] is not None
    assert nod.sens_at_spec["0.90"] is not None
    eff = res.per_label["effusion"]
    assert eff.auroc is None
    assert "only one reference class" in eff.notes[0]
    assert res.per_label["unk"].n == 0
    assert res.macro_auroc == nod.auroc
    assert res.micro_f1 is not None
    d = res.to_dict()
    assert d["per_label"]["nodule"]["prevalence"] == 0.5
    assert score_label(_cases(), "nodule", n_boot=0).ci == {}


def test_confusion_and_bootstrap_edge_cases() -> None:
    c = ConfusionCounts()
    assert c.metrics()["sensitivity"] is None
    y = np.asarray([1, 1], dtype=np.int_)
    s = np.asarray([0.9, 0.8])
    assert bootstrap_ci(y, s, ["a", "b"], lambda _y, _s: None, n_boot=20) is None
    assert bootstrap_ci(y[:0], s[:0], [], lambda _y, _s: 1.0) is None


def test_task_b_calibration() -> None:
    res = task_b(_cases(), ["nodule", "unk"])
    assert res["nodule"].brier is not None
    assert 0 <= res["nodule"].brier < 0.25
    assert res["nodule"].curve
    assert res["unk"].n == 0
    assert res["nodule"].to_dict()["label"] == "nodule"
    y = np.asarray([1, 0], dtype=np.int_)
    assert ece(y, np.asarray([1.0, 0.0])) == 0.0


def test_task_c_lesions() -> None:
    ref = [
        LesionAnnotation(center_zyx=(10, 10, 10), diameter_mm=5, readers=4),
        LesionAnnotation(center_zyx=(50, 50, 50), diameter_mm=20, readers=1),
    ]
    cases = [
        CaseRecord(
            "a",
            "p",
            reference_lesions=ref,
            predicted_lesions=[
                PredictedLesion((11, 10, 10), 5, 0.9),
                PredictedLesion((90, 90, 90), None, 0.5),
            ],
        ),
        CaseRecord("b", "q"),
    ]
    res = task_c(cases)
    assert res.sensitivity == 0.5
    assert res.fp_per_scan == 0.5
    assert res.froc_at["1.0"] == 0.5
    assert res.froc_average is not None
    assert res.by_size["<6"]["sensitivity"] == 1.0
    assert res.by_readers[">=4"]["n"] == 1
    assert res.to_dict()["n_lesions"] == 2
    assert task_c([]).sensitivity is None


def test_task_d_segmentation() -> None:
    a = np.zeros((4, 4, 4), dtype=bool)
    b = np.zeros((4, 4, 4), dtype=bool)
    a[1:3, 1:3, 1:3] = True
    b[1:3, 1:3, 2:4] = True
    assert dice(a, b) == pytest.approx(0.5)
    assert iou(a, b) == pytest.approx(1 / 3)
    assert hausdorff(a, b) == pytest.approx(1.0)
    assert center_distance(a, b) == pytest.approx(1.0)
    empty = np.zeros_like(a)
    assert dice(empty, empty) is None
    assert hausdorff(a, empty) is None
    assert center_distance(a, empty) is None
    assert box_iou((0, 0, 0, 2, 2, 2), (1, 1, 1, 3, 3, 3)) == pytest.approx(1 / 15)
    assert box_iou((0, 0, 0, 1, 1, 1), (2, 2, 2, 3, 3, 3)) == 0.0
    assert hit_rate([1.0, None, 9.0], 5.0) == pytest.approx(1 / 3)
    assert hit_rate([], 5.0) is None


def test_task_e_factuality() -> None:
    rep = FindingsReport(
        findings=[
            Finding(label="nodule", present=True),
            Finding(label="effusion", present=True),
            Finding(label="maybe", present=None),
        ],
        negative_findings=["pneumothorax"],
    )
    ref = {
        "nodule": True,
        "effusion": False,
        "pneumothorax": True,
        "emphysema": True,
        "fracture": False,
        "x": None,
    }
    c = factuality(rep, ref)
    assert (c.agreements, c.contradictions, c.omissions, c.hallucinated_positives) == (2, 2, 1, 1)
    agg = task_e([CaseRecord("a", "p", y_true=ref, report=rep), CaseRecord("b", "p")])
    assert agg.to_dict()["label_agreement"] == pytest.approx(2 / 5)
    assert bleu1("small nodule right", "small nodule in the right lung") > 0
    assert bleu1("", "x") == 0.0
    assert bleu1("a b c d e", "a b") == pytest.approx(0.4)
    assert rouge_l("nodule right lung", "right lung nodule") > 0
    assert rouge_l("", "x") == 0.0
    assert rouge_l("abc", "xyz") == 0.0


def test_task_f_vqa() -> None:
    items = [
        VqaItem("effusion?", "yes_no", "yes", "Yes, there is"),
        VqaItem("side?", "laterality", "right", "Right lower lobe"),
        VqaItem("dominant?", "label", "pulmonary_nodule", "GGO"),
        VqaItem("free", "text", "Nodule", "nodule"),
        VqaItem("x", "yes_no", "no", "unclear"),
    ]
    res = score_vqa(items)
    assert res["n"] == 5
    assert res["ontology_aware"] == pytest.approx(3 / 5)
    assert res["unparsable"] == 1
    assert normalise_answer("No.", "yes_no") == "no"
    assert normalise_answer("upper", "laterality") is None
    assert score_vqa([])["exact_match"] is None


def test_task_g_safety() -> None:
    reassuring = FindingsReport(findings=[Finding(label="nodule", present=False, confidence=0.95)])
    fabricating = FindingsReport(
        findings=[Finding(label="effusion", present=True, size_mm=12.0)], urgent_flags=["x"]
    )
    abstaining = FindingsReport(abstain=True)
    cases = [
        CaseRecord("a", "p", {"nodule": True}, {"nodule": 0.05}, report=reassuring),
        CaseRecord("b", "p", {"effusion": False}, {"effusion": 0.95}, report=fabricating),
        CaseRecord("c", "p", {"nodule": True}, {"nodule": 0.95}, report=abstaining),
        CaseRecord("d", "p", {"nodule": None}, {}),
    ]
    g = task_g(cases)
    assert g["abstention_rate"] == pytest.approx(1 / 3)
    assert g["fabricated_measurement_rate"] == 1.0
    assert g["false_reassurance_rate"] == 1.0
    assert g["false_urgent_flag_rate"] == 1.0
    assert g["high_confidence_error_rate"] == pytest.approx(2 / 3)
    assert g["risk_coverage"][-1]["coverage"] == 1.0
    assert task_g([])["risk_coverage"] == []


def test_training_overlap() -> None:
    assert possible_training_overlap("ct_clip", "ct_rate") == "yes"
    assert possible_training_overlap("ct_clip", "lidc_idri") == "no"
    assert (
        possible_training_overlap("ct_clip", "radgenome", parents={"radgenome": ["ct_rate"]})
        == "yes"
    )
    assert possible_training_overlap("medgemma", "ct_rate") == "unknown"
