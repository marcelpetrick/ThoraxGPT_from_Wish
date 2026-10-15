/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it> */
"use strict";
(() => {
  const words = {
    en: {
      skipTip:"Move keyboard focus directly to the research workspace.",noticeTip:"Status of the most recent local request. Errors show a reason so you can correct the input or retry.",brandLocal:"LOCAL RESEARCH",skip:"Skip to workspace",workspace:"Workspace",navigation:"Main navigation",analysis:"Analysis",about:"About",local:"Runs on your workstation",privacy:"Local inference. No telemetry.",light:"Light",dark:"Dark",languageAria:"Switch interface to German",themeAria:"Switch to dark theme",research:"Research use only",disclaimer:"Self-made experimental research tool. Not medical advice from a qualified healthcare professional, a diagnosis, or a medical device. Findings may be incorrect, incomplete or misleading; do not use for diagnosis or treatment decisions.",eyebrow:"LOCAL RESEARCH WORKBENCH",heading:"A study. A model. Inspectable results.",intro:"Explore a synthetic demo or a development study with the same engine as the CLI.",holdout:"Sealed holdout protected",inputHeading:"Choose a study",inputIntro:"Only synthetic and permitted development studies appear here.",study:"Study",loading:"Loading…",noStudies:"No studies yet — create a demo",createDemo:"Create synthetic demo",modelHeading:"Select a local model",model:"Model",modelNote:"Availability is not benchmark performance.",imageCount:"Images for vision models",baselineNote:"The heuristic baseline uses HU measurements; it does not send images to a vision model.",run:"Run analysis locally",runtimeNote:"Vision models can take several minutes. Failed or inadequate inputs abstain.",viewerHeading:"Study viewer",viewerNote:"Axial DICOM slice · research inspection",viewerEmpty:"Your study appears here",viewerEmptyNote:"Create a synthetic demo to try the complete pipeline.",sliceAlt:"Axial CT research slice",window:"Window",lung:"Lung",soft:"Mediastinum",bone:"Bone",abdomen:"Abdomen",slice:"Slice",resultsHeading:"Inspect the outcome",downloadHtml:"Download HTML",htmlNote:"The standalone HTML report combines input images, findings and reported evidence references. References are not verified localization.",htmlTip:"Download a self-contained HTML research report with embedded images. Open it in a browser without the server. Images are research inputs, not validated finding overlays.",evidenceTip:"Evidence references are the model’s reported association with input views or slices. They do not establish a verified location or segmentation.",downloadJson:"Download JSON",downloadReport:"Download report",resultsEmpty:"Ready when you are.",resultsEmptyNote:"Run a study to inspect findings, timing, provenance and the English research report.",engineTime:"Engine stages",status:"Status",findingCount:"Findings returned",scoresNotice:"Higher presence scores mean more support that a finding is present. Scores are uncalibrated; accuracy remains unmeasured.",finding:"Finding",presence:"Presence",score:"Presence score",side:"Side",size:"Size",reportHeading:"English research report",reportLanguage:"The reproducible research report stays in English. The interface language does not change model prompts or results.",aboutEyebrow:"TRANSPARENT BY DESIGN",aboutHeading:"About ThoraxBench Local",aboutIntro:"A local laboratory for reproducible thoracic CT model research.",project:"The project",projectText:"Inspect the path from DICOM input to model output, with explicit quality checks and provenance. This MVP supports individual study exploration; comparative benchmarking is still pending.",author:"Author",version:"Version",license:"Project license",aiNote:"Self-made with AI assistance and to the best of our knowledge. Errors and omissions remain possible; research outputs require independent evaluation.",libraries:"Libraries & licenses",librariesNote:"Installed runtime dependencies and their declared licenses.",library:"Library",licenseShort:"License",footer:"Research use only · Local inference · No telemetry",available:"available locally",unavailable:"unavailable",synthetic:"Synthetic",calibration:"Calibration",internal_test:"Internal test",development:"Development",adequate:"QC adequate",inadequate:"QC limited",slices:"slices",running:"Running locally…",creating:"Creating synthetic demo…",demoReady:"Synthetic demo ready. Select a model and run your first analysis.",complete:"Analysis completed. Inspect the uncalibrated findings and research report below.",abstained:"Abstained",completed:"Completed",abstainNotice:"The engine abstained. No reliable finding summary is available; inspect the report for the reason.",failed:"Request failed",invalidImages:"Choose an image count between 1 and 16.",sliceFailed:"The slice could not be displayed. Check the study quality or choose another study.",present:"Present",absent:"Not detected",uncertain:"Uncertain",left:"Left",right:"Right",bilateral:"Bilateral",midline:"Midline",unknown:"Unknown",noFindings:"No findings returned. Inspect the report and abstention status.",modelReady:"Locally available · benchmark accuracy not yet measured",modelNotReady:"Unavailable · choose another local model",brandTip:"Open the local research workspace. All inference stays on this workstation.",analysisTip:"Inspect a development or synthetic study and run a local model.",aboutTip:"View the author, software version, and dependency licenses.",localTip:"No cloud inference or telemetry. The app uses local services only.",languageTip:"Switch the interface between English and German. Reports and model prompts stay in English.",themeTip:"Switch between light and dark appearance. Your choice is saved in this browser.",holdoutTip:"Sealed validation studies are hidden and cannot be opened by this development interface.",studyTip:"Choose a synthetic demo or a case permitted by the frozen development split.",phaseTip:"The study's development subset. Synthetic demos are separate from the patient split.",qcTip:"Quality control indicates whether the input supports this research pipeline. It does not establish clinical suitability.",slicesTip:"Number of axial slices in the selected study.",demoTip:"Generate a synthetic 64-slice DICOM phantom with a nodule and effusion. No patient data is used.",modelTip:"Choose the deterministic HU baseline or a locally hosted model. Available does not mean benchmarked.",availabilityTip:"Local availability checks whether the model can run. No accuracy ranking is implied.",imagesTip:"For vision models: request 1–16 sampled slices. The HU heuristic does not use rendered images.",runTip:"Run the selected study and local model. Changing controls is disabled until this request completes.",sliceTip:"Browse axial slices. Use Left and Right arrow keys on the slider; displayed numbering starts at 1.",windowTip:"Change the display window only. This does not change analysis settings or predictions.",jsonTip:"Download the full research result, including findings, QC, timings, hashes and provenance.",reportTip:"Download the English Markdown research report. It is not a patient care plan.",resultModelTip:"The model that produced the currently displayed result.",timingTip:"Measured engine stages only. Excludes DICOM loading, report rendering and provenance collection.",resultStatusTip:"Completed means the engine returned output. Abstention means the engine declined to provide findings.",findingCountTip:"Count of returned findings, including uncertain or negative entries. This is not an accuracy metric.",scoresTip:"Uncalibrated heuristic or model outputs. Do not interpret them as validated probabilities.",findingTip:"Canonical ontology label returned by the engine. Finding names are research artifact identifiers.",presenceTip:"The model's reported presence, absence or uncertainty.",scoreTip:"Higher values mean more support for the finding being present. Uncalibrated, not an accuracy measure. Missing confidence or uncertain presence is shown without a score.",sideTip:"Reported laterality, not an independently verified localization.",sizeTip:"Reported candidate diameter in millimeters, when available.",reportBodyTip:"Expand the complete English Markdown research report, displayed as safe plain text.",authorTip:"Project author and maintainer.",versionTip:"Installed software version for this local application or dependency.",licenseTip:"Declared software license. See the source distribution for full terms and attribution.",libraryTip:"Runtime library used by the local Python application."
    },
    de: {
      skipTip:"Den Tastaturfokus direkt in den Forschungsarbeitsbereich verschieben.",noticeTip:"Status der letzten lokalen Anfrage. Bei Fehlern wird ein Grund angezeigt, damit Sie die Eingabe korrigieren oder erneut versuchen können.",brandLocal:"LOKALE FORSCHUNG",skip:"Zum Arbeitsbereich",workspace:"Arbeitsbereich",navigation:"Hauptnavigation",analysis:"Analyse",about:"Über",local:"Läuft auf Ihrem Rechner",privacy:"Lokale Inferenz. Keine Telemetrie.",light:"Hell",dark:"Dunkel",languageAria:"Oberfläche auf Englisch umstellen",themeAria:"Zum dunklen Design wechseln",research:"Nur für Forschungszwecke",disclaimer:"Selbst entwickeltes experimentelles Forschungswerkzeug. Keine medizinische Beratung durch qualifiziertes medizinisches Fachpersonal, keine Diagnose und kein Medizinprodukt. Ergebnisse können falsch, unvollständig oder irreführend sein; nicht für Diagnose- oder Behandlungsentscheidungen verwenden.",eyebrow:"LOKALER FORSCHUNGSARBEITSPLATZ",heading:"Eine Studie. Ein Modell. Prüfbare Ergebnisse.",intro:"Untersuchen Sie eine synthetische Demo oder Entwicklungsstudie mit derselben Engine wie in der CLI.",holdout:"Versiegelte Validierung geschützt",inputHeading:"Studie auswählen",inputIntro:"Hier erscheinen nur synthetische und zugelassene Entwicklungsstudien.",study:"Studie",loading:"Wird geladen…",noStudies:"Noch keine Studien — Demo erstellen",createDemo:"Synthetische Demo erstellen",modelHeading:"Lokales Modell auswählen",model:"Modell",modelNote:"Verfügbarkeit ist kein Benchmark-Ergebnis.",imageCount:"Bilder für Vision-Modelle",baselineNote:"Die HU-Heuristik nutzt Messwerte und sendet keine Bilder an ein Vision-Modell.",run:"Analyse lokal starten",runtimeNote:"Vision-Modelle benötigen gegebenenfalls mehrere Minuten. Bei Fehlern oder ungeeigneten Eingaben enthält sich die Engine.",viewerHeading:"Studienansicht",viewerNote:"Axiale DICOM-Schicht · Forschungsansicht",viewerEmpty:"Hier erscheint Ihre Studie",viewerEmptyNote:"Erstellen Sie eine synthetische Demo, um die gesamte Verarbeitung zu testen.",sliceAlt:"Axiale CT-Schicht für Forschungszwecke",window:"Fenster",lung:"Lunge",soft:"Mediastinum",bone:"Knochen",abdomen:"Abdomen",slice:"Schicht",resultsHeading:"Ergebnis prüfen",downloadHtml:"HTML herunterladen",htmlNote:"Der eigenständige HTML-Bericht verbindet Eingabebilder, Befunde und angegebene Evidenzverweise. Die Verweise sind keine verifizierte Lokalisation.",htmlTip:"Eigenständigen HTML-Forschungsbericht mit eingebetteten Bildern herunterladen und ohne Server im Browser öffnen. Die Bilder sind Forschungseingaben, keine validierten Befund-Overlays.",evidenceTip:"Evidenzverweise sind die vom Modell angegebenen Zuordnungen zu Eingabeansichten oder Schichten. Sie belegen keine verifizierte Position oder Segmentierung.",downloadJson:"JSON herunterladen",downloadReport:"Bericht herunterladen",resultsEmpty:"Bereit für die erste Analyse.",resultsEmptyNote:"Starten Sie eine Studie, um Befunde, Laufzeit, Provenienz und den englischen Forschungsbericht zu prüfen.",engineTime:"Engine-Schritte",status:"Status",findingCount:"Zurückgegebene Befunde",scoresNotice:"Höhere Werte sprechen stärker für das Vorhandensein eines Befunds. Die Werte sind unkalibriert; die Genauigkeit ist noch nicht gemessen.",finding:"Befund",presence:"Vorhandensein",score:"Wert für Vorhandensein",side:"Seite",size:"Größe",reportHeading:"Englischer Forschungsbericht",reportLanguage:"Der reproduzierbare Forschungsbericht bleibt auf Englisch. Die Sprache der Oberfläche ändert weder Modell-Prompts noch Ergebnisse.",aboutEyebrow:"TRANSPARENZ ALS PRINZIP",aboutHeading:"Über ThoraxBench Local",aboutIntro:"Ein lokales Labor für reproduzierbare Forschung an Thorax-CT-Modellen.",project:"Das Projekt",projectText:"Prüfen Sie den Weg von DICOM-Daten zur Modellausgabe einschließlich Qualitätskontrolle und Provenienz. Dieses MVP ermöglicht die Untersuchung einzelner Studien; vergleichende Benchmarks stehen noch aus.",author:"Autor",version:"Version",license:"Projektlizenz",aiNote:"Selbst entwickelt mit KI-Unterstützung und nach bestem Wissen. Fehler und Auslassungen sind möglich; Forschungsergebnisse erfordern eine unabhängige Bewertung.",libraries:"Bibliotheken & Lizenzen",librariesNote:"Installierte Laufzeitabhängigkeiten mit ihren deklarierten Lizenzen.",library:"Bibliothek",licenseShort:"Lizenz",footer:"Nur für Forschungszwecke · Lokale Inferenz · Keine Telemetrie",available:"lokal verfügbar",unavailable:"nicht verfügbar",synthetic:"Synthetisch",calibration:"Kalibrierung",internal_test:"Interner Test",development:"Entwicklung",adequate:"QC ausreichend",inadequate:"QC eingeschränkt",slices:"Schichten",running:"Lokale Verarbeitung läuft…",creating:"Synthetische Demo wird erstellt…",demoReady:"Synthetische Demo bereit. Wählen Sie ein Modell und starten Sie Ihre erste Analyse.",complete:"Analyse abgeschlossen. Prüfen Sie unten die unkalibrierten Befunde und den Forschungsbericht.",abstained:"Enthaltung",completed:"Abgeschlossen",abstainNotice:"Die Engine hat sich enthalten. Es liegt keine belastbare Befundzusammenfassung vor; der Bericht nennt den Grund.",failed:"Anfrage fehlgeschlagen",invalidImages:"Wählen Sie eine Bildanzahl zwischen 1 und 16.",sliceFailed:"Die Schicht konnte nicht angezeigt werden. Prüfen Sie die Studienqualität oder wählen Sie eine andere Studie.",present:"Vorhanden",absent:"Nicht erkannt",uncertain:"Unklar",left:"Links",right:"Rechts",bilateral:"Beidseits",midline:"Mittig",unknown:"Unbekannt",noFindings:"Keine Befunde zurückgegeben. Prüfen Sie Bericht und Enthaltungsstatus.",modelReady:"Lokal verfügbar · Benchmark-Genauigkeit noch nicht gemessen",modelNotReady:"Nicht verfügbar · anderes lokales Modell wählen",brandTip:"Lokalen Forschungsarbeitsbereich öffnen. Jede Inferenz bleibt auf diesem Rechner.",analysisTip:"Entwicklungsstudie oder synthetische Studie untersuchen und ein lokales Modell starten.",aboutTip:"Autor, Softwareversion und Lizenzen der Abhängigkeiten anzeigen.",localTip:"Keine Cloud-Inferenz oder Telemetrie. Die Anwendung nutzt ausschließlich lokale Dienste.",languageTip:"Zwischen deutscher und englischer Oberfläche wechseln. Berichte und Modell-Prompts bleiben auf Englisch.",themeTip:"Zwischen hellem und dunklem Design wechseln. Die Auswahl wird in diesem Browser gespeichert.",holdoutTip:"Versiegelte Validierungsstudien sind verborgen und in dieser Entwicklungsoberfläche nicht zugänglich.",studyTip:"Synthetische Demo oder einen Fall aus der eingefrorenen Entwicklungsaufteilung auswählen.",phaseTip:"Entwicklungs-Teilmenge dieser Studie. Synthetische Demos gehören nicht zur Patientenaufteilung.",qcTip:"Die Qualitätskontrolle bewertet die Eignung für diese Forschungspipeline, nicht die klinische Eignung.",slicesTip:"Anzahl axialer Schichten der ausgewählten Studie.",demoTip:"Synthetisches DICOM-Phantom mit 64 Schichten, Rundherd und Erguss erzeugen. Es werden keine Patientendaten verwendet.",modelTip:"Deterministische HU-Heuristik oder lokal gehostetes Modell auswählen. Verfügbar bedeutet nicht benchmark-validiert.",availabilityTip:"Die lokale Verfügbarkeit prüft, ob das Modell lauffähig ist. Sie stellt keine Genauigkeitsbewertung dar.",imagesTip:"Für Vision-Modelle: 1–16 ausgewählte Schichten anfordern. Die HU-Heuristik nutzt keine gerenderten Bilder.",runTip:"Ausgewählte Studie mit dem lokalen Modell analysieren. Die Einstellungen bleiben während der Anfrage gesperrt.",sliceTip:"Axiale Schichten durchblättern. Nutzen Sie am Regler die Pfeiltasten links/rechts. Die Anzeige zählt ab 1.",windowTip:"Nur das Darstellungsfenster ändern. Analyseparameter und Vorhersagen bleiben unverändert.",jsonTip:"Vollständiges Forschungsergebnis mit Befunden, QC, Laufzeiten, Hashes und Provenienz herunterladen.",reportTip:"Englischen Markdown-Forschungsbericht herunterladen. Er ist kein Behandlungsplan.",resultModelTip:"Modell, das das aktuell angezeigte Ergebnis erzeugt hat.",timingTip:"Nur gemessene Engine-Schritte. DICOM-Laden, Berichtserstellung und Provenienz-Erfassung sind nicht enthalten.",resultStatusTip:"Abgeschlossen bedeutet, dass die Engine eine Ausgabe geliefert hat. Bei Enthaltung werden keine Befunde zugesichert.",findingCountTip:"Anzahl zurückgegebener Befunde einschließlich unklarer oder negativer Einträge. Keine Genauigkeitsmetrik.",scoresTip:"Unkalibrierte Heuristik- oder Modellausgaben. Nicht als validierte Wahrscheinlichkeiten interpretieren.",findingTip:"Kanonisches Ontologie-Label der Engine. Befundnamen sind Kennungen des Forschungsartefakts.",presenceTip:"Vom Modell angegebene Anwesenheit, Abwesenheit oder Unsicherheit.",scoreTip:"Höhere Werte sprechen stärker für das Vorhandensein des Befunds. Unkalibriert und kein Maß für Genauigkeit. Bei fehlender Konfidenz oder unklarem Vorhandensein wird kein Wert angezeigt.",sideTip:"Angegebene Seite, keine unabhängig überprüfte Lokalisation.",sizeTip:"Angegebener Kandidatendurchmesser in Millimetern, falls vorhanden.",reportBodyTip:"Vollständigen englischen Markdown-Forschungsbericht als sicheren Klartext öffnen.",authorTip:"Autor und Maintainer des Projekts.",versionTip:"Installierte Softwareversion dieser lokalen Anwendung oder Abhängigkeit.",licenseTip:"Deklarierte Softwarelizenz. Vollständige Bedingungen und Namensnennungen stehen in der Quelldistribution.",libraryTip:"Laufzeitbibliothek der lokalen Python-Anwendung."
    }
  };
  const $ = (id) => document.getElementById(id);
  const readPreference = (key, allowed, fallback) => { try { const value = localStorage.getItem(key); return allowed.includes(value) ? value : fallback; } catch { return fallback; } };
  let language = readPreference("thoraxbench.language", ["en", "de"], "en");
  let theme = readPreference("thoraxbench.theme", ["light", "dark"], "light");
  let studies = [], models = [], busy = false, output = null, noticeKey = null;
  const t = (key) => words[language][key] || words.en[key] || key;
  const save = (key, value) => { try { localStorage.setItem(key, value); } catch { /* Preferences remain usable when storage is blocked. */ } };
  const setText = (id, value) => { $(id).textContent = value; };
  const tooltip = $("tooltip");
  let tooltipTarget = null;
  let tooltipDismissed = false;
  let tooltipHideTimer = null;
  function initializeTooltips() {
    document.querySelectorAll("[data-tip]").forEach((element) => {
      element.setAttribute("aria-describedby", "tooltip");
    });
  }
  function showTooltip(element) {
    if (!element || tooltipDismissed) return;
    clearTimeout(tooltipHideTimer);
    tooltipTarget = element;
    tooltip.textContent = t(element.dataset.tip);
    tooltip.hidden = false;
    const rect = element.getBoundingClientRect();
    const box = tooltip.getBoundingClientRect();
    const left = Math.max(12, Math.min(rect.left, window.innerWidth - box.width - 12));
    const top = rect.bottom + box.height + 12 < window.innerHeight ? rect.bottom + 8 : Math.max(12, rect.top - box.height - 8);
    tooltip.style.left = `${left}px`; tooltip.style.top = `${top}px`;
  }
  function hideTooltip() { clearTimeout(tooltipHideTimer); tooltip.hidden = true; tooltipTarget = null; }
  function scheduleTooltipHide() {
    clearTimeout(tooltipHideTimer);
    tooltipHideTimer = setTimeout(() => {
      if (tooltip.matches(":hover") || tooltipTarget?.contains(document.activeElement)) return;
      hideTooltip();
    }, 180);
  }
  tooltip.addEventListener("mouseenter", () => clearTimeout(tooltipHideTimer));
  tooltip.addEventListener("mouseleave", scheduleTooltipHide);
  document.addEventListener("mouseover", (event) => { const target = event.target.closest("[data-tip]"); if (target) showTooltip(target); });
  document.addEventListener("mouseout", (event) => { if (event.target.closest("[data-tip]") && !event.target.closest("[data-tip]").contains(event.relatedTarget)) scheduleTooltipHide(); });
  document.addEventListener("focusin", (event) => { tooltipDismissed = false; showTooltip(event.target.closest("[data-tip]")); });
  document.addEventListener("pointermove", (event) => { if (tooltipDismissed) { tooltipDismissed = false; showTooltip(event.target.closest("[data-tip]")); } });
  document.addEventListener("focusout", hideTooltip);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") { tooltipDismissed = true; hideTooltip(); } });
  window.addEventListener("scroll", () => {
    const focused = document.activeElement?.closest("[data-tip]");
    if (focused && !tooltip.hidden) showTooltip(focused);
    else hideTooltip();
  }, true);
  function notice(key, kind = "", detail = "") {
    noticeKey = key ? {key,kind,detail} : null;
    $("notice").hidden = !key;
    $("notice").className = `notice ${kind}`;
    $("notice").textContent = key ? `${t(key)}${detail ? ` ${detail}` : ""}` : "";
  }
  function applyLanguage() {
    document.documentElement.lang = language;
    document.querySelectorAll("[data-i18n]").forEach((element) => { element.textContent = t(element.dataset.i18n); });
    document.querySelectorAll("[data-aria]").forEach((element) => element.setAttribute("aria-label", t(element.dataset.aria)));
    document.querySelectorAll("[data-alt]").forEach((element) => element.alt = t(element.dataset.alt));
    $("language-toggle").textContent = language === "en" ? "EN / DE" : "DE / EN";
    $("language-toggle").setAttribute("aria-pressed", String(language === "de"));
    document.title = `ThoraxBench Local · ${t("research")}`;
    $("findings-table").setAttribute("aria-label", language === "en" ? "Findings" : "Befunde");
    $("libraries-table").setAttribute("aria-label", language === "en" ? "Dependency licenses" : "Lizenzen der Abhängigkeiten");
    renderStudies(); renderModels(); renderStudyFacts(); renderResult(); applyTheme(); showSlice();
    if (noticeKey) notice(noticeKey.key, noticeKey.kind, noticeKey.detail);
    if (busy) setText("run-analysis", t("running"));
    if (tooltipTarget) showTooltip(tooltipTarget);
    if (location.pathname === "/about") setText("page-crumb", t("about"));
  }
  function applyTheme() {
    document.documentElement.dataset.theme = theme;
    $("theme-toggle").textContent = `${theme === "light" ? "☀" : "☾"} ${t(theme)}`;
    $("theme-toggle").setAttribute("aria-pressed", String(theme === "dark"));
    $("theme-toggle").setAttribute("aria-label", language === "en" ? `Switch to ${theme === "light" ? "dark" : "light"} theme` : `Zum ${theme === "light" ? "dunklen" : "hellen"} Design wechseln`);
  }
  function currentStudy() { return studies[Number($("study-select").value)] || null; }
  function renderStudies() {
    const previous = $("study-select").value;
    $("study-select").replaceChildren();
    if (!studies.length) { $("study-select").add(new Option(t("noStudies"), "")); return; }
    studies.forEach((study, index) => $("study-select").add(new Option(`${study.dataset} / ${study.case_id}`, String(index))));
    if ([...$("study-select").options].some((option) => option.value === previous)) $("study-select").value = previous;
  }
  function renderModels() {
    const previous = $("model-select").value || "heuristic-hu";
    $("model-select").replaceChildren();
    models.forEach((model) => { const option = new Option(`${model.id} · ${t(model.available ? "available" : "unavailable")}`, model.id); option.disabled = !model.available; $("model-select").add(option); });
    if (models.some((model) => model.id === previous)) $("model-select").value = previous;
    else if (models.some((model) => model.id === "heuristic-hu")) $("model-select").value = "heuristic-hu";
    renderModelStatus();
  }
  function renderModelStatus() {
    const model = models.find((entry) => entry.id === $("model-select").value);
    setText("model-status", t(model?.available ? "modelReady" : "modelNotReady"));
    updateControls();
  }
  function renderStudyFacts() {
    const study = currentStudy();
    setText("study-phase", study ? t(study.dataset === "demo" ? "synthetic" : study.phase) : "—");
    setText("study-qc", study ? t(study.qc_adequate ? "adequate" : "inadequate") : "—");
    setText("study-slices", study ? `${study.n_slices} ${t("slices")}` : "—");
    updateControls();
  }
  function updateControls() {
    const study = currentStudy(), model = models.find((entry) => entry.id === $("model-select").value);
    ["study-select","model-select","window-select","image-count","create-demo"].forEach((id) => { $(id).disabled = busy; });
    $("slice-slider").disabled = busy || !study;
    $("run-analysis").disabled = busy || !study || !model?.available;
    $("image-count").disabled = busy || $("model-select").value === "heuristic-hu";
    $("run-analysis").textContent = t(busy ? "running" : "run");
    document.body.classList.toggle("busy", busy);
    $("analysis-page").setAttribute("aria-busy", String(busy));
  }
  function setBusy(value) { busy = value; updateControls(); }
  function showSlice(reset = false) {
    const study = currentStudy();
    if (!study) { $("ct-image").hidden = true; $("viewer-empty").hidden = false; return; }
    $("slice-slider").max = Math.max(0, study.n_slices - 1);
    if (reset) $("slice-slider").value = Math.floor(study.n_slices / 2);
    const index = Number($("slice-slider").value);
    setText("slice-counter", `${index + 1} / ${study.n_slices}`);
    $("slice-slider").setAttribute("aria-valuetext", `${t("slice")} ${index + 1} / ${study.n_slices}`);
    $("ct-image").src = `/api/studies/${encodeURIComponent(study.dataset)}/${encodeURIComponent(study.case_id)}/slice/${index}.png?window=${encodeURIComponent($("window-select").value)}`;
    $("ct-image").hidden = false; $("viewer-empty").hidden = true;
  }
  async function api(path, body) {
    const response = await fetch(path, body === undefined ? {} : {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`);
    return data;
  }
  function cell(value, tip) { const element = document.createElement("td"); element.textContent = value; if (tip) { element.dataset.tip = tip; element.tabIndex = 0; } return element; }
  function renderResult() {
    $("results-empty").hidden = !!output; $("results-content").hidden = !output;
    if (!output) return;
    const result = output.result, findings = result.report.findings || [];
    setText("metric-model", result.model_id);
    setText("metric-time", `${Number(result.perf.total_s).toFixed(3)} s`);
    setText("metric-status", t(result.report.abstain || result.raw_error ? "abstained" : "completed"));
    setText("metric-findings", String(findings.length));
    $("findings-body").replaceChildren();
    findings.forEach((finding) => { const row = document.createElement("tr"); row.append(cell(finding.label.replaceAll("_", " "),"findingTip"),cell(t(finding.present === true ? "present" : finding.present === false ? "absent" : "uncertain"),"presenceTip"),cell(finding.present == null || finding.confidence == null ? "—" : Number(finding.present ? finding.confidence : 1 - finding.confidence).toFixed(2),"scoreTip"),cell(t(finding.laterality || "unknown"),"sideTip"),cell(finding.size_mm == null ? "—" : `${finding.size_mm} mm`,"sizeTip")); $("findings-body").append(row); });
    if (!findings.length) { const row = document.createElement("tr"), message = cell(t("noFindings"), "resultStatusTip"); message.colSpan = 5; row.append(message); $("findings-body").append(row); }
    setText("report-content", output.markdown);
    [["download-json","json"],["download-report","markdown"],["download-html","html"]].forEach(([id,key]) => { const url = output.downloads[key]; if (url) { $(id).href = url; $(id).setAttribute("aria-disabled","false"); $(id).setAttribute("download",""); } });
    initializeTooltips();
  }
  function clearResult() { output = null; renderResult(); ["download-json","download-report","download-html"].forEach((id) => { $(id).removeAttribute("href"); $(id).setAttribute("aria-disabled","true"); }); }
  $("language-toggle").addEventListener("click", () => { language = language === "en" ? "de" : "en"; save("thoraxbench.language",language); applyLanguage(); });
  $("theme-toggle").addEventListener("click", () => { theme = theme === "light" ? "dark" : "light"; save("thoraxbench.theme",theme); applyTheme(); });
  $("study-select").addEventListener("change", () => { clearResult(); notice(null); renderStudyFacts(); showSlice(true); });
  $("model-select").addEventListener("change", renderModelStatus);
  $("slice-slider").addEventListener("input", () => showSlice());
  $("window-select").addEventListener("change", () => showSlice());
  $("ct-image").addEventListener("error", () => { $("ct-image").hidden = true; $("viewer-empty").hidden = false; notice("sliceFailed","error"); });
  $("create-demo").addEventListener("click", async () => {
    setBusy(true); notice("creating");
    try { const data = await api("/api/demo",{}); studies = data.studies; renderStudies(); const index = studies.findIndex((study) => study.dataset === "demo"); $("study-select").value = String(index >= 0 ? index : 0); clearResult(); renderStudyFacts(); showSlice(true); notice("demoReady"); }
    catch (error) { notice("failed","error",error.message); }
    finally { setBusy(false); }
  });
  $("run-analysis").addEventListener("click", async () => {
    const study = currentStudy(), count = Number($("image-count").value);
    if (!Number.isInteger(count) || count < 1 || count > 16) { notice("invalidImages","error"); return; }
    if (!study) return;
    clearResult(); setBusy(true); notice("running");
    try { output = await api("/api/analyze",{dataset:study.dataset,case_id:study.case_id,model_id:$("model-select").value,n_images:count}); renderResult(); notice(output.result.report.abstain || output.result.raw_error ? "abstainNotice" : "complete", output.result.report.abstain || output.result.raw_error ? "warning" : ""); }
    catch (error) { notice("failed","error",error.message); }
    finally { setBusy(false); }
  });
  async function loadAbout() {
    const about = await api("/api/about");
    setText("about-author", about.author); setText("about-version", about.version); setText("about-license", about.license);
    if (about.email) { const link = document.createElement("a"); link.href = `mailto:${about.email}`; link.textContent = about.author; link.dataset.tip = "authorTip"; $("about-author").replaceChildren(link); }
    $("libraries-body").replaceChildren();
    (about.libraries || []).forEach((library) => { const row = document.createElement("tr"); row.append(cell(library.name,"libraryTip"),cell(library.version,"versionTip"),cell(library.license,"licenseTip")); $("libraries-body").append(row); });
    initializeTooltips();
  }
  if (location.pathname === "/about") { $("analysis-page").hidden = true; $("about-page").hidden = false; $("nav-analysis").classList.remove("active"); $("nav-about").classList.add("active"); $("nav-about").setAttribute("aria-current","page"); }
  else $("nav-analysis").setAttribute("aria-current","page");
  initializeTooltips(); applyLanguage();
  if (location.pathname === "/about") loadAbout().catch((error) => { const message = document.createElement("p"); message.className = "notice error"; message.role = "alert"; message.textContent = `${t("failed")} ${error.message}`; $("about-page").prepend(message); });
  else Promise.all([api("/api/studies"),api("/api/models")]).then(([studyData,modelData]) => { studies = studyData.studies; models = modelData.models; renderStudies(); renderModels(); renderStudyFacts(); showSlice(true); }).catch((error) => notice("failed","error",error.message));
})();
