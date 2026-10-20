# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Self-contained plain-language HTML for a full thorax review (no scripts, no network).

Written for a non-expert reader: the outcome first, then where to look, what was not
flagged, which answers carried no information and the rule-based next steps. Slab images
are downscaled copies of the actual images sent to the model, embedded as data URIs. One
short disclaimer line; no SeriesInstanceUID, patient identifier or path is ever printed.
"""

from __future__ import annotations

import base64
from html import escape
from typing import Any

from thoraxbench.ontology.clinical import load_clinical_kb
from thoraxbench.reports.outcome import SHORT_DISCLAIMER as OUTCOME_DISCLAIMER

# One shared short line for every report; the full text lives in docs/DISCLAIMER.md.
SHORT_DISCLAIMER = OUTCOME_DISCLAIMER["en"]
#: At most this many slab images per look-here entry, and in the whole report.
IMAGES_PER_ENTRY = 3
MAX_IMAGES = 30

HEADLINES = {
    "findings_to_review": "Something to show a radiologist",
    "nothing_flagged_in_checked_area": "Nothing was flagged in the checked area",
    "not_assessable": "This scan could not be assessed",
}
SOURCE_NAMES = {
    "vlm": "image model",
    "detector": "nodule detector",
    "hu": "density (HU) measurement",
}
_CSS = """
body{font:16px/1.5 system-ui,sans-serif;max-width:60rem;margin:0 auto;padding:1rem;color:#1b1f24;
background:#fff}h1{font-size:1.5rem}h2{font-size:1.2rem;margin-top:1.6rem}
.disclaimer{font-size:.9rem;color:#5b2c00;background:#fff4e5;padding:.4rem .6rem;border-radius:4px}
.outcome{border:2px solid #345;border-radius:6px;padding:.8rem 1rem;margin:1rem 0}
.outcome.review{border-color:#b45309}.outcome.none{border-color:#15803d}
.outcome.na{border-color:#6b7280}.outcome strong{font-size:1.25rem;display:block}
ol.look li{margin-bottom:1rem}.muted{color:#555;font-size:.9rem}
.slabs{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.4rem}
figure{margin:0}figure img{width:160px;height:160px;object-fit:contain;background:#000}
figcaption{font-size:.75rem;color:#555;max-width:160px}
table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:.2rem .5rem;text-align:left}
"""


def _slices(lo: int | None, hi: int | None) -> str:
    if lo is None or hi is None:
        return "whole-scan measurement (no single location)"
    return f"slice {lo + 1}" if lo == hi else f"slices {lo + 1} to {hi + 1}"


def _side(side: str) -> str:
    return {"left": ", left side", "right": ", right side", "bilateral": ", both sides"}.get(
        side, ""
    )


def _coverage_text(summary: dict[str, Any]) -> str:
    cov = summary["coverage"]
    total, answered = cov["slabs_total"], cov["slabs_answered"]
    if not total:
        if summary.get("detector", {}).get("status") == "completed":
            return (
                "No image-model slab sweep ran; the nodule detector and the density rules "
                "checked the whole scan volume."
            )
        return "No part of the scan was checked by the image model."
    pct = round(100 * answered / total)
    covered = cov.get("covered_slices") or [0, cov["slices_total"] - 1]
    text = (
        f"The image model checked {answered} of {total} slabs ({pct} %), each about "
        f"{cov['slab_mm']:.0f} mm thick, covering slices {covered[0] + 1} to {covered[1] + 1} "
        f"of {cov['slices_total']} (the lungs plus a margin above and below)."
    )
    if cov["partial"]:
        reason = (
            "it was stopped"
            if cov.get("stopped")
            else "the model runtime kept failing"
            if cov.get("runtime_failed")
            else "not every slab returned an answer"
        )
        text += f" This is a partial result because {reason}."
    return text


def _reliability_text(summary: dict[str, Any], names: dict[str, str]) -> str:
    if summary.get("model_constant"):
        rate = summary.get("overall_positive_rate") or 0.0
        return (
            f"The image model answered “yes” to {round(100 * rate)} % of all questions, so its "
            "answers carry no information about this scan. Only the detector and density "
            "measurements count."
        )
    constant = summary.get("labels_not_informative") or []
    if constant:
        listed = ", ".join(names.get(lbl, lbl) for lbl in constant)
        return (
            f"For {len(constant)} finding type(s) the image model said “yes” on most slabs "
            f"({listed}); those answers carry no information and are not listed as places "
            "to look."
        )
    return ""


def _tools_text(tools: dict[str, list[str]], names: dict[str, str]) -> str:
    """Which labels the detector and density rules answered over the whole volume."""
    parts = [
        f"{', '.join(names.get(lbl, lbl) for lbl in tools.get(key, []))} ({tool})"
        for key, tool in (("detector", "nodule detector"), ("hu", "density rules, weak cues"))
        if tools.get(key)
    ]
    return "; ".join(parts) or "none"


def _baseline_text(summary: dict[str, Any]) -> str:
    detector = summary.get("detector", {})
    status = detector.get("status")
    parts = []
    if status == "completed":
        parts.append(
            f"The nodule detector checked the whole scan ({detector.get('candidates', 0)} "
            "raw candidate(s); only those at or above its score cut-off are listed)."
        )
    else:
        parts.append(f"The nodule detector did not run ({status or 'not configured'}).")
    if summary.get("heuristic", {}).get("status") == "completed":
        parts.append("Density (HU) measurements were taken on the whole scan.")
    return " ".join(parts)


def _figure(png: bytes, caption: str) -> str:
    data = base64.b64encode(png).decode("ascii")
    return (
        f'<figure><img src="data:image/png;base64,{data}" alt="{escape(caption)}">'
        f"<figcaption>{escape(caption)}</figcaption></figure>"
    )


def _entry_slabs(item: dict[str, Any], slabs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lo, hi = item.get("slice_lo"), item.get("slice_hi")
    if lo is None or hi is None:
        return []
    hits = [s for s in slabs if s["slice_hi"] >= lo and s["slice_lo"] <= hi]
    if len(hits) > IMAGES_PER_ENTRY:
        mid = len(hits) // 2
        hits = hits[max(0, mid - 1) : max(0, mid - 1) + IMAGES_PER_ENTRY]
    return hits


def _look_here_html(
    look: list[dict[str, Any]],
    names: dict[str, str],
    slabs: list[dict[str, Any]],
    thumbnails: dict[int, bytes],
) -> list[str]:
    """Ordered "where to look" list with plain explanations and bounded slab images."""
    kb = load_clinical_kb()
    images_left = MAX_IMAGES
    out = ["<h2>Where to look</h2><ol class='look'>"]
    for item in look:
        label = item["label"]
        sources = ", ".join(SOURCE_NAMES.get(s, s) for s in item["sources"])
        facts = [f"Found by: {sources}."]
        if item.get("agreement"):
            facts.append("Several independent tools point to this place.")
        if item.get("weak"):
            facts.append("Weak cue: only the density rules point here; they often over-report.")
        if item.get("vlm_positive_slabs"):
            facts.append(
                f"Image model said yes on {item['vlm_positive_slabs']} of "
                f"{item['vlm_spanned_slabs']} neighbouring slab(s)."
            )
        if item.get("detector_score") is not None:
            facts.append(f"Detector score {item['detector_score']:.2f} (not a probability).")
        if item.get("size_mm") is not None:
            facts.append(f"Measured size about {item['size_mm']:.0f} mm.")
        entry = kb.get(label)
        out.append(
            f"<li><strong>{escape(names.get(label, label))}</strong> — "
            f"{escape(_slices(item.get('slice_lo'), item.get('slice_hi')))}"
            f"{escape(_side(item.get('side', 'unknown')))}<br>{escape(' '.join(facts))}"
        )
        if entry is not None:
            plain = " ".join(entry.plain_language.split())
            out.append(f"<br><span class='muted'>What this means: {escape(plain)}</span>")
        for text in item.get("evidence", [])[:3]:
            out.append(f"<br><span class='muted'>Tool note: “{escape(text)}”</span>")
        figures = []
        for slab in _entry_slabs(item, slabs):
            png = thumbnails.get(slab["position"])
            if png is None or images_left <= 0:
                continue
            images_left -= 1
            figures.append(
                _figure(
                    png,
                    f"Image sent to the model: slices {slab['slice_lo'] + 1} to "
                    f"{slab['slice_hi'] + 1}",
                )
            )
        if figures:
            out.append(f"<div class='slabs'>{''.join(figures)}</div>")
        out.append("</li>")
    out.append("</ol>")
    return out


def render_full_review_html(summary: dict[str, Any], thumbnails: dict[int, bytes]) -> str:
    """Render the summary as one offline HTML page; every model/text value is escaped."""
    names: dict[str, str] = summary.get("label_names", {})
    verdict = summary["verdict"]
    css_class = {
        "findings_to_review": "review",
        "nothing_flagged_in_checked_area": "none",
        "not_assessable": "na",
    }[verdict]
    look = summary.get("look_here", [])
    lead = {
        "findings_to_review": f"{len(look)} place(s) to look at are listed below.",
        "nothing_flagged_in_checked_area": (
            "No checked tool flagged anything. This does not mean the scan is normal: "
            "this research tool can miss findings."
        ),
        "not_assessable": "No usable answer came back, so nothing can be said about this scan.",
    }[verdict]
    out = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Full thorax review — research result</title>",
        f"<style>{_CSS}</style></head><body>",
        "<h1>Full thorax review</h1>",
        f"<p class='disclaimer'>{escape(SHORT_DISCLAIMER)}</p>",
        f"<section class='outcome {css_class}'><strong>{escape(HEADLINES[verdict])}</strong>",
        f"<p>{escape(lead)}</p><p>{escape(_coverage_text(summary))}</p>",
    ]
    reliability = _reliability_text(summary, names)
    if reliability:
        out.append(f"<p>{escape(reliability)}</p>")
    out.append(f"<p class='muted'>{escape(_baseline_text(summary))}</p></section>")
    if look:
        out += _look_here_html(look, names, summary.get("slabs", []), thumbnails)

    def _names(key: str) -> str:
        return ", ".join(names.get(lbl, lbl) for lbl in summary.get(key, [])) or "none"

    swept = bool(summary.get("coverage", {}).get("slabs_total"))
    tools = summary.get("labels_tool_checked")
    if tools is not None:
        out += [
            "<h2>Checked over the whole volume</h2>",
            f"<p>{escape(_tools_text(tools, names))}</p>",
        ]
    if swept:
        out += [
            "<h2>What the image model checked and did not flag</h2>",
            f"<p>{escape(_names('labels_no_flags'))}</p>",
            "<h2>Answers without information</h2>",
            "<p class='muted'>The image model said “yes” on most slabs for these, so a yes "
            "means nothing here.</p>",
            f"<p>{escape(_names('labels_not_informative'))}</p>",
        ]
    unchecked = "labels_not_checked" if "labels_not_checked" in summary else "labels_unanswered"
    out += [
        "<h2>Not checked in this run</h2>",
        f"<p>{escape(_names(unchecked))}</p>",
    ]
    if not swept and summary.get(unchecked):
        out.append(
            "<p class='muted'>These need the image-model slab sweep: run the full review "
            "with an image model to include them.</p>"
        )
    out += [
        "<h2>Next steps (rule-based guideline context, educational)</h2><ul>",
        *[f"<li>{escape(step)}</li>" for step in summary.get("next_steps", [])],
        "</ul>",
    ]
    timing = summary.get("timing", {})
    prov = summary.get("provenance", {})
    rows = [
        ("Image model", summary.get("model_id", "")),
        ("Prompt", summary.get("prompt_id", "")),
        (
            "Time per image",
            f"{timing['seconds_per_image']:.1f} s"
            if timing.get("seconds_per_image") is not None
            else "—",
        ),
        ("Total time", f"{timing.get('total_s', 0.0):.0f} s"),
        ("Slab strategy", f"{prov.get('strategy', {}).get('id', '')}"),
        ("Strategy hash", str(prov.get("strategy_sha256", ""))[:16]),
        ("Software version", str(prov.get("thoraxbench_version", ""))),
    ]
    out.append("<details><summary>Technical details</summary><table>")
    out += [f"<tr><th>{escape(k)}</th><td>{escape(str(v))}</td></tr>" for k, v in rows]
    out.append("</table></details></body></html>")
    return "\n".join(out)
