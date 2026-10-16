/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it> */
"use strict";
(() => {
  const words = {
    en: {
      setupHeading:"Model availability & setup",setupIntro:"Unavailable models need local setup. Review model terms, access approval, disk space and hardware before downloading weights.",setupTip:"Inspect every configured model and its setup requirements. Downloads retrieve model weights only; study images stay local. Access gates and license terms still apply.",setupOllama:"Model tag is absent from local Ollama, or Ollama is unreachable. Review the model terms and available disk space/VRAM, start local Ollama, acknowledge the terms below, then download this configured model.",setupService:"Obtain the publisher’s permitted weights and any required access approval. Review the model configuration below, provide suitable hardware, then start its configured loopback HTTP service. Automatic download cannot bypass access gates or install this service.",setupBaseline:"Included deterministic baseline; no download required.",setupAvailable:"Locally available; no download required.",setupMetadata:"Provider configuration (English)",setupMetadataTip:"Exact model identifier, configured tag, provider notes and operator instructions. Preserve these source details when checking upstream access and service requirements.",sourceTerms:"Model source — locate and review upstream terms",terms:"Model terms",termsTip:"Open the publisher’s model terms. Read and determine whether you may use these weights before acknowledging and downloading.",termsAck:"I reviewed and may comply with the applicable model terms",termsAckTip:"Your explicit acknowledgement is required before downloading this model. This does not grant access or replace publisher approval.",downloadModel:"Download model weights",downloadModelTip:"Ask local Ollama to download only this configured model tag. This uses network access and disk space; model inference remains local. No download begins until you acknowledge the terms and choose this action.",downloadProgress:"Model download",downloadProgressTip:"Actual Ollama status and active layer bytes, not whole-model completion percentage. Layers may change or reset the counters. Analysis is locked while the download is active.",queued:"Queued",downloadRunning:"Downloading",downloadCompleted:"Download finished",downloadFailed:"Download failed",layerBytes:"Active layer bytes",refreshModels:"Refresh model availability",refreshModelsTip:"Check the local Ollama inventory again after manual setup or a failed download.",forecast:"Rough remaining estimate",forecastSeed:"Initial workstation guess; may take longer",forecastHistory:"Based on local request history; may take longer",forecastOver:"Taking longer than estimated; still running",forecastDone:"Request finished; elapsed time is shown above",forecastTip:"Planning guess, not measured model progress or a guarantee. Initial ranges: HU rules 1–60 seconds; vision models 1–15+ minutes. Later estimates use half to twice the recent local wall time for that model and image count. No study identifiers are saved. Larger inputs or a busy workstation can take longer.",comparisonSingle:"Only one model returned an output; this does not support a cross-model comparison.",compareModels:"Compare recommended local models",compareTip:"Run locally available recommended models one after another on this study. Unavailable models are skipped. Differences in findings or scores do not establish accuracy.",compareRun:"Compare local models",comparisonHeading:"Local model comparison",comparisonNote:"Sequential runs on the same study. Shows agreement and disagreement without reference labels, not an accuracy ranking. Scores are uncalibrated and not directly comparable across model families. Inspect each model’s failures and abstentions.",waiting:"Waiting",skipped:"Skipped: unavailable",error:"Failed",comparisonDone:"Comparison finished. Inspect completed, abstained, failed and skipped models below.",activeModel:"Current model",modelElapsed:"Current model elapsed",batchProgress:"Batch progress",wallTime:"Browser wall time",wallTip:"Elapsed browser time for this model request, including loading and report generation. Separate from engine stage timing.",progressTip:"Model position and elapsed request time, not inference completion percentage. Recommended models run sequentially. Unavailable models are skipped; completed results remain available when another model fails.",inspect:"Inspect result",inspectTip:"Open this model’s findings, report and individual downloads in the detailed outcome section.",comparisonDownload:"Download comparison HTML",comparisonExportTip:"Download an offline comparison of the completed outputs, including explicit skipped and failed models. Differences are not benchmark accuracy.",comparisonExportFailed:"Comparison export failed. Individual completed results remain downloadable.",noPrediction:"No prediction",actualImages:"Actual prepared model images",actualImagesTip:"Actual rendered images recorded by the engine, including any extra landmark, coronal or window views. This is not the requested source-slice target. Zero means no rendered model images were prepared; unknown stays unavailable.",requestElapsed:"Browser request elapsed",requestElapsedTip:"Wall-clock time since this browser started the analysis request, including loading, inference and report generation. Separate from the measured engine stages returned below.",skipTip:"Move keyboard focus directly to the research workspace.",noticeTip:"Status of the most recent local request. Errors show a reason so you can correct the input or retry.",brandLocal:"LOCAL RESEARCH",skip:"Skip to workspace",workspace:"Workspace",navigation:"Main navigation",analysis:"Analysis",about:"About",local:"Runs on your workstation",privacy:"Local inference. No telemetry.",light:"Light",dark:"Dark",languageAria:"Switch interface to German",themeAria:"Switch to dark theme",research:"Research use only",disclaimer:"Self-made experimental research tool. Not medical advice from a qualified healthcare professional, a diagnosis, or a medical device. Findings may be incorrect, incomplete or misleading; do not use for diagnosis or treatment decisions.",eyebrow:"LOCAL RESEARCH WORKBENCH",heading:"A study. A model. Inspectable results.",intro:"Explore a synthetic demo or a development study with the same engine as the CLI.",holdout:"Sealed holdout protected",inputHeading:"Choose a study",inputIntro:"Only synthetic and permitted development studies appear here.",study:"Study",loading:"Loading…",noStudies:"No studies yet — create a demo",createDemo:"Create synthetic demo",modelHeading:"Select a local model",model:"Model",modelNote:"Availability is not benchmark performance.",imageCount:"Target source slices",baselineNote:"The heuristic baseline uses HU measurements; it does not send images to a vision model.",run:"Run analysis locally",runtimeNote:"Vision models can take several minutes. Failed or inadequate inputs abstain.",viewerHeading:"Study viewer",viewerNote:"Axial DICOM slice · research inspection",viewerEmpty:"Your study appears here",viewerEmptyNote:"Create a synthetic demo to try the complete pipeline.",sliceAlt:"Axial CT research slice",window:"Window",lung:"Lung",soft:"Mediastinum",bone:"Bone",abdomen:"Abdomen",slice:"Slice",resultsHeading:"Inspect the outcome",downloadHtml:"Download HTML",htmlNote:"The standalone HTML report combines input images, findings and reported evidence references. References are not verified localization.",htmlTip:"Download a self-contained HTML research report with embedded images. Open it in a browser without the server. Images are research inputs, not validated finding overlays.",evidenceTip:"Evidence references are the model’s reported association with input views or slices. They do not establish a verified location or segmentation.",downloadJson:"Download JSON",downloadReport:"Download report",resultsEmpty:"Ready when you are.",resultsEmptyNote:"Run a study to inspect findings, timing, provenance and the English research report.",engineTime:"Engine stages",status:"Status",findingCount:"Findings returned",scoresNotice:"Higher presence scores mean more support that a finding is present. Scores are uncalibrated; accuracy remains unmeasured.",finding:"Finding",presence:"Presence",score:"Presence score",side:"Side",size:"Size",reportHeading:"English research report",reportLanguage:"The reproducible research report stays in English. The interface language does not change model prompts or results.",aboutEyebrow:"TRANSPARENT BY DESIGN",aboutHeading:"About ThoraxBench Local",aboutIntro:"A local laboratory for reproducible thoracic CT model research.",project:"The project",projectText:"Inspect the path from DICOM input to model output, with explicit quality checks and provenance. This MVP supports individual study exploration; comparative benchmarking is still pending.",author:"Author",version:"Version",license:"Project license",aiNote:"Self-made with AI assistance and to the best of our knowledge. Errors and omissions remain possible; research outputs require independent evaluation.",libraries:"Libraries & licenses",librariesNote:"Installed runtime dependencies and their declared licenses.",library:"Library",licenseShort:"License",footer:"Research use only · Local inference · No telemetry",available:"available locally",unavailable:"unavailable",synthetic:"Synthetic",calibration:"Calibration",internal_test:"Internal test",development:"Development",adequate:"QC adequate",inadequate:"QC limited",slices:"slices",running:"Running locally…",creating:"Creating synthetic demo…",demoReady:"Synthetic demo ready. Select a model and run your first analysis.",complete:"Analysis completed. Inspect the uncalibrated findings and research report below.",abstained:"Abstained",completed:"Completed",abstainNotice:"The engine abstained. No reliable finding summary is available; inspect the report for the reason.",failed:"Request failed",invalidImages:"Choose an image count between 1 and 16.",sliceFailed:"The slice could not be displayed. Check the study quality or choose another study.",present:"Present",absent:"Not detected",uncertain:"Uncertain",left:"Left",right:"Right",bilateral:"Bilateral",midline:"Midline",unknown:"Unknown",noFindings:"No findings returned. Inspect the report and abstention status.",modelReady:"Locally available · benchmark accuracy not yet measured",modelNotReady:"Unavailable · choose another local model",brandTip:"Open the local research workspace. All inference stays on this workstation.",analysisTip:"Inspect a development or synthetic study and run a local model.",aboutTip:"View the author, software version, and dependency licenses.",localTip:"No cloud inference or telemetry. The app uses local services only.",languageTip:"Switch the interface between English and German. Reports and model prompts stay in English.",themeTip:"Switch between light and dark appearance. Your choice is saved in this browser.",holdoutTip:"Sealed validation studies are hidden and cannot be opened by this development interface.",studyTip:"Choose a synthetic demo or a case permitted by the frozen development split.",phaseTip:"The study's development subset. Synthetic demos are separate from the patient split.",qcTip:"Quality control indicates whether the input supports this research pipeline. It does not establish clinical suitability.",slicesTip:"Number of axial slices in the selected study.",demoTip:"Generate a synthetic 64-slice DICOM phantom with a nodule and effusion. No patient data is used.",modelTip:"Choose the deterministic HU baseline or a locally hosted model. Available does not mean benchmarked.",availabilityTip:"Local availability checks whether the model can run. No accuracy ranking is implied.",imagesTip:"For vision models, request a target of 1–16 source slices. Anatomy sampling can retain more landmark slices than requested; coronal and multi-window views can add images. Results show the actual prepared count. The HU heuristic sends no model images.",runTip:"Run the selected study and local model. Changing controls is disabled until this request completes.",sliceTip:"Browse axial slices. Use Left and Right arrow keys on the slider; displayed numbering starts at 1.",windowTip:"Change the display window only. This does not change analysis settings or predictions.",jsonTip:"Download the full research result, including findings, QC, timings, hashes and provenance.",reportTip:"Download the English Markdown research report. It is not a patient care plan.",resultModelTip:"The model that produced the currently displayed result.",timingTip:"Measured engine stages only. Excludes DICOM loading, report rendering and provenance collection.",resultStatusTip:"Completed means the engine returned output. Abstention means the engine declined to provide findings.",findingCountTip:"Count of returned findings, including uncertain or negative entries. This is not an accuracy metric.",scoresTip:"Uncalibrated heuristic or model outputs. Do not interpret them as validated probabilities.",findingTip:"Canonical ontology label returned by the engine. Finding names are research artifact identifiers.",presenceTip:"The model's reported presence, absence or uncertainty.",scoreTip:"Higher values mean more support for the finding being present. Uncalibrated, not an accuracy measure. Missing confidence or uncertain presence is shown without a score.",sideTip:"Reported laterality, not an independently verified localization.",sizeTip:"Reported candidate diameter in millimeters, when available.",reportBodyTip:"Expand the complete English Markdown research report, displayed as safe plain text.",authorTip:"Project author and maintainer.",versionTip:"Installed software version for this local application or dependency.",licenseTip:"Declared software license. See the source distribution for full terms and attribution.",libraryTip:"Runtime library used by the local Python application."
    },
    de: {
      setupHeading:"Modellverfügbarkeit und Einrichtung",setupIntro:"Nicht verfügbare Modelle benötigen eine lokale Einrichtung. Modellbedingungen, Zugangsfreigabe, Speicherplatz und Hardware vor dem Herunterladen prüfen.",setupTip:"Alle konfigurierten Modelle und ihre Einrichtungsvoraussetzungen prüfen. Heruntergeladen werden nur Modellgewichte; Studienbilder bleiben lokal. Zugangsbeschränkungen und Lizenzbedingungen gelten weiterhin.",setupOllama:"Der Modell-Tag fehlt in lokalem Ollama oder Ollama ist nicht erreichbar. Modellbedingungen, Speicherplatz und VRAM prüfen, lokales Ollama starten, unten die Bedingungen bestätigen und dieses konfigurierte Modell herunterladen.",setupService:"Zulässige Gewichte beim Anbieter beschaffen und erforderliche Zugangsfreigaben einholen. Unten die Modellkonfiguration prüfen, geeignete Hardware bereitstellen und den konfigurierten lokalen HTTP-Dienst starten. Ein automatischer Download kann weder Zugangssperren umgehen noch diesen Dienst installieren.",setupBaseline:"Enthaltene deterministische Heuristik; kein Download erforderlich.",setupAvailable:"Lokal verfügbar; kein Download erforderlich.",setupMetadata:"Anbieterkonfiguration (Englisch)",setupMetadataTip:"Exakte Modellkennung, konfigurierter Tag, Anbieterhinweise und Einrichtungsschritte. Diese Quellenangaben bei der Prüfung von Zugangs- und Dienstvoraussetzungen beibehalten.",sourceTerms:"Modellquelle — geltende Anbieterbedingungen suchen und prüfen",terms:"Modellbedingungen",termsTip:"Modellbedingungen des Anbieters öffnen. Vor der Bestätigung und dem Download prüfen, ob Sie diese Gewichte verwenden dürfen.",termsAck:"Ich habe die geltenden Modellbedingungen geprüft und kann sie einhalten",termsAckTip:"Vor dem Modelldownload ist Ihre ausdrückliche Bestätigung erforderlich. Sie erteilt keinen Zugang und ersetzt keine Anbieterfreigabe.",downloadModel:"Modellgewichte herunterladen",downloadModelTip:"Lokales Ollama anweisen, ausschließlich diesen konfigurierten Modell-Tag herunterzuladen. Benötigt Netzwerk und Speicherplatz; die Inferenz bleibt lokal. Der Download beginnt erst nach Ihrer Bestätigung und Auswahl dieser Aktion.",downloadProgress:"Modelldownload",downloadProgressTip:"Tatsächlicher Ollama-Status und Bytes der aktiven Schicht, kein Fertigstellungsprozentsatz des gesamten Modells. Schichtenwechsel können die Zähler zurücksetzen. Während des Downloads sind Analysen gesperrt.",queued:"Wartet",downloadRunning:"Wird heruntergeladen",downloadCompleted:"Download beendet",downloadFailed:"Download fehlgeschlagen",layerBytes:"Bytes der aktiven Schicht",refreshModels:"Modellverfügbarkeit aktualisieren",refreshModelsTip:"Lokales Ollama-Inventar nach manueller Einrichtung oder fehlgeschlagenem Download erneut prüfen.",forecast:"Grobe verbleibende Zeitschätzung",forecastSeed:"Anfängliche Schätzung für diesen Rechner; längere Laufzeit möglich",forecastHistory:"Aus lokalem Anfrageverlauf geschätzt; längere Laufzeit möglich",forecastOver:"Dauert länger als geschätzt; läuft weiterhin",forecastDone:"Anfrage beendet; verstrichene Zeit steht oben",forecastTip:"Planungsschätzung, kein gemessener Modellfortschritt und keine Garantie. Anfangsbereiche: HU-Regeln 1–60 Sekunden; Vision-Modelle 1–15+ Minuten. Später wird die halbe bis doppelte lokale Anfragezeit für Modell und Bildanzahl geschätzt. Keine Studienkennungen werden gespeichert. Größere Eingaben oder Rechnerauslastung können die Laufzeit verlängern.",comparisonSingle:"Nur ein Modell hat eine Ausgabe geliefert; damit ist kein Vergleich zwischen Modellen möglich.",compareModels:"Empfohlene lokale Modelle vergleichen",compareTip:"Lokal verfügbare empfohlene Modelle nacheinander auf dieser Studie ausführen. Nicht verfügbare Modelle werden übersprungen. Unterschiede bei Befunden oder Werten belegen keine Genauigkeit.",compareRun:"Lokale Modelle vergleichen",comparisonHeading:"Vergleich lokaler Modelle",comparisonNote:"Aufeinanderfolgende Durchläufe auf derselben Studie. Zeigt Übereinstimmungen und Unterschiede ohne Referenzlabels, keine Genauigkeitsrangfolge. Werte sind unkalibriert und nicht direkt zwischen Modellfamilien vergleichbar. Fehler und Enthaltungen jedes Modells prüfen.",waiting:"Wartet",skipped:"Übersprungen: nicht verfügbar",error:"Fehlgeschlagen",comparisonDone:"Vergleich beendet. Abgeschlossene, enthaltene, fehlgeschlagene und übersprungene Modelle unten prüfen.",activeModel:"Aktuelles Modell",modelElapsed:"Zeit des aktuellen Modells",batchProgress:"Vergleichsfortschritt",wallTime:"Gesamtzeit im Browser",wallTip:"Verstrichene Zeit im Browser für diese Modellanfrage einschließlich Laden und Berichtserstellung. Getrennt von der Engine-Schrittzeit.",progressTip:"Modellposition und verstrichene Anfragezeit, kein Prozentsatz der abgeschlossenen Inferenz. Empfohlene Modelle laufen nacheinander. Nicht verfügbare Modelle werden übersprungen; abgeschlossene Ergebnisse bleiben bei Fehlern anderer Modelle verfügbar.",inspect:"Ergebnis prüfen",inspectTip:"Befunde, Bericht und einzelne Downloads dieses Modells im ausführlichen Ergebnisbereich öffnen.",comparisonDownload:"Vergleich als HTML herunterladen",comparisonExportTip:"Offline-Vergleich der abgeschlossenen Ausgaben einschließlich übersprungener und fehlgeschlagener Modelle herunterladen. Unterschiede belegen keine Benchmark-Genauigkeit.",comparisonExportFailed:"Vergleichsexport fehlgeschlagen. Einzelne abgeschlossene Ergebnisse bleiben herunterladbar.",noPrediction:"Keine Vorhersage",actualImages:"Tatsächlich vorbereitete Modellbilder",actualImagesTip:"Tatsächlich von der Engine aufgezeichnete gerenderte Bilder einschließlich zusätzlicher Landmarken-, Koronal- oder Fensteransichten. Dies ist nicht die angeforderte Quellschicht-Zielanzahl. Null bedeutet, dass keine Modellbilder vorbereitet wurden; unbekannte Werte bleiben nicht verfügbar.",requestElapsed:"Verstrichene Anfragezeit im Browser",requestElapsedTip:"Gesamtzeit seit Beginn der Analyseanfrage im Browser, einschließlich Laden, Inferenz und Berichtserstellung. Getrennt von den unten angezeigten gemessenen Engine-Schritten.",skipTip:"Den Tastaturfokus direkt in den Forschungsarbeitsbereich verschieben.",noticeTip:"Status der letzten lokalen Anfrage. Bei Fehlern wird ein Grund angezeigt, damit Sie die Eingabe korrigieren oder erneut versuchen können.",brandLocal:"LOKALE FORSCHUNG",skip:"Zum Arbeitsbereich",workspace:"Arbeitsbereich",navigation:"Hauptnavigation",analysis:"Analyse",about:"Über",local:"Läuft auf Ihrem Rechner",privacy:"Lokale Inferenz. Keine Telemetrie.",light:"Hell",dark:"Dunkel",languageAria:"Oberfläche auf Englisch umstellen",themeAria:"Zum dunklen Design wechseln",research:"Nur für Forschungszwecke",disclaimer:"Selbst entwickeltes experimentelles Forschungswerkzeug. Keine medizinische Beratung durch qualifiziertes medizinisches Fachpersonal, keine Diagnose und kein Medizinprodukt. Ergebnisse können falsch, unvollständig oder irreführend sein; nicht für Diagnose- oder Behandlungsentscheidungen verwenden.",eyebrow:"LOKALER FORSCHUNGSARBEITSPLATZ",heading:"Eine Studie. Ein Modell. Prüfbare Ergebnisse.",intro:"Untersuchen Sie eine synthetische Demo oder Entwicklungsstudie mit derselben Engine wie in der CLI.",holdout:"Versiegelte Validierung geschützt",inputHeading:"Studie auswählen",inputIntro:"Hier erscheinen nur synthetische und zugelassene Entwicklungsstudien.",study:"Studie",loading:"Wird geladen…",noStudies:"Noch keine Studien — Demo erstellen",createDemo:"Synthetische Demo erstellen",modelHeading:"Lokales Modell auswählen",model:"Modell",modelNote:"Verfügbarkeit ist kein Benchmark-Ergebnis.",imageCount:"Zielanzahl der Quellschichten",baselineNote:"Die HU-Heuristik nutzt Messwerte und sendet keine Bilder an ein Vision-Modell.",run:"Analyse lokal starten",runtimeNote:"Vision-Modelle benötigen gegebenenfalls mehrere Minuten. Bei Fehlern oder ungeeigneten Eingaben enthält sich die Engine.",viewerHeading:"Studienansicht",viewerNote:"Axiale DICOM-Schicht · Forschungsansicht",viewerEmpty:"Hier erscheint Ihre Studie",viewerEmptyNote:"Erstellen Sie eine synthetische Demo, um die gesamte Verarbeitung zu testen.",sliceAlt:"Axiale CT-Schicht für Forschungszwecke",window:"Fenster",lung:"Lunge",soft:"Mediastinum",bone:"Knochen",abdomen:"Abdomen",slice:"Schicht",resultsHeading:"Ergebnis prüfen",downloadHtml:"HTML herunterladen",htmlNote:"Der eigenständige HTML-Bericht verbindet Eingabebilder, Befunde und angegebene Evidenzverweise. Die Verweise sind keine verifizierte Lokalisation.",htmlTip:"Eigenständigen HTML-Forschungsbericht mit eingebetteten Bildern herunterladen und ohne Server im Browser öffnen. Die Bilder sind Forschungseingaben, keine validierten Befund-Overlays.",evidenceTip:"Evidenzverweise sind die vom Modell angegebenen Zuordnungen zu Eingabeansichten oder Schichten. Sie belegen keine verifizierte Position oder Segmentierung.",downloadJson:"JSON herunterladen",downloadReport:"Bericht herunterladen",resultsEmpty:"Bereit für die erste Analyse.",resultsEmptyNote:"Starten Sie eine Studie, um Befunde, Laufzeit, Provenienz und den englischen Forschungsbericht zu prüfen.",engineTime:"Engine-Schritte",status:"Status",findingCount:"Zurückgegebene Befunde",scoresNotice:"Höhere Werte sprechen stärker für das Vorhandensein eines Befunds. Die Werte sind unkalibriert; die Genauigkeit ist noch nicht gemessen.",finding:"Befund",presence:"Vorhandensein",score:"Wert für Vorhandensein",side:"Seite",size:"Größe",reportHeading:"Englischer Forschungsbericht",reportLanguage:"Der reproduzierbare Forschungsbericht bleibt auf Englisch. Die Sprache der Oberfläche ändert weder Modell-Prompts noch Ergebnisse.",aboutEyebrow:"TRANSPARENZ ALS PRINZIP",aboutHeading:"Über ThoraxBench Local",aboutIntro:"Ein lokales Labor für reproduzierbare Forschung an Thorax-CT-Modellen.",project:"Das Projekt",projectText:"Prüfen Sie den Weg von DICOM-Daten zur Modellausgabe einschließlich Qualitätskontrolle und Provenienz. Dieses MVP ermöglicht die Untersuchung einzelner Studien; vergleichende Benchmarks stehen noch aus.",author:"Autor",version:"Version",license:"Projektlizenz",aiNote:"Selbst entwickelt mit KI-Unterstützung und nach bestem Wissen. Fehler und Auslassungen sind möglich; Forschungsergebnisse erfordern eine unabhängige Bewertung.",libraries:"Bibliotheken & Lizenzen",librariesNote:"Installierte Laufzeitabhängigkeiten mit ihren deklarierten Lizenzen.",library:"Bibliothek",licenseShort:"Lizenz",footer:"Nur für Forschungszwecke · Lokale Inferenz · Keine Telemetrie",available:"lokal verfügbar",unavailable:"nicht verfügbar",synthetic:"Synthetisch",calibration:"Kalibrierung",internal_test:"Interner Test",development:"Entwicklung",adequate:"QC ausreichend",inadequate:"QC eingeschränkt",slices:"Schichten",running:"Lokale Verarbeitung läuft…",creating:"Synthetische Demo wird erstellt…",demoReady:"Synthetische Demo bereit. Wählen Sie ein Modell und starten Sie Ihre erste Analyse.",complete:"Analyse abgeschlossen. Prüfen Sie unten die unkalibrierten Befunde und den Forschungsbericht.",abstained:"Enthaltung",completed:"Abgeschlossen",abstainNotice:"Die Engine hat sich enthalten. Es liegt keine belastbare Befundzusammenfassung vor; der Bericht nennt den Grund.",failed:"Anfrage fehlgeschlagen",invalidImages:"Wählen Sie eine Bildanzahl zwischen 1 und 16.",sliceFailed:"Die Schicht konnte nicht angezeigt werden. Prüfen Sie die Studienqualität oder wählen Sie eine andere Studie.",present:"Vorhanden",absent:"Nicht erkannt",uncertain:"Unklar",left:"Links",right:"Rechts",bilateral:"Beidseits",midline:"Mittig",unknown:"Unbekannt",noFindings:"Keine Befunde zurückgegeben. Prüfen Sie Bericht und Enthaltungsstatus.",modelReady:"Lokal verfügbar · Benchmark-Genauigkeit noch nicht gemessen",modelNotReady:"Nicht verfügbar · anderes lokales Modell wählen",brandTip:"Lokalen Forschungsarbeitsbereich öffnen. Jede Inferenz bleibt auf diesem Rechner.",analysisTip:"Entwicklungsstudie oder synthetische Studie untersuchen und ein lokales Modell starten.",aboutTip:"Autor, Softwareversion und Lizenzen der Abhängigkeiten anzeigen.",localTip:"Keine Cloud-Inferenz oder Telemetrie. Die Anwendung nutzt ausschließlich lokale Dienste.",languageTip:"Zwischen deutscher und englischer Oberfläche wechseln. Berichte und Modell-Prompts bleiben auf Englisch.",themeTip:"Zwischen hellem und dunklem Design wechseln. Die Auswahl wird in diesem Browser gespeichert.",holdoutTip:"Versiegelte Validierungsstudien sind verborgen und in dieser Entwicklungsoberfläche nicht zugänglich.",studyTip:"Synthetische Demo oder einen Fall aus der eingefrorenen Entwicklungsaufteilung auswählen.",phaseTip:"Entwicklungs-Teilmenge dieser Studie. Synthetische Demos gehören nicht zur Patientenaufteilung.",qcTip:"Die Qualitätskontrolle bewertet die Eignung für diese Forschungspipeline, nicht die klinische Eignung.",slicesTip:"Anzahl axialer Schichten der ausgewählten Studie.",demoTip:"Synthetisches DICOM-Phantom mit 64 Schichten, Rundherd und Erguss erzeugen. Es werden keine Patientendaten verwendet.",modelTip:"Deterministische HU-Heuristik oder lokal gehostetes Modell auswählen. Verfügbar bedeutet nicht benchmark-validiert.",availabilityTip:"Die lokale Verfügbarkeit prüft, ob das Modell lauffähig ist. Sie stellt keine Genauigkeitsbewertung dar.",imagesTip:"Für Vision-Modelle eine Zielanzahl von 1–16 Quellschichten anfordern. Anatomisches Sampling kann mehr Landmarken-Schichten beibehalten; koronale und Mehrfenster-Ansichten können Bilder ergänzen. Das Ergebnis zeigt die tatsächliche Anzahl vorbereiteter Bilder. Die HU-Heuristik sendet keine Modellbilder.",runTip:"Ausgewählte Studie mit dem lokalen Modell analysieren. Die Einstellungen bleiben während der Anfrage gesperrt.",sliceTip:"Axiale Schichten durchblättern. Nutzen Sie am Regler die Pfeiltasten links/rechts. Die Anzeige zählt ab 1.",windowTip:"Nur das Darstellungsfenster ändern. Analyseparameter und Vorhersagen bleiben unverändert.",jsonTip:"Vollständiges Forschungsergebnis mit Befunden, QC, Laufzeiten, Hashes und Provenienz herunterladen.",reportTip:"Englischen Markdown-Forschungsbericht herunterladen. Er ist kein Behandlungsplan.",resultModelTip:"Modell, das das aktuell angezeigte Ergebnis erzeugt hat.",timingTip:"Nur gemessene Engine-Schritte. DICOM-Laden, Berichtserstellung und Provenienz-Erfassung sind nicht enthalten.",resultStatusTip:"Abgeschlossen bedeutet, dass die Engine eine Ausgabe geliefert hat. Bei Enthaltung werden keine Befunde zugesichert.",findingCountTip:"Anzahl zurückgegebener Befunde einschließlich unklarer oder negativer Einträge. Keine Genauigkeitsmetrik.",scoresTip:"Unkalibrierte Heuristik- oder Modellausgaben. Nicht als validierte Wahrscheinlichkeiten interpretieren.",findingTip:"Kanonisches Ontologie-Label der Engine. Befundnamen sind Kennungen des Forschungsartefakts.",presenceTip:"Vom Modell angegebene Anwesenheit, Abwesenheit oder Unsicherheit.",scoreTip:"Höhere Werte sprechen stärker für das Vorhandensein des Befunds. Unkalibriert und kein Maß für Genauigkeit. Bei fehlender Konfidenz oder unklarem Vorhandensein wird kein Wert angezeigt.",sideTip:"Angegebene Seite, keine unabhängig überprüfte Lokalisation.",sizeTip:"Angegebener Kandidatendurchmesser in Millimetern, falls vorhanden.",reportBodyTip:"Vollständigen englischen Markdown-Forschungsbericht als sicheren Klartext öffnen.",authorTip:"Autor und Maintainer des Projekts.",versionTip:"Installierte Softwareversion dieser lokalen Anwendung oder Abhängigkeit.",licenseTip:"Deklarierte Softwarelizenz. Vollständige Bedingungen und Namensnennungen stehen in der Quelldistribution.",libraryTip:"Laufzeitbibliothek der lokalen Python-Anwendung."
    }
  };
  Object.assign(words.en, {"studySearch": "Search studies", "studySearchTip": "Filter research study identifiers in the indexed library. This does not search patient names or acquire data.", "datasetFilter": "Dataset", "datasetFilterTip": "Limit the study list to a dataset. Synthetic demos remain separate from development studies.", "allDatasets": "All datasets", "libraryTip": "Visible indexed studies after filtering, total permitted development studies, and synthetic demos. Sealed cases never appear.", "refreshStudies": "Refresh study library", "refreshStudiesTip": "Reload guarded local indexes after indexing or acquiring development studies. Does not download data or read sealed studies.", "optionalDemo": "Optional: try a synthetic study without patient data.", "libraryReady": "Indexed development library ready", "split_required": "Create the development/sealed split before indexing.", "not_indexed": "Development index missing. Index the approved dataset from the CLI, then refresh.", "libraryUnavailable": "Library unavailable. Check local configuration and permissions, then refresh.", "visibleStudies": "visible", "developmentStudies": "development studies", "syntheticStudies": "synthetic demos", "noMatches": "No matching studies — clear the search or change the dataset", "selectStudy": "Select a matching study", "openSetup": "Set up local models", "openSetupTip": "Open local model availability, license review, downloads and manual service setup. No download starts automatically.", "visionInputNote": "Vision models use prepared images. Landmark, coronal and window views can increase the actual input count.", "serviceInputNote": "This model uses its configured local HTTP service. Check model setup for required weights, access and input representation.", "viewerChoose": "Select a development study above, refresh the library, or try the optional synthetic demo.", "viewerFailureTitle": "Slice unavailable", "viewerFailureNote": "Try another slice or display window, or select another study. This display failure does not provide a model prediction.", "resultContextTip": "Identifies the completed study and model, requested source-slice target and actual prepared images. Downloads belong to this recorded run.", "previousSettings": "These results belong to previous settings. Run again to apply the current controls.", "previousSettingsTip": "Changing the study, model, comparison mode or source-slice target does not alter a completed run. Its downloads retain their original inputs.", "severity": "Educational severity", "attention": "Typical review context", "severityTip": "Educational reference context from the project knowledge base for usable positive findings only. It is not a validated assessment, diagnosis or treatment recommendation for this study.", "attentionTip": "General educational review context, not a patient-specific deadline or care instruction. Unknown, negative and abstained findings have no assigned context.", "educationCaution": "Severity and review context are educational reference information, not advice for this study. Inspect evidence in the HTML report.", "incidental": "Incidental", "low": "Low", "moderate": "Moderate", "high": "High", "critical": "Critical", "routine": "Routine review", "soon": "Earlier review", "urgent": "Urgent context", "emergency": "Emergency context", "notAvailable": "Unavailable", "leavingBusy": "A local request is still running."});
  Object.assign(words.de, {"studySearch": "Studien suchen", "studySearchTip": "Forschungskennungen im indizierten Bestand filtern. Sucht keine Patientennamen und beschafft keine Daten.", "datasetFilter": "Datensatz", "datasetFilterTip": "Studienliste auf einen Datensatz beschränken. Synthetische Demos bleiben von Entwicklungsstudien getrennt.", "allDatasets": "Alle Datensätze", "libraryTip": "Sichtbare indizierte Studien nach Filterung, zugelassene Entwicklungsstudien und synthetische Demos. Versiegelte Fälle erscheinen nie.", "refreshStudies": "Studienbestand aktualisieren", "refreshStudiesTip": "Geschützte lokale Indizes nach Indizierung oder Beschaffung von Entwicklungsstudien neu laden. Lädt keine Daten herunter und liest keine versiegelten Studien.", "optionalDemo": "Optional: eine synthetische Studie ohne Patientendaten ausprobieren.", "libraryReady": "Indizierter Entwicklungsbestand bereit", "split_required": "Vor der Indizierung die Entwicklungs- und versiegelte Aufteilung erstellen.", "not_indexed": "Entwicklungsindex fehlt. Zugelassenen Datensatz in der CLI indizieren, dann aktualisieren.", "libraryUnavailable": "Bestand nicht verfügbar. Lokale Konfiguration und Berechtigungen prüfen, dann aktualisieren.", "visibleStudies": "sichtbar", "developmentStudies": "Entwicklungsstudien", "syntheticStudies": "synthetische Demos", "noMatches": "Keine passenden Studien — Suche leeren oder Datensatz wechseln", "selectStudy": "Passende Studie auswählen", "openSetup": "Lokale Modelle einrichten", "openSetupTip": "Lokale Modellverfügbarkeit, Lizenzprüfung, Downloads und manuelle Diensteinrichtung öffnen. Startet keinen automatischen Download.", "visionInputNote": "Vision-Modelle nutzen vorbereitete Bilder. Landmarken-, Koronal- und Fensteransichten können die tatsächliche Eingabeanzahl erhöhen.", "serviceInputNote": "Dieses Modell nutzt seinen konfigurierten lokalen HTTP-Dienst. Voraussetzungen für Gewichte, Zugang und Eingabedarstellung unter Modelle einrichten prüfen.", "viewerChoose": "Oben eine Entwicklungsstudie wählen, den Bestand aktualisieren oder die optionale synthetische Demo ausprobieren.", "viewerFailureTitle": "Schicht nicht verfügbar", "viewerFailureNote": "Andere Schicht, anderes Darstellungsfenster oder andere Studie wählen. Aus diesem Darstellungsfehler folgt keine Modellvorhersage.", "resultContextTip": "Kennzeichnet abgeschlossene Studie und Modell, angeforderte Quellschicht-Zielanzahl und tatsächlich vorbereitete Bilder. Downloads gehören zu diesem aufgezeichneten Durchlauf.", "previousSettings": "Diese Ergebnisse gehören zu früheren Einstellungen. Für die aktuellen Einstellungen erneut ausführen.", "previousSettingsTip": "Änderungen an Studie, Modell, Vergleichsmodus oder Quellschicht-Zielanzahl ändern keinen abgeschlossenen Durchlauf. Seine Downloads behalten die ursprünglichen Eingaben.", "severity": "Lehrbezogener Schweregrad", "attention": "Allgemeiner Prüfungskontext", "severityTip": "Allgemeine Lehrinformation aus der Projektwissensbasis nur für nutzbare positive Befunde. Keine validierte Bewertung, Diagnose oder Behandlungsempfehlung für diese Studie.", "attentionTip": "Allgemeiner lehrbezogener Prüfungskontext, keine patientenbezogene Frist oder Versorgungsvorgabe. Unbekannte, negative und enthaltene Befunde erhalten keine Zuordnung.", "educationCaution": "Schweregrad und Prüfungskontext sind allgemeine Lehrinformationen, keine Beratung für diese Studie. Evidenz im HTML-Bericht prüfen.", "incidental": "Nebenbefund", "low": "Gering", "moderate": "Mäßig", "high": "Hoch", "critical": "Kritisch", "routine": "Routineprüfung", "soon": "Frühere Prüfung", "urgent": "Dringlicher Kontext", "emergency": "Notfallkontext", "notAvailable": "Nicht verfügbar", "leavingBusy": "Eine lokale Anfrage läuft noch."});
  const findingNames = {"en": {"pulmonary_nodule": "Pulmonary nodule", "pulmonary_mass": "Pulmonary mass", "consolidation": "Consolidation", "ground_glass_opacity": "Ground-glass opacity", "lung_opacity": "Lung opacity (unspecified)", "atelectasis": "Atelectasis", "emphysema": "Emphysema", "fibrosis_interstitial": "Fibrosis / interstitial abnormality", "bronchiectasis": "Bronchiectasis", "cavitation": "Cavitation", "mosaic_attenuation": "Mosaic attenuation", "peribronchial_thickening": "Peribronchial thickening", "interlobular_septal_thickening": "Interlobular septal thickening", "pleural_effusion": "Pleural effusion", "pneumothorax": "Pneumothorax", "pleural_thickening": "Pleural thickening / mass", "lymphadenopathy": "Mediastinal / hilar lymphadenopathy", "mediastinal_mass": "Mediastinal mass", "cardiomegaly": "Cardiomegaly", "pericardial_effusion": "Pericardial effusion", "aortic_abnormality": "Aortic abnormality", "coronary_calcification": "Coronary artery calcification", "arterial_wall_calcification": "Arterial wall calcification", "hiatal_hernia": "Hiatal hernia", "fracture": "Fracture", "osseous_lesion": "Suspicious osseous lesion", "chest_wall_abnormality": "Chest-wall abnormality", "medical_device": "Medical device / material"}, "de": {"pulmonary_nodule": "Lungenrundherd", "pulmonary_mass": "Lungenraumforderung", "consolidation": "Konsolidierung", "ground_glass_opacity": "Milchglastrübung", "lung_opacity": "Unspezifische Lungenverdichtung", "atelectasis": "Atelektase", "emphysema": "Emphysem", "fibrosis_interstitial": "Fibrose / interstitielle Auffälligkeit", "bronchiectasis": "Bronchiektasen", "cavitation": "Kavitation", "mosaic_attenuation": "Mosaikmuster", "peribronchial_thickening": "Peribronchiale Verdickung", "interlobular_septal_thickening": "Interlobuläre Septenverdickung", "pleural_effusion": "Pleuraerguss", "pneumothorax": "Pneumothorax", "pleural_thickening": "Pleuraverdickung / Raumforderung", "lymphadenopathy": "Mediastinale / hiläre Lymphknotenvergrößerung", "mediastinal_mass": "Mediastinale Raumforderung", "cardiomegaly": "Herzvergrößerung", "pericardial_effusion": "Perikarderguss", "aortic_abnormality": "Aortenauffälligkeit", "coronary_calcification": "Koronare Verkalkung", "arterial_wall_calcification": "Arterielle Wandverkalkung", "hiatal_hernia": "Hiatushernie", "fracture": "Fraktur", "osseous_lesion": "Verdächtige Knochenläsion", "chest_wall_abnormality": "Brustwandauffälligkeit", "medical_device": "Medizinisches Gerät / Material"}};
  const $ = (id) => document.getElementById(id);
  const readPreference = (key, allowed, fallback) => { try { const value = localStorage.getItem(key); return allowed.includes(value) ? value : fallback; } catch { return fallback; } };
  let language = readPreference("thoraxbench.language", ["en", "de"], "en");
  let theme = readPreference("thoraxbench.theme", ["light", "dark"], "light");
  let studies = [], models = [], busy = false, pulling = false, initialized = false, output = null, noticeKey = null;
  let pullSnapshot = null, libraries = [], viewerFailed = false, aboutLoaded = false;
  let requestSnapshot = null;
  const viewScroll = {analysis:0,about:0};
  const acknowledgedModels = new Set();
  let requestStarted = null, requestTimer = null, modelStarted = null;
  let comparison = [], comparisonDownload = null, forecastFinished = false;
  let durationHistory = {};
  try { const stored = JSON.parse(localStorage.getItem("thoraxbench.duration-history") || "{}"); if (stored && typeof stored === "object" && !Array.isArray(stored)) durationHistory = stored; } catch { /* Timing estimates work without persistent browser storage. */ }
  function durationKey(id, count) { return `${id}:${count}`; }
  function observedDurations(id, count) { const values = durationHistory[durationKey(id,count)]; return Array.isArray(values) ? values.filter((value) => typeof value === "number" && Number.isFinite(value) && value > 0 && value < 86400).slice(-5) : []; }
  function rememberDuration(id, count, seconds) { if (!Number.isFinite(seconds) || seconds <= 0 || seconds >= 86400) return; durationHistory[durationKey(id,count)] = [...observedDurations(id,count),seconds].slice(-5); save("thoraxbench.duration-history", JSON.stringify(durationHistory)); }
  function estimateFor(id, count) { const previous = observedDurations(id,count); if (previous.length) { const mean = previous.reduce((sum,value) => sum + value,0) / previous.length; return {low:mean * 0.5,high:mean * 2,seed:false}; } return id === "heuristic-hu" ? {low:1,high:60,seed:true} : {low:60,high:900,seed:true}; }
  function renderForecast() {
    if (forecastFinished) { setText("request-forecast", t("forecastDone")); return; }
    const count = Number($("image-count").value), comparing = $("compare-models").checked;
    const entries = busy && comparing && comparison.length ? comparison.filter((entry) => ["waiting","running"].includes(entry.status)) : (comparing ? models.filter((entry) => entry.recommended && entry.available) : [{id:$("model-select").value}]);
    let low = 0, high = 0, seed = false, over = false;
    entries.forEach((entry) => { const range = estimateFor(entry.id,count); const elapsed = busy && requestTimer !== null && requestStarted !== null && (!comparing || (entry.status === "running" && modelStarted !== null)) ? (performance.now() - (comparing ? modelStarted : requestStarted)) / 1000 : 0; low += Math.max(0,range.low - elapsed); high += Math.max(0,range.high - elapsed); seed ||= range.seed; over ||= elapsed > range.high; });
    const range = high >= 120 ? `${Math.ceil(low / 60)}–${Math.ceil(high / 60)}+ min` : `${Math.ceil(low)}–${Math.ceil(high)} s`;
    setText("request-forecast", over ? t("forecastOver") : `${t("forecast")}: ${range} · ${t(seed ? "forecastSeed" : "forecastHistory")}`);
  }
  function updateRequestTimer() { if (requestStarted !== null) setText("request-elapsed", `${((performance.now() - requestStarted) / 1000).toFixed(1)} s`); if (modelStarted !== null) setText("model-elapsed", `${((performance.now() - modelStarted) / 1000).toFixed(1)} s`); renderForecast(); }
  function stopRequestTimer() { forecastFinished = true; updateRequestTimer(); clearInterval(requestTimer); requestTimer = null; }
  function resetRequestTimer() { clearInterval(requestTimer); requestTimer = null; requestStarted = null; modelStarted = null; forecastFinished = false; $("request-timer").hidden = true; setText("request-elapsed", "0.0 s"); }
  function startRequestTimer() { forecastFinished = false; requestStarted = performance.now(); $("request-timer").hidden = false; updateRequestTimer(); requestTimer = setInterval(updateRequestTimer, 100); }
  const t = (key) => words[language][key] || words.en[key] || key;
  const save = (key, value) => { try { localStorage.setItem(key, value); } catch { /* Preferences remain usable when storage is blocked. */ } };
  const setText = (id, value) => { $(id).textContent = value; };
  const tooltip = $("tooltip");
  const TOOLTIP_DELAY_MS = 650;
  let tooltipTarget = null;
  let tooltipDismissed = false;
  let tooltipShowTimer = null, tooltipHideTimer = null;
  const helpDescriptions = new Map();
  function initializeTooltips() {
    if (tooltipTarget && !tooltipTarget.isConnected) hideTooltip();
    document.querySelectorAll("[data-tip]").forEach((element) => {
      const key = element.dataset.tip;
      if (!helpDescriptions.has(key)) { const description = document.createElement("span"); description.id = `help-${key}`; $("help-descriptions").append(description); helpDescriptions.set(key,description); }
      element.setAttribute("aria-describedby", `help-${key}`);
    });
    helpDescriptions.forEach((description,key) => { description.textContent = t(key);
    });
  }
  function positionTooltip(element) {
    tooltip.textContent = t(element.dataset.tip);
    const rect = element.getBoundingClientRect();
    const box = tooltip.getBoundingClientRect();
    const left = Math.max(12, Math.min(rect.left, window.innerWidth - box.width - 12));
    const top = rect.bottom + box.height + 12 < window.innerHeight ? rect.bottom + 8 : Math.max(12, rect.top - box.height - 8);
    tooltip.style.left = `${left}px`; tooltip.style.top = `${top}px`;
  }
  function hideTooltip() { clearTimeout(tooltipHideTimer); clearTimeout(tooltipShowTimer); tooltipShowTimer = null; tooltip.hidden = true; tooltipTarget = null; }
  function showTooltip(element) {
    if (!element || tooltipDismissed || !element.isConnected) return;
    clearTimeout(tooltipHideTimer);
    if (tooltipTarget === element) {
      if (!tooltip.hidden) positionTooltip(element);
      return;
    }
    hideTooltip();
    tooltipTarget = element;
    tooltip.textContent = t(element.dataset.tip);
    tooltipShowTimer = setTimeout(() => {
      tooltipShowTimer = null;
      if (tooltipTarget !== element || tooltipDismissed || !element.isConnected) return;
      tooltip.hidden = false;
      positionTooltip(element);
    }, TOOLTIP_DELAY_MS);
  }
  document.addEventListener("mouseout", (event) => {
    const target = event.target.closest("[data-tip]");
    if (target && target === tooltipTarget && !target.contains(event.relatedTarget)) {
      if (tooltip.hidden) hideTooltip();
      else if (!tooltip.contains(event.relatedTarget) && document.activeElement !== target) tooltipHideTimer = setTimeout(hideTooltip,180);
    }
  });
  tooltip.addEventListener("mouseenter", () => clearTimeout(tooltipHideTimer));
  tooltip.addEventListener("mouseleave", () => { if (document.activeElement?.closest("[data-tip]") !== tooltipTarget) hideTooltip(); });
  document.addEventListener("focusin", (event) => { tooltipDismissed = false; showTooltip(event.target.closest("[data-tip]")); });
  // Real pointer movement starts hover help; layout-only mouseover events must not replace keyboard help.
  document.addEventListener("pointermove", (event) => { if (tooltip.contains(event.target)) { clearTimeout(tooltipHideTimer); return; } tooltipDismissed = false; showTooltip(event.target.closest("[data-tip]")); });
  document.addEventListener("focusout", (event) => { if (event.target.closest("[data-tip]") === tooltipTarget) hideTooltip(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") { tooltipDismissed = true; hideTooltip(); } });
  window.addEventListener("scroll", () => {
    if (!tooltipTarget || (!tooltip.hidden && tooltip.matches(":hover"))) return;
    const focused = document.activeElement?.closest("[data-tip]");
    if (focused === tooltipTarget || tooltipTarget.matches(":hover")) {
      if (!tooltip.hidden) positionTooltip(tooltipTarget);
    } else hideTooltip();
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
    renderStudies(); renderModels(); renderStudyFacts(); renderResult(); renderComparison(); renderSetup(); renderPullStatus(); applyTheme(); renderViewerEmpty(); updateSliceLabels();
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
  function currentStudy() { return $("study-select").value === "" ? null : studies[Number($("study-select").value)] || null; }
  function renderStudies() {
    const previous = $("study-select").value, dataset = $("dataset-filter").value;
    $("dataset-filter").replaceChildren(new Option(t("allDatasets"), ""));
    [...new Set(studies.map((study) => study.dataset))].sort().forEach((name) => $("dataset-filter").add(new Option(name,name)));
    if ([...$("dataset-filter").options].some((option) => option.value === dataset)) $("dataset-filter").value = dataset;
    const query = $("study-search").value.trim().toLocaleLowerCase();
    const visible = studies.map((study,index) => ({study,index})).filter(({study}) => (!$("dataset-filter").value || study.dataset === $("dataset-filter").value) && `${study.dataset} ${study.case_id}`.toLocaleLowerCase().includes(query));
    visible.sort((a,b) => Number(a.study.dataset === "demo") - Number(b.study.dataset === "demo") || a.study.dataset.localeCompare(b.study.dataset) || a.study.case_id.localeCompare(b.study.case_id));
    const select = $("study-select"); select.replaceChildren();
    if (!visible.length) select.add(new Option(studies.length ? t("noMatches") : t("noStudies"),""));
    const groups = new Map();
    visible.forEach(({study,index}) => { if (!groups.has(study.dataset)) { const group = document.createElement("optgroup"); group.label = study.dataset; select.append(group); groups.set(study.dataset,group); } const option = new Option(study.case_id,String(index)); groups.get(study.dataset).append(option); });
    if (visible.some(({index}) => String(index) === previous)) select.value = previous;
    setText("library-counts", `${visible.length} / ${studies.length} ${t("visibleStudies")} · ${studies.filter((study) => study.dataset !== "demo").length} ${t("developmentStudies")} · ${studies.filter((study) => study.dataset === "demo").length} ${t("syntheticStudies")}`);
    $("library-status").replaceChildren();
    libraries.forEach((library) => { const message = document.createElement("p"); message.tabIndex = 0; message.dataset.tip = "refreshStudiesTip"; message.textContent = `${library.dataset}: ${t(library.status === "ready" ? "libraryReady" : library.status === "unavailable" ? "libraryUnavailable" : library.status)} (${library.available_studies ?? 0})`; $("library-status").append(message); });
    initializeTooltips();
  }
  function loadLibrary(data) { const selected = currentStudy(); studies = data.studies || []; libraries = data.libraries || []; renderStudies(); if (selected) { const index = studies.findIndex((study) => study.dataset === selected.dataset && study.case_id === selected.case_id); if (index >= 0 && [...$("study-select").options].some((option) => option.value === String(index))) $("study-select").value = String(index); } renderStudyFacts(); showSlice(true); }
  async function refreshStudies() { loadLibrary(await api("/api/studies")); }
  function filterStudies() { renderStudies(); renderStudyFacts(); showSlice(true); renderResult(); }
  $("study-search").addEventListener("input", filterStudies);
  $("dataset-filter").addEventListener("change", filterStudies);
  $("refresh-studies").addEventListener("click", async () => { try { await refreshStudies(); } catch (error) { notice("failed","error",error.message); } });
  function renderModels() {
    const previous = $("model-select").value || "heuristic-hu";
    $("model-select").replaceChildren();
    models.forEach((model) => { const option = new Option(`${model.id} · ${t(model.available ? "available" : "unavailable")}`, model.id); option.disabled = !model.available; $("model-select").add(option); });
    if (models.some((model) => model.id === previous)) $("model-select").value = previous;
    else if (models.some((model) => model.id === "heuristic-hu")) $("model-select").value = "heuristic-hu";
    renderModelStatus(); renderSetup();
  }
  function renderModelStatus() {
    const model = models.find((entry) => entry.id === $("model-select").value);
    setText("model-status", t(model?.available ? "modelReady" : "modelNotReady"));
    setText("model-input-note", t(model?.adapter === "http_service" ? "serviceInputNote" : model?.adapter === "heuristic" || model?.id === "heuristic-hu" ? "baselineNote" : "visionInputNote"));
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
    ["study-select","study-search","dataset-filter","refresh-studies","model-select","window-select","image-count","create-demo","compare-models"].forEach((id) => { $(id).disabled = busy || pulling; });
    $("slice-slider").disabled = busy || !study;
    const comparing = $("compare-models").checked;
    $("model-select").disabled = busy || pulling || comparing;
    $("run-analysis").disabled = busy || pulling || !study || (comparing ? !models.some((entry) => entry.recommended && entry.available) : !model?.available);
    $("image-count").disabled = busy || pulling || (!comparing && $("model-select").value === "heuristic-hu");
    $("run-analysis").textContent = t(busy ? "running" : comparing ? "compareRun" : "run");
    document.body.classList.toggle("busy", busy);
    $("analysis-page").setAttribute("aria-busy", String(busy));
    $("create-demo").disabled = busy || pulling || !initialized;
    $("refresh-models").disabled = busy || pulling || !initialized;
    document.querySelectorAll("[data-setup-control]").forEach((control) => { control.disabled = busy || pulling || (control.tagName === "BUTTON" && !acknowledgedModels.has(control.dataset.model)); });
    renderResultContext(); renderComparisonContext(); renderForecast();
  }
  function setBusy(value) { busy = value; updateControls(); }
  function showSlice(reset = false) {
    const study = currentStudy();
    viewerFailed = false; renderViewerEmpty();
    if (!study) { $("ct-image").hidden = true; $("viewer-empty").hidden = false; return; }
    $("slice-slider").max = Math.max(0, study.n_slices - 1);
    if (reset) $("slice-slider").value = Math.floor(study.n_slices / 2);
    const index = Number($("slice-slider").value);
    updateSliceLabels();
    $("ct-image").src = `/api/studies/${encodeURIComponent(study.dataset)}/${encodeURIComponent(study.case_id)}/slice/${index}.png?window=${encodeURIComponent($("window-select").value)}`;
    $("ct-image").hidden = false; $("viewer-empty").hidden = true;
  }
  function updateSliceLabels() { const study = currentStudy(); const index = Number($("slice-slider").value); setText("slice-counter", study ? `${index + 1} / ${study.n_slices}` : "— / —"); if (study) $("slice-slider").setAttribute("aria-valuetext", `${t("slice")} ${index + 1} / ${study.n_slices}`); }
  function renderViewerEmpty() { setText("viewer-empty-title", t(viewerFailed ? "viewerFailureTitle" : "viewerEmpty")); setText("viewer-empty-note", t(viewerFailed ? "viewerFailureNote" : "viewerChoose")); }
  async function api(path, body) {
    const response = await fetch(path, body === undefined ? {} : {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`);
    return data;
  }
  function cell(value, tip) { const element = document.createElement("td"); element.textContent = value; if (tip) { element.dataset.tip = tip; element.tabIndex = 0; } return element; }
  function preparedImageCount(result) { const count = result.perf?.n_images; return Number.isInteger(count) && count >= 0 ? String(count) : "—"; }
  function snapshot(study,count,model) { return {dataset:study.dataset,case_id:study.case_id,target:count,model,compare:$("compare-models").checked}; }
  function settingsMatch(recorded) {
    const study = currentStudy();
    return !!study && study.dataset === recorded.dataset && study.case_id === recorded.case_id && Number($("image-count").value) === recorded.target && $("compare-models").checked === recorded.compare && (recorded.compare || $("model-select").value === recorded.model);
  }
  function renderResultContext() {
    if (!output) return;
    const recorded = output.ui_snapshot || {dataset:output.result.dataset || "—",case_id:output.result.case_id || "—",target:"—",model:output.result.model_id};
    setText("result-context", `${t("study")}: ${recorded.dataset} / ${recorded.case_id} · ${t("model")}: ${output.result.model_id} · ${t("imageCount")}: ${recorded.target} · ${t("actualImages")}: ${preparedImageCount(output.result)}`);
    $("previous-settings").hidden = settingsMatch(recorded);
  }
  function renderComparisonContext() {
    const recorded = comparison.find((entry) => entry.output)?.output.ui_snapshot || (comparison.length ? requestSnapshot : null);
    $("comparison-context").hidden = !recorded;
    $("comparison-previous-settings").hidden = !recorded || settingsMatch(recorded);
    if (recorded) setText("comparison-context", `${t("study")}: ${recorded.dataset} / ${recorded.case_id} · ${t("imageCount")}: ${recorded.target}`);
  }
  function findingCell(label) { const element = cell("","findingTip"), name = document.createElement("span"), code = document.createElement("code"); name.textContent = findingNames[language][label] || label; code.textContent = label; code.className = "canonical-label"; element.append(name,code); return element; }
  function educationCell(output,index,finding,key,tip) { const item = output.presentation?.findings?.find((entry) => entry.finding_index === index && entry.label === finding.label); const allowed = key === "severity" ? ["incidental","low","moderate","high","critical"] : ["routine","soon","urgent","emergency"]; return cell(presenceOf(finding) === "present" && item?.status === "present" && allowed.includes(item[key]) ? t(item[key]) : "—",tip); }
  function renderResult() {
    $("results-empty").hidden = !!output; $("results-content").hidden = !output;
    if (!output) return;
    const result = output.result, findings = result.report.abstain || result.raw_error ? [] : result.report.findings || [];
    renderResultContext();
    setText("metric-model", result.model_id);
    setText("metric-images", preparedImageCount(result));
    setText("metric-time", `${Number(result.perf.total_s).toFixed(3)} s`);
    setText("metric-status", t(result.report.abstain || result.raw_error ? "abstained" : "completed"));
    setText("metric-findings", String((result.report.findings || []).length));
    $("findings-body").replaceChildren();
    findings.map((finding,index) => ({finding,index})).sort((a,b) => ({present:0,uncertain:1,absent:2}[presenceOf(a.finding)] - {present:0,uncertain:1,absent:2}[presenceOf(b.finding)])).forEach(({finding,index}) => { const row = document.createElement("tr"); row.append(findingCell(finding.label),cell(t(presenceOf(finding)),"presenceTip"),cell(scoreOf(finding),"scoreTip"),cell(t(finding.laterality || "unknown"),"sideTip"),cell(finding.size_mm == null ? "—" : `${finding.size_mm} mm`,"sizeTip"),educationCell(output,index,finding,"severity","severityTip"),educationCell(output,index,finding,"attention","attentionTip")); $("findings-body").append(row); });
    if (!findings.length) { const row = document.createElement("tr"), message = cell(t(result.report.abstain || result.raw_error ? "noPrediction" : "noFindings"), "resultStatusTip"); message.colSpan = 7; row.append(message); $("findings-body").append(row); }
    setText("report-content", output.markdown);
    [["download-json","json"],["download-report","markdown"],["download-html","html"]].forEach(([id,key]) => { const url = output.downloads[key]; if (url) { $(id).href = url; $(id).setAttribute("aria-disabled","false"); $(id).setAttribute("download",""); } });
    initializeTooltips();
  }
  function clearResult() { resetRequestTimer(); $("batch-status").hidden = true; comparison = []; comparisonDownload = null; renderComparison(); output = null; renderResult(); ["download-json","download-report","download-html"].forEach((id) => { $(id).removeAttribute("href"); $(id).setAttribute("aria-disabled","true"); }); }
  $("language-toggle").addEventListener("click", () => { language = language === "en" ? "de" : "en"; save("thoraxbench.language",language); applyLanguage(); });
  $("theme-toggle").addEventListener("click", () => { theme = theme === "light" ? "dark" : "light"; save("thoraxbench.theme",theme); applyTheme(); });
  $("study-select").addEventListener("change", () => { resetRequestTimer(); $("batch-status").hidden = true; renderComparisonContext(); notice(null); renderStudyFacts(); showSlice(true); renderResult(); });
  $("model-select").addEventListener("change", () => { forecastFinished = false; renderModelStatus(); renderResultContext(); });
  $("compare-models").addEventListener("change", () => { forecastFinished = false; renderComparison(); updateControls(); });
  $("image-count").addEventListener("input", () => { forecastFinished = false; renderForecast(); renderResultContext(); renderComparisonContext(); });
  $("slice-slider").addEventListener("input", () => showSlice());
  $("window-select").addEventListener("change", () => showSlice());
  $("ct-image").addEventListener("load", () => { if (noticeKey?.key === "sliceFailed") notice(null); });
  $("ct-image").addEventListener("error", () => { viewerFailed = true; renderViewerEmpty(); $("ct-image").hidden = true; $("viewer-empty").hidden = false; notice("sliceFailed","error"); });
  $("create-demo").addEventListener("click", async () => {
    setBusy(true); notice("creating");
    try { const data = await api("/api/demo",{}); $("study-search").value = ""; $("dataset-filter").value = ""; loadLibrary(data); const index = studies.findIndex((study) => study.dataset === "demo"); $("study-select").value = String(index >= 0 ? index : 0); clearResult(); renderStudyFacts(); showSlice(true); notice("demoReady"); }
    catch (error) { notice("failed","error",error.message); }
    finally { setBusy(false); }
  });
  function presenceOf(finding) { if (!finding || finding.present == null || finding.confidence == null) return "uncertain"; const score = finding.present ? finding.confidence : 1 - finding.confidence; return score >= 0.5 ? "present" : "absent"; }
  function scoreOf(finding) {
    if (!finding || finding.present == null || finding.confidence == null) return "—";
    return Number(finding.present ? finding.confidence : 1 - finding.confidence).toFixed(2);
  }
  function helpHeading(text, tip) { const heading = document.createElement("th"); heading.textContent = text; heading.dataset.tip = tip; heading.tabIndex = 0; return heading; }
  function renderComparison() {
    renderComparisonContext();
    $("comparison-panel").hidden = !$("compare-models").checked && !comparison.length;
    const entries = comparison.length ? comparison : models.filter((entry) => entry.recommended).map((entry) => ({id:entry.id,status:entry.available ? "waiting" : "skipped"}));
    $("comparison-body").replaceChildren();
    entries.forEach((entry) => {
      const row = document.createElement("tr"); row.dataset.model = entry.id;
      row.append(cell(entry.id,"resultModelTip"),cell(t(entry.status),"resultStatusTip"),cell(entry.output ? preparedImageCount(entry.output.result) : "—","actualImagesTip"),cell(entry.output ? `${Number(entry.output.result.perf.total_s).toFixed(3)} s` : "—","timingTip"),cell(entry.wall == null ? "—" : `${entry.wall.toFixed(1)} s`,"wallTip"));
      const actions = cell(entry.detail || "", "resultStatusTip");
      if (entry.output) {
        const inspect = document.createElement("button"); inspect.type = "button"; inspect.className = "button secondary"; inspect.dataset.tip = "inspectTip"; inspect.textContent = t("inspect"); inspect.addEventListener("click", () => { output = entry.output; renderResult(); $("results-heading").scrollIntoView({block:"start"}); }); actions.append(inspect);
        [["json","downloadJson","jsonTip"],["markdown","downloadReport","reportTip"],["html","downloadHtml","htmlTip"]].forEach(([kind,label,tip]) => { if (!entry.output.downloads[kind]) return; const link = document.createElement("a"); link.href = entry.output.downloads[kind]; link.download = ""; link.textContent = t(label); link.dataset.tip = tip; link.className = "button secondary"; actions.append(link); });
      }
      row.append(actions); $("comparison-body").append(row);
    });
    const head = $("comparison-findings-head"), body = $("comparison-findings-body"); head.replaceChildren(helpHeading(t("finding"),"findingTip")); body.replaceChildren();
    entries.forEach((entry) => head.append(helpHeading(entry.id,"resultModelTip")));
    const labels = [...new Set(entries.flatMap((entry) => (entry.output?.result.report.findings || []).map((finding) => finding.label)))];
    labels.forEach((label) => { const row = document.createElement("tr"); row.append(findingCell(label)); entries.forEach((entry) => { const report = entry.output?.result.report; const matches = report?.findings.filter((value) => value.label === label) || []; const text = !report || report.abstain || entry.output.result.raw_error ? t(entry.status === "completed" ? "noPrediction" : entry.status) : matches.length ? matches.map((finding) => `${t(presenceOf(finding))} · ${scoreOf(finding)}`).join("; ") : t("noPrediction"); row.append(cell(text,"scoresTip")); }); body.append(row); });
    $("comparison-single").hidden = comparison.filter((entry) => entry.output).length !== 1;
    $("comparison-download").hidden = !comparisonDownload;
    if (comparisonDownload) $("comparison-download").href = comparisonDownload;
    initializeTooltips();
  }
  async function runComparison(study, count) {
    comparison = models.filter((entry) => entry.recommended).map((entry) => ({id:entry.id,status:entry.available ? "waiting" : "skipped"}));
    renderComparison();
    for (const [index, entry] of comparison.entries()) {
      if (entry.status === "skipped") continue;
      entry.status = "running"; modelStarted = performance.now();
      setText("batch-progress", `${index + 1} / ${comparison.length} · ${entry.id}`); setText("model-elapsed", "0.0 s"); renderComparison();
      try {
        entry.output = await api("/api/analyze",{dataset:study.dataset,case_id:study.case_id,model_id:entry.id,n_images:count});
        entry.output.ui_snapshot = snapshot(study,count,entry.id);
        entry.status = entry.output.result.report.abstain || entry.output.result.raw_error ? "abstained" : "completed";
        entry.detail = entry.output.result.raw_error || entry.output.result.report.uncertainty || "";
        if (!entry.output.result.raw_error) rememberDuration(entry.id,count,(performance.now() - modelStarted) / 1000);
        output = entry.output; renderResult();
      } catch (error) { entry.status = "error"; entry.detail = error.message; }
      finally { entry.wall = (performance.now() - modelStarted) / 1000; modelStarted = null; renderComparison(); }
    }
    setText("batch-progress", `${comparison.length} / ${comparison.length}`); setText("model-elapsed", "—");
    const results = comparison.filter((entry) => entry.output?.id);
    if (results.length) {
      try { const exported = await api("/api/compare", {result_ids:results.map((entry) => entry.output.id),omissions:comparison.filter((entry) => ["skipped","error"].includes(entry.status)).map((entry) => ({model_id:entry.id,status:entry.status,detail:(entry.detail || t("unavailable")).slice(0,500)}))}); comparisonDownload = exported.downloads.html; renderComparison(); }
      catch (error) { notice("comparisonExportFailed","warning",error.message); return; }
    }
    notice("comparisonDone", comparison.some((entry) => ["error","abstained"].includes(entry.status)) ? "warning" : "");
  }
  $("run-analysis").addEventListener("click", async () => {
    const study = currentStudy(), count = Number($("image-count").value);
    if (!Number.isInteger(count) || count < 1 || count > 16) { notice("invalidImages","error"); return; }
    if (!study) return;
    clearResult(); requestSnapshot = snapshot(study,count,$("model-select").value); setBusy(true); startRequestTimer(); notice("running");
    $("batch-status").hidden = !$("compare-models").checked;
    try {
      if ($("compare-models").checked) await runComparison(study, count);
      else { output = await api("/api/analyze",{dataset:study.dataset,case_id:study.case_id,model_id:$("model-select").value,n_images:count}); output.ui_snapshot = requestSnapshot; if (!output.result.raw_error) rememberDuration(output.result.model_id,count,(performance.now() - requestStarted) / 1000); renderResult(); notice(output.result.report.abstain || output.result.raw_error ? "abstainNotice" : "complete", output.result.report.abstain || output.result.raw_error ? "warning" : ""); }
    } catch (error) { notice("failed","error",error.message); }
    finally { stopRequestTimer(); setBusy(false); }
  });
  function renderSetup() {
    $("model-setup-body").replaceChildren();
    models.forEach((model, index) => {
      const row = document.createElement("tr"); row.dataset.setupModel = model.id; row.tabIndex = -1; row.dataset.tip = "setupTip";
      row.append(cell(model.id,"resultModelTip"),cell(t(model.available ? "available" : "unavailable"),"availabilityTip"));
      const setup = cell("", "setupTip"); setup.append(document.createTextNode(`${model.license || t("unknown")} · ${t(model.available ? "setupAvailable" : model.adapter === "http_service" ? "setupService" : model.adapter === "heuristic" ? "setupBaseline" : "setupOllama")}`));
      if ((model.terms_url || model.source_url) && /^https?:\/\//.test(model.terms_url || model.source_url)) { const link = document.createElement("a"); link.href = model.terms_url || model.source_url; link.textContent = t(model.terms_url ? "terms" : "sourceTerms"); link.dataset.tip = "termsTip"; link.target = "_blank"; link.rel = "noopener noreferrer"; link.className = "setup-terms"; setup.append(link); }
      const metadata = document.createElement("details"), summary = document.createElement("summary"), description = document.createElement("pre"); summary.textContent = t("setupMetadata"); summary.dataset.tip = "setupMetadataTip"; description.textContent = [`configs/models/${model.id}.yaml`,model.tag || "",model.notes || "",...(model.setup_steps || [])].filter(Boolean).join("\n"); metadata.append(summary,description); setup.append(metadata);
      if (!model.available && model.download_supported) {
        const controls = document.createElement("div"), checkbox = document.createElement("input"), label = document.createElement("label"), button = document.createElement("button"); controls.className = "setup-download"; checkbox.type = "checkbox"; checkbox.id = `model-terms-${index}`; checkbox.dataset.setupControl = ""; checkbox.dataset.model = model.id; checkbox.dataset.tip = "termsAckTip"; checkbox.checked = acknowledgedModels.has(model.id); label.htmlFor = checkbox.id; label.tabIndex = 0; label.dataset.tip = "termsAckTip"; label.textContent = t("termsAck"); button.type = "button"; button.dataset.setupControl = ""; button.dataset.model = model.id; button.dataset.tip = "downloadModelTip"; button.textContent = t("downloadModel"); button.className = "button secondary"; checkbox.addEventListener("change", () => { if (checkbox.checked) acknowledgedModels.add(model.id); else acknowledgedModels.delete(model.id); updateControls(); }); button.addEventListener("click", () => startPull(model.id)); controls.append(checkbox,label,button); setup.append(controls);
      }
      row.append(setup); $("model-setup-body").append(row);
    });
    initializeTooltips(); updateControls();
  }
  function renderPullStatus() {
    $("pull-progress").hidden = !pullSnapshot;
    if (!pullSnapshot) return;
    const snapshot = pullSnapshot, statusKey = {queued:"queued",running:"downloadRunning",completed:"downloadCompleted",error:"downloadFailed"}[snapshot.status] || "unknown";
    const bytes = typeof snapshot.completed === "number" && typeof snapshot.total === "number" ? ` · ${t("layerBytes")}: ${snapshot.completed.toLocaleString(language)} / ${snapshot.total.toLocaleString(language)}` : "";
    $("pull-progress").textContent = `${t("downloadProgress")}: ${snapshot.model_id} · ${t(statusKey)}${bytes}${snapshot.detail ? ` · ${snapshot.detail}` : ""}`;
  }
  async function refreshModels() { const data = await api("/api/models"); models = data.models; renderModels(); renderComparison(); }
  async function pollPull(snapshot) {
    pullSnapshot = snapshot; renderPullStatus();
    if (["completed","error"].includes(snapshot.status)) { pulling = false; acknowledgedModels.delete(snapshot.model_id); renderSetup(); updateControls(); if (snapshot.status === "completed") { try { await refreshModels(); } catch (error) { notice("failed","error",error.message); } } return; }
    setTimeout(async () => { try { await pollPull(await api(`/api/model-pulls/${encodeURIComponent(snapshot.id)}`)); } catch (error) { pulling = false; pullSnapshot = {...snapshot,status:"error",detail:error.message,completed:null,total:null}; renderPullStatus(); updateControls(); } },1000);
  }
  async function startPull(modelId) {
    if (busy || pulling || !acknowledgedModels.has(modelId)) return;
    pulling = true; updateControls();
    try { await pollPull(await api(`/api/models/${encodeURIComponent(modelId)}/pull`,{terms_acknowledged:true})); }
    catch (error) { pulling = false; pullSnapshot = {model_id:modelId,status:"error",detail:error.message}; renderPullStatus(); updateControls(); }
  }
  $("open-model-setup").addEventListener("click", () => { $("model-setup").open = true; $("model-setup").scrollIntoView({block:"start"}); const selected = models.find((model) => model.id === $("model-select").value); const target = selected && selected.id !== "heuristic-hu" ? selected : models.find((model) => !model.available); const row = target ? [...$("model-setup-body").children].find((entry) => entry.dataset.setupModel === target.id) : null; (row || $("model-setup").querySelector("summary")).focus(); if (row) row.scrollIntoView({block:"center"}); });
  $("refresh-models").addEventListener("click", async () => { try { await refreshModels(); } catch (error) { notice("failed","error",error.message); } });
  async function loadAbout() {
    const about = await api("/api/about");
    setText("about-author", about.author); setText("about-version", about.version); setText("about-license", about.license);
    if (about.email) { const link = document.createElement("a"); link.href = `mailto:${about.email}`; link.textContent = about.author; link.dataset.tip = "authorTip"; $("about-author").replaceChildren(link); }
    $("libraries-body").replaceChildren();
    (about.libraries || []).forEach((library) => { const row = document.createElement("tr"); row.append(cell(library.name,"libraryTip"),cell(library.version,"versionTip"),cell(library.license,"licenseTip")); $("libraries-body").append(row); });
    initializeTooltips();
  }
  async function navigate(path, push = false) {
    viewScroll[$("about-page").hidden ? "analysis" : "about"] = window.scrollY;
    if (push && location.pathname !== path) history.pushState({},"",path);
    const about = path === "/about";
    $("analysis-page").hidden = about; $("about-page").hidden = !about;
    ["nav-analysis","nav-about"].forEach((id) => { const active = id === (about ? "nav-about" : "nav-analysis"); $(id).classList.toggle("active",active); if (active) $(id).setAttribute("aria-current","page"); else $(id).removeAttribute("aria-current"); });
    setText("page-crumb",t(about ? "about" : "analysis")); hideTooltip();
    window.scrollTo(0,viewScroll[about ? "about" : "analysis"]);
    if (about && !aboutLoaded) { try { await loadAbout(); aboutLoaded = true; $("about-load-error").hidden = true; } catch (error) { $("about-load-error").hidden = false; setText("about-load-error", `${t("failed")} ${error.message}`); } }
  }
  document.querySelectorAll(".brand,#nav-analysis,#nav-about").forEach((link) => link.addEventListener("click", (event) => { if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return; event.preventDefault(); navigate(new URL(link.href).pathname,true); }));
  window.addEventListener("popstate", () => navigate(location.pathname));
  window.addEventListener("beforeunload", (event) => { if (busy || pulling) { event.preventDefault(); event.returnValue = ""; } });
  initializeTooltips(); applyLanguage(); navigate(location.pathname);
  Promise.all([api("/api/studies"),api("/api/models")]).then(([studyData,modelData]) => { initialized = true; models = modelData.models; loadLibrary(studyData); renderModels(); renderComparison(); }).catch((error) => { initialized = true; updateControls(); notice("failed","error",error.message); });
})();
