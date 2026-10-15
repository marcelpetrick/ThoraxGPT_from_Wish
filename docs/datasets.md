# ThoraxBench Local — dataset license research & pilot acquisition notes

Verified 2026-10-15 against the official pages (TCIA collection pages + NBIA `getSeries` LicenseName/LicenseURI fields; HF dataset cards + HF API; medRxiv API for MosMedData). Machine-readable registry: `configs/datasets/*.yaml` (one entry per source, with the license decision as `status`).

> Research use only. This self-made experimental tool is not professional medical advice.
> Findings may be incorrect, incomplete or misleading. Do not use outputs for diagnosis or
> treatment decisions.

## Before using these notes

The tables record source research as of 2026-10-15. Suggested statuses are research notes;
`configs/datasets/*.yaml` is the machine-readable policy source. Do not infer approval
from a source URL, another collection's terms or an old table entry.

1. Run `uv run thoraxbench datasets` from the repository root.
2. Inspect the intended dataset's registry entry.
3. Verify its specific current terms before any acquisition.
4. Check free space with `df -h .` and usage with `du -sh data`.
5. Use the maintained split procedure before indexing an approved downloaded cohort.

   ```bash
   uv run thoraxbench split lidc_idri
   ```

6. Check the frozen development/holdout counts.
7. Index a permitted development case.

   ```bash
   uv run thoraxbench index lidc_idri --limit 1
   ```

**Checkpoint:** a split already present must refuse replacement. Keep it. The index contains
only permitted development cases. Never read sealed images or sealed IDs for these checks.

**Recovery:** if approval, access, space or the split is missing, stop that workflow and
record the unmet prerequisite. Do not bypass the license gate or split guard.
`thoraxbench acquire` enforces the configured 10 GB budget (`THORAXBENCH_DATA_BUDGET_GB`)
for its own downloads only. The budget is not a complete write quota for demo/analysis
routes; inspect actual storage usage.

## Acquire an approved dataset

`thoraxbench acquire` downloads one approved TCIA collection through the public NBIA REST
API into `data/raw/<id>/`. It refuses the run when a gate fails:

* the registry status is not `approved*`;
* the registry entry has no `acquisition.nbia_collection` or no `license_url`;
* any series reports another collection or another license URI than the registry entry;
* a patient split already exists and the plan would add new patients;
* the pending bytes plus one ZIP in flight exceed the remaining data budget.

Prerequisites:

* Network access to `services.cancerimagingarchive.net` and `www.cancerimagingarchive.net`.
* A registry entry with `status: approved*`, a verified `license_url`, and a verified
  `acquisition.nbia_collection` (NBIA name, for example `NSCLC Radiogenomics` with a space).
  Optional: `acquisition.label_files` (TCIA upload file names) and, for LIDC-IDRI,
  `acquisition.lidc_xml_archive`.
* For a new cohort: no split exists yet for that dataset.

Steps (working directory: repository root; replace `<id>` with the registry id):

1. Find the dataset id and its status.

   ```bash
   uv run thoraxbench datasets
   ```

2. Show the plan and the budget verdict. A new selection needs a patient count.

   ```bash
   uv run thoraxbench acquire <id> --dry-run --patients 20
   ```

3. Read the plan lines: series counts per state, estimate, `data/` usage and `fits`.
4. Start the acquisition with the same options.

   ```bash
   uv run thoraxbench acquire <id> --patients 20
   ```

5. Re-run the command without `--patients` to resume. Complete series are skipped.
6. Re-hash the stored files against their SHA-256 entries. After a split exists, only
   development patients are opened and hashed; sealed patients are only checked for
   missing listed files.

   ```bash
   uv run thoraxbench acquire <id> --verify
   ```

7. Freeze the split before any indexing (see *Before using these notes*).

**Checkpoint:** exit code 0. `data/raw/<id>/` holds `_selection.json` (frozen plan),
`_sha256.txt`, `_acquisition.json`, `_LICENSE_SNAPSHOT.txt`, `_api_log.jsonl` and
`<PatientID>/<SeriesInstanceUID>/*.dcm`. `manifests/datasets/<id>.json` is byte-identical
to `_acquisition.json` and contains IDs, counts and hashes only.

**Recovery:**

* Exit code 2 (`Acquisition refused`): fix the registry entry or the plan. Never edit the
  status or license to pass the gate without a new terms review.
* `REFUSED: exceeds the data budget`: lower `--patients` for a new selection or free space.
* `exists but is incomplete`: raw data is immutable. Remove only that series directory and
  re-run.
* `SHA-256 mismatch` or `missing listed file`: the manifests stay unchanged. Restore the
  file or remove the series directory and re-run.
* Network errors: re-run later. In-flight files under `.partial/` are discarded.

The selection of an existing `_selection.json` is frozen and reused; `--patients`,
`--modality` and `--seed` then have no effect. The pilot datasets `lidc_idri` and
`nsclc_radiogenomics` have frozen selections and frozen splits:
`uv run thoraxbench acquire lidc_idri --dry-run` reports 60 complete series. A new selection takes
whole patients in a seeded order (`--seed`, default 20261015) with the requested
`--modality` values (default CT). It uses no labels or findings.

## Summary table

| id | license | access | commercial | redistribution | size/patient | labels | suggested status |
|---|---|---|---|---|---|---|---|
| ct_rate | CC-BY-NC-SA-4.0 | gated (HF login + accept terms + share contact info; HF API gated='auto') | no (without prior permission, contact@forithmus.com) | no | ~0.4 GB per NIfTI volume (21.3 TB / 50,188 volumes incl. reconstructions; 25,692 scans, 21,304 patients) | free-text radiology reports; 18 multi-abnormality labels (report-derived); metadata; VQA pairs (CT-CHAT); official train/validation split | approved_noncommercial (gated; documented only, not downloaded) |
| lidc_idri | CC-BY-3.0 | public (no registration) | yes | yes, with attribution (CC BY 3.0) + TCIA policy (DACs mirroring must link back to TCIA policy) | ~130 MB (133.15 GB / 1,010 pts; CT series median 107 MB, range 34-402 MB) | 4-reader nodule markup XML (nodule >=3 mm contours + 9 characteristics incl. malignancy 1-5; nodule <3 mm centroids; non-nodule >=3 mm centroids); per-patient nodule counts xlsx; patient-level diagnosis for a subset (tcia-diagnosis-data-2012-04-20.xls) | approved |
| radgenome_chestct | CC-BY-4.0 (metadata tag) BUT card terms copied from CT-RATE: research/educational only, no commercial exploitation, no redistribution | HF API currently reports gated=False (2026-10-15), but card carries extra_gated_prompt terms; images are CT-RATE volumes (gated) -- only masks/reports here | no (per card terms) | no (per card terms) | 1.32 TB total (masks + parquet reports), CT volumes come from CT-RATE | 197-class organ/region segmentation masks; 665K sentence-level grounded reports; 1.3M grounded VQA pairs | pending_terms_review (license tag vs. terms conflict) |
| nsclc_radiogenomics | CC-BY-3.0 | public (no registration) | yes | yes, with attribution | ~465 MB (98 GB / 211 pts incl. PET); CT series median ~120 MB | DICOM-SEG tumor segmentation (144 pts, R01 cohort); AIM semantic annotations; clinical: histology, stage, smoking, survival/recurrence; EGFR/KRAS/ALK mutation status; (RNA-seq at GEO GSE103584) | approved |
| nsclc_radiomics | CC-BY-NC-3.0 | public (no registration) | no | yes, non-commercial, with attribution | ~85 MB (35.78 GB / 422 pts) | GTV-1 + organs-at-risk RTSTRUCT/SEG; clinical CSV: histology, TNM stage, survival | approved_noncommercial |
| mosmeddata_covid19_1110 | CC-BY-NC-ND-3.0 | public per paper; official host mosmed.ai unreachable from here (connection reset 2026-10-15) -- re-verify terms on host before ingest | no | verbatim only, non-commercial, attribution | unverified (1,110 studies; NIfTI; reportedly only every 10th slice kept) | CT-0..CT-4 severity category (CT-0 = no COVID findings: normal/negatives); binary GGO/consolidation masks for 50 studies | approved_eval_only (pending host re-verification) |
| deeplesion | UNVERIFIED (secondary sources claim CC-BY-NC-SA-4.0 or 'other'; official Box link returned HTTP 404 on 2026-10-15) | public (historically NIH Box, no login); currently unreachable | unverified (likely no) | unverified | ~221 GB total key slices +/- context (32,120 slices / 4,427 pts); not volumetric, multi-region (not thorax-only) | RECIST-diameter bounding boxes for 32,735 lesions; coarse lesion type (lung, mediastinum, liver, ...) | candidate / license-review-required (keep) |
| nlst | CC-BY-4.0 | public (images + publicly distributable clinical subset); full clinical data via NCI CDAS (application) | yes | yes, attribution | ~450 MB (11.92 TB / 26,254 pts, multiple screening rounds/recons) | public clinical subset (package-nlst-780.2021-05-28.zip): screening abnormalities incl. non-nodule findings, lung cancer diagnosis/follow-up | approved (candidate) |
| midrc_ricord_1b | CC-BY-NC-4.0 | public (no registration) | no | yes, non-commercial, attribution | ~74 MB (8.67 GB / 117 pts) | COVID-negative status; clinical/demographic xlsx | approved_noncommercial |
| midrc_ricord_1a | CC-BY-NC-4.0 | public (no registration) | no | yes, non-commercial, attribution | ~106 MB (11.7 GB / 110 pts) | expert per-slice segmentation/labels of COVID-related opacities (MD.ai JSON); study-level classification (typical/indeterminate/atypical/negative); clinical xlsx | approved_noncommercial |
| covid_19_ar | CC-BY-4.0 | public (no registration) | yes | yes, attribution | ~160 MB CT (16.7 GB CT / 105 pts; plus CR/DX) | RT-PCR COVID-19 positive (all); clinical correlates xlsx: admission, ventilation, mortality | approved |
| covid_19_ny_sbu | CC-BY-4.0 | public (no registration) | yes | yes, attribution | ~210 MB CT (292.7 GB CT / 1,384 pts; mostly CR/DX) | COVID-19 positive; rich EHR-derived clinical CSV (outcomes, comorbidities) | approved (candidate) |
| ct_images_in_covid_19 | CC-BY-4.0 | public (no registration) | yes | yes, attribution | ~22 MB (14.71 GB / 661 pts, NIfTI) | RT-PCR COVID-19 positive (all) | approved (candidate) |
| rider_lung_ct | CC-BY-4.0 (images, v3 2024); lesion-notes XLS listed as CC-BY-3.0 | public (no registration) | yes | yes, attribution | ~1.3 GB (43 GB / 32 pts, many recons) | lesion SEG / measurements (test-retest) | approved (candidate) |
| lctsc | CC-BY-3.0 | public (no registration) | yes | yes, attribution | ~83 MB (5.0 GB / 60 pts) | organ-at-risk RTSTRUCT (lungs, heart, esophagus, spinal cord) | approved (candidate) |
| lung_pet_ct_dx | CC-BY-4.0 | public (no registration) | yes | yes, attribution | ~350 MB (123 GB CT / 355 pts) | tumor bounding boxes (PASCAL-VOC XML); histology: adenocarcinoma/small-cell/large-cell/squamous | approved (candidate) |

## Per-dataset details

### CT-RATE (`ct_rate`)

- URL: https://huggingface.co/datasets/ibrahimhamamci/CT-RATE
- DOI: None
- Provider: Hamamci et al. / Forithmus (Hugging Face)
- License: CC-BY-NC-SA-4.0
- Access: gated (HF login + accept terms + share contact info; HF API gated='auto')
- Redistribution: no; commercial: no (without prior permission, contact@forithmus.com); derivatives: share-alike (NC-SA) + terms restrict sharing derived data
- Download: huggingface_hub snapshot_download / hf CLI with HF_TOKEN after accepting terms (NOT possible here: no token)
- Format: NIfTI (.nii.gz) + CSV metadata; size: ~0.4 GB per NIfTI volume (21.3 TB / 50,188 volumes incl. reconstructions; 25,692 scans, 21,304 patients)
- Labels: free-text radiology reports; 18 multi-abnormality labels (report-derived); metadata; VQA pairs (CT-CHAT); official train/validation split
- license_extra: HF gated terms: academic/research/educational use only; commercial exploitation without prior permission forbidden; redistribution of the dataset or any portion not allowed; no re-identification
- Citation: Hamamci, I.E., Er, S., Wang, C., Almas, F., Simsek, A.G., Esirgun, S.N., Dogan, I., Durugol, O.F., Hou, B., Shit, S., et al. Generalist foundation models from a multimodal dataset for 3D computed tomography. Nature Biomedical Engineering (2026). (also arXiv:2403.17834)
- Verified from: HF dataset card, HF API /api/datasets/ibrahimhamamci/CT-RATE (cardData.license, gated, extra_gated_prompt)

### LIDC-IDRI (`lidc_idri`)

- URL: https://www.cancerimagingarchive.net/collection/lidc-idri/
- DOI: 10.7937/K9/TCIA.2015.LO9QL9SX
- Provider: The Cancer Imaging Archive (TCIA), NCI
- License: CC-BY-3.0 (https://creativecommons.org/licenses/by/3.0/)
- Access: public (no registration)
- Redistribution: yes, with attribution (CC BY 3.0) + TCIA policy (DACs mirroring must link back to TCIA policy); commercial: yes; derivatives: yes
- Download: TCIA NBIA REST API v1 (getSeries / getSeriesSize / getImage?SeriesInstanceUID=), or TCIA Data Retriever with the .tcia manifest; no login
- Format: DICOM CT (+ a few CR/DX) ; XML reader annotations; size: ~130 MB (133.15 GB / 1,010 pts; CT series median 107 MB, range 34-402 MB)
- Labels: 4-reader nodule markup XML (nodule >=3 mm contours + 9 characteristics incl. malignancy 1-5; nodule <3 mm centroids; non-nodule >=3 mm centroids); per-patient nodule counts xlsx; patient-level diagnosis for a subset (tcia-diagnosis-data-2012-04-20.xls)
- source_version: Version 4 (2020-09-21)
- Citation: Armato III, S. G., McLennan, G., Bidaut, L., McNitt-Gray, M. F., Meyer, C. R., Reeves, A. P., Zhao, B., Aberle, D. R., Henschke, C. I., Hoffman, E. A., Kazerooni, E. A., MacMahon, H., Van Beek, E. J. R., Yankelevitz, D., et al. (2015). Data From LIDC-IDRI [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/K9/TCIA.2015.LO9QL9SX ; plus publication Armato et al., Med Phys 38(2):915-931 (2011) https://doi.org/10.1118/1.3528204 ; plus acknowledgement: 'The authors acknowledge the National Cancer Institute and the Foundation for the National Institutes of Health, and their critical role in the creation of the free publicly available LIDC/IDRI Database used in this study.'
- Verified from: collection page, NBIA getSeries LicenseName/LicenseURI fields

### RadGenome-ChestCT (`radgenome_chestct`)

- URL: https://huggingface.co/datasets/RadGenome/RadGenome-ChestCT
- DOI: 10.57967/hf/5331
- Provider: RadGenome team (Hugging Face)
- License: CC-BY-4.0 (metadata tag) BUT card terms copied from CT-RATE: research/educational only, no commercial exploitation, no redistribution
- Access: HF API currently reports gated=False (2026-10-15), but card carries extra_gated_prompt terms; images are CT-RATE volumes (gated) -- only masks/reports here
- Redistribution: no (per card terms); commercial: no (per card terms); derivatives: unclear -> treat as research-only
- Download: huggingface_hub (needs CT-RATE volumes separately, which are gated); not downloaded here
- Format: NIfTI segmentation masks + parquet/JSON grounded reports & VQA; size: 1.32 TB total (masks + parquet reports), CT volumes come from CT-RATE
- Labels: 197-class organ/region segmentation masks; 665K sentence-level grounded reports; 1.3M grounded VQA pairs
- Citation: Zhang, X., Wu, C., Zhao, Z., Lei, J., Zhang, Y., Wang, Y., Xie, W. RadGenome-Chest CT: A Grounded Vision-Language Dataset for Chest CT Analysis. arXiv:2404.16754 (2024); and CT-CLIP arXiv:2403.17834
- Verified from: HF dataset card README.md, HF API (gated=False, license=cc-by-4.0, extra_gated_prompt)

### NSCLC Radiogenomics (`nsclc_radiogenomics`)

- URL: https://www.cancerimagingarchive.net/collection/nsclc-radiogenomics/
- DOI: 10.7937/K9/TCIA.2017.7hs46erv
- Provider: The Cancer Imaging Archive (TCIA), NCI
- License: CC-BY-3.0 (https://creativecommons.org/licenses/by/3.0/)
- Access: public (no registration)
- Redistribution: yes, with attribution; commercial: yes; derivatives: yes
- Download: TCIA NBIA REST API v1 (getSeries / getSeriesSize / getImage?SeriesInstanceUID=), or TCIA Data Retriever with the .tcia manifest; no login
- Format: DICOM CT, PET, DICOM-SEG; size: ~465 MB (98 GB / 211 pts incl. PET); CT series median ~120 MB
- Labels: DICOM-SEG tumor segmentation (144 pts, R01 cohort); AIM semantic annotations; clinical: histology, stage, smoking, survival/recurrence; EGFR/KRAS/ALK mutation status; (RNA-seq at GEO GSE103584)
- source_version: Version 4 (2021-06-01)
- nbia_collection_name: NSCLC Radiogenomics (space, not dash)
- Citation: Bakr, S., Gevaert, O., Echegaray, S., Ayers, K., Zhou, M., Shafiq, M., Zheng, H., Zhang, W., Leung, A., Kadoch, M., Shrager, J., Quon, A., Rubin, D., Plevritis, S., & Napel, S. (2017). Data for NSCLC Radiogenomics (Version 4) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/K9/TCIA.2017.7hs46erv ; publication: Bakr et al., Sci Data 5:180202 (2018) https://doi.org/10.1038/sdata.2018.202
- Verified from: collection page, NBIA getSeries LicenseName/LicenseURI fields

### NSCLC-Radiomics (Lung1) (`nsclc_radiomics`)

- URL: https://www.cancerimagingarchive.net/collection/nsclc-radiomics/
- DOI: 10.7937/K9/TCIA.2015.PF0M9REI
- Provider: The Cancer Imaging Archive (TCIA), NCI
- License: CC-BY-NC-3.0 (https://creativecommons.org/licenses/by-nc/3.0/)
- Access: public (no registration)
- Redistribution: yes, non-commercial, with attribution; commercial: no; derivatives: yes (NC)
- Download: TCIA NBIA REST API v1 (getSeries / getSeriesSize / getImage?SeriesInstanceUID=), or TCIA Data Retriever with the .tcia manifest; no login
- Format: DICOM CT, RTSTRUCT, SEG; size: ~85 MB (35.78 GB / 422 pts)
- Labels: GTV-1 + organs-at-risk RTSTRUCT/SEG; clinical CSV: histology, TNM stage, survival
- source_version: Version 4 (2020-10-22)
- Citation: Aerts, H. J. W. L., Wee, L., Rios Velazquez, E., Leijenaar, R. T. H., Parmar, C., Grossmann, P., Carvalho, S., Bussink, J., Monshouwer, R., Haibe-Kains, B., Rietveld, D., Hoebers, F., Rietbergen, M. M., Leemans, C. R., Dekker, A., Quackenbush, J., Gillies, R. J., Lambin, P. (2014). Data From NSCLC-Radiomics (version 4) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/K9/TCIA.2015.PF0M9REI
- Verified from: collection page, NBIA getSeries LicenseName/LicenseURI fields

### MosMedData: Chest CT Scans with COVID-19 Related Findings (COVID19_1110) (`mosmeddata_covid19_1110`)

- URL: https://mosmed.ai/datasets/covid19_1110
- DOI: 10.1101/2020.05.20.20100362 (medRxiv preprint); journal version 10.17816/dd46826 (Digital Diagnostics)
- Provider: Research and Practical Clinical Center for Diagnostics and Telemedicine Technologies, Moscow Health Care Dept.
- License: CC-BY-NC-ND-3.0
- Access: public per paper; official host mosmed.ai unreachable from here (connection reset 2026-10-15) -- re-verify terms on host before ingest
- Redistribution: verbatim only, non-commercial, attribution; commercial: no; derivatives: no (ND): do not publish transformed subsets
- Download: direct archive download from mosmed.ai (host unreachable during this session)
- Format: NIfTI; size: unverified (1,110 studies; NIfTI; reportedly only every 10th slice kept)
- Labels: CT-0..CT-4 severity category (CT-0 = no COVID findings: normal/negatives); binary GGO/consolidation masks for 50 studies
- Citation: Morozov, S.P., Andreychenko, A.E., Pavlov, N.A., Vladzymyrskyy, A.V., Ledikhova, N.V., Gombolevskiy, V.A., Blokhin, I.A., Gelezhe, P.B., Gonchar, A.V., Chernina, V.Yu., Babkin, V. (2020). MosMedData: Chest CT Scans With COVID-19 Related Findings Dataset. medRxiv 2020.05.20.20100362. https://doi.org/10.1101/2020.05.20.20100362
- Verified from: medRxiv API abstract (license statement verbatim), Crossref metadata

### DeepLesion (`deeplesion`)

- URL: https://nihcc.app.box.com/v/DeepLesion
- DOI: 10.1117/1.JMI.5.3.036501 (paper)
- Provider: NIH Clinical Center
- License: UNVERIFIED (secondary sources claim CC-BY-NC-SA-4.0 or 'other'; official Box link returned HTTP 404 on 2026-10-15)
- Access: public (historically NIH Box, no login); currently unreachable
- Redistribution: unverified; commercial: unverified (likely no); derivatives: unverified
- Download: NIH Box zip parts (batch_download_zips.py) -- link dead at check time
- Format: 16-bit PNG slices + DL_info.csv; size: ~221 GB total key slices +/- context (32,120 slices / 4,427 pts); not volumetric, multi-region (not thorax-only)
- Labels: RECIST-diameter bounding boxes for 32,735 lesions; coarse lesion type (lung, mediastinum, liver, ...)
- Citation: Yan, K., Wang, X., Lu, L., Summers, R.M. (2018). DeepLesion: automated mining of large-scale lesion annotations and universal lesion detection with deep learning. J. Med. Imaging 5(3):036501. https://doi.org/10.1117/1.JMI.5.3.036501
- Verified from: Box URL HTTP 404, web search (secondary only)

### National Lung Screening Trial (NLST) CT (`nlst`)

- URL: https://www.cancerimagingarchive.net/collection/nlst/
- DOI: 10.7937/TCIA.HMQ8-J677
- Provider: The Cancer Imaging Archive (TCIA), NCI
- License: CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/)
- Access: public (images + publicly distributable clinical subset); full clinical data via NCI CDAS (application)
- Redistribution: yes, attribution; commercial: yes; derivatives: yes
- Download: TCIA NBIA REST API v1 (getSeries / getSeriesSize / getImage?SeriesInstanceUID=), or TCIA Data Retriever with the .tcia manifest; no login
- Format: DICOM CT (low-dose screening); size: ~450 MB (11.92 TB / 26,254 pts, multiple screening rounds/recons)
- Labels: public clinical subset (package-nlst-780.2021-05-28.zip): screening abnormalities incl. non-nodule findings, lung cancer diagnosis/follow-up
- negatives_value: HIGH: screening population, majority without cancer; best open CC BY 4.0 source of 'normal'/negative chest CT; recommended for Phase B
- Citation: National Lung Screening Trial Research Team. (2013). Data from the National Lung Screening Trial (NLST) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/TCIA.HMQ8-J677
- Verified from: collection page, NBIA getSeries LicenseName/LicenseURI fields

### MIDRC-RICORD-1B (Chest CT COVID-negative) (`midrc_ricord_1b`)

- URL: https://www.cancerimagingarchive.net/collection/midrc-ricord-1b/
- DOI: 10.7937/31V8-4A40
- Provider: The Cancer Imaging Archive (TCIA), NCI
- License: CC-BY-NC-4.0 (https://creativecommons.org/licenses/by-nc/4.0/)
- Access: public (no registration)
- Redistribution: yes, non-commercial, attribution; commercial: no; derivatives: yes (NC)
- Download: TCIA NBIA REST API v1 (getSeries / getSeriesSize / getImage?SeriesInstanceUID=), or TCIA Data Retriever with the .tcia manifest; no login
- Format: DICOM CT; size: ~74 MB (8.67 GB / 117 pts)
- Labels: COVID-negative status; clinical/demographic xlsx
- negatives_value: HIGH (COVID-negative chest CT, may include other pathology)
- Citation: Tsai, E. B., Simpson, S., Lungren, M. P., et al. (2021). Medical Imaging Data Resource Center (MIDRC) - RSNA International COVID-19 Open Radiology Database (RICORD) Release 1b - Chest CT Covid- (MIDRC-RICORD-1B) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/31V8-4A40
- Verified from: collection page, NBIA getSeries LicenseName/LicenseURI fields

### MIDRC-RICORD-1A (Chest CT COVID-positive, annotated) (`midrc_ricord_1a`)

- URL: https://www.cancerimagingarchive.net/collection/midrc-ricord-1a/
- DOI: 10.7937/VTW4-X588
- Provider: The Cancer Imaging Archive (TCIA), NCI
- License: CC-BY-NC-4.0 (https://creativecommons.org/licenses/by-nc/4.0/)
- Access: public (no registration)
- Redistribution: yes, non-commercial, attribution; commercial: no; derivatives: yes (NC)
- Download: TCIA NBIA REST API v1 (getSeries / getSeriesSize / getImage?SeriesInstanceUID=), or TCIA Data Retriever with the .tcia manifest; no login
- Format: DICOM CT + JSON annotations; size: ~106 MB (11.7 GB / 110 pts)
- Labels: expert per-slice segmentation/labels of COVID-related opacities (MD.ai JSON); study-level classification (typical/indeterminate/atypical/negative); clinical xlsx
- negatives_value: non-nodule abnormality (GGO/consolidation)
- Citation: Tsai, E., Simpson, S., Lungren, M.P., et al. (2020). Data from the Medical Imaging Data Resource Center - RSNA International COVID Radiology Database Release 1a - Chest CT Covid+ (MIDRC-RICORD-1A). The Cancer Imaging Archive. https://doi.org/10.7937/VTW4-X588
- Verified from: collection page, NBIA getSeries LicenseName/LicenseURI fields

### COVID-19-AR (`covid_19_ar`)

- URL: https://www.cancerimagingarchive.net/collection/covid-19-ar/
- DOI: 10.7937/tcia.2020.py71-5978
- Provider: The Cancer Imaging Archive (TCIA), NCI
- License: CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/)
- Access: public (no registration)
- Redistribution: yes, attribution; commercial: yes; derivatives: yes
- Download: TCIA NBIA REST API v1 (getSeries / getSeriesSize / getImage?SeriesInstanceUID=), or TCIA Data Retriever with the .tcia manifest; no login
- Format: DICOM CT, CR, DX; size: ~160 MB CT (16.7 GB CT / 105 pts; plus CR/DX)
- Labels: RT-PCR COVID-19 positive (all); clinical correlates xlsx: admission, ventilation, mortality
- negatives_value: non-nodule abnormality (COVID pneumonia), no negatives
- Citation: Desai, S., Baghal, A., Wongsurawat, T., Al-Shukri, S., Gates, K., Farmer, P., Rutherford, M., Blake, G.D., Nolan, T., Powell, T., Sexton, K., Bennett, W., Prior, F. (2020). Data from Chest Imaging with Clinical and Genomic Correlates Representing a Rural COVID-19 Positive Population [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/tcia.2020.py71-5978
- Verified from: collection page, NBIA getSeries LicenseName/LicenseURI fields

### COVID-19-NY-SBU (`covid_19_ny_sbu`)

- URL: https://www.cancerimagingarchive.net/collection/covid-19-ny-sbu/
- DOI: 10.7937/TCIA.BBAG-2923
- Provider: The Cancer Imaging Archive (TCIA), NCI
- License: CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/)
- Access: public (no registration)
- Redistribution: yes, attribution; commercial: yes; derivatives: yes
- Download: TCIA NBIA REST API v1 (getSeries / getSeriesSize / getImage?SeriesInstanceUID=), or TCIA Data Retriever with the .tcia manifest; no login
- Format: DICOM CT/CR/DX/...; size: ~210 MB CT (292.7 GB CT / 1,384 pts; mostly CR/DX)
- Labels: COVID-19 positive; rich EHR-derived clinical CSV (outcomes, comorbidities)
- negatives_value: non-nodule abnormality
- Citation: Saltz, J., Saltz, M., Prasanna, P., Moffitt, R., Hajagos, J., Bremer, E., Balsamo, J., & Kurc, T. (2021). Stony Brook University COVID-19 Positive Cases [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/TCIA.BBAG-2923
- Verified from: collection page, NBIA getSeries LicenseName/LicenseURI fields

### CT Images in COVID-19 (`ct_images_in_covid_19`)

- URL: https://www.cancerimagingarchive.net/collection/ct-images-in-covid-19/
- DOI: 10.7937/TCIA.2020.GQRY-NC81
- Provider: The Cancer Imaging Archive (TCIA), NCI
- License: CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/)
- Access: public (no registration)
- Redistribution: yes, attribution; commercial: yes; derivatives: yes
- Download: IBM Aspera (faspex) package -- NOT in NBIA (getSeries returns nothing)
- Format: NIfTI (unenhanced chest CT); size: ~22 MB (14.71 GB / 661 pts, NIfTI)
- Labels: RT-PCR COVID-19 positive (all)
- negatives_value: non-nodule abnormality, no negatives
- Citation: An, P., Xu, S., Harmon, S. A., Turkbey, E. B., Sanford, T. H., Amalou, A., Kassin, M., Varble, N., Blain, M., Anderson, V., Patella, F., Carrafiello, G., Turkbey, B. T., & Wood, B. J. (2020). CT Images in COVID-19 [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/TCIA.2020.GQRY-NC81
- Verified from: collection page, NBIA getSeries LicenseName/LicenseURI fields

### RIDER Lung CT (`rider_lung_ct`)

- URL: https://www.cancerimagingarchive.net/collection/rider-lung-ct/
- DOI: 10.7937/K9/TCIA.2015.U1X8A5NR
- Provider: The Cancer Imaging Archive (TCIA), NCI
- License: CC-BY-4.0 (images, v3 2024); lesion-notes XLS listed as CC-BY-3.0 (https://creativecommons.org/licenses/by/4.0/)
- Access: public (no registration)
- Redistribution: yes, attribution; commercial: yes; derivatives: yes
- Download: TCIA NBIA REST API v1 (getSeries / getSeriesSize / getImage?SeriesInstanceUID=), or TCIA Data Retriever with the .tcia manifest; no login
- Format: DICOM CT, SEG, SR, PR; size: ~1.3 GB (43 GB / 32 pts, many recons)
- Labels: lesion SEG / measurements (test-retest)
- negatives_value: low (all NSCLC); test-retest repeatability only
- Citation: Zhao, B., Schwartz, L. H., Kris, M. G., & Riely, G. J. (2015). Coffee-break lung CT collection with scan images reconstructed at multiple imaging parameters (Version 3) [Dataset]. The Cancer Imaging Archive. https://doi.org/10.7937/k9/tcia.2015.u1x8a5nr
- Verified from: collection page, NBIA getSeries LicenseName/LicenseURI fields

### Lung CT Segmentation Challenge 2017 (LCTSC) (`lctsc`)

- URL: https://www.cancerimagingarchive.net/collection/lctsc/
- DOI: 10.7937/K9/TCIA.2017.3R3FVZ08
- Provider: The Cancer Imaging Archive (TCIA), NCI
- License: CC-BY-3.0 (https://creativecommons.org/licenses/by/3.0/)
- Access: public (no registration)
- Redistribution: yes, attribution; commercial: yes; derivatives: yes
- Download: TCIA NBIA REST API v1 (getSeries / getSeriesSize / getImage?SeriesInstanceUID=), or TCIA Data Retriever with the .tcia manifest; no login
- Format: DICOM CT + RTSTRUCT; size: ~83 MB (5.0 GB / 60 pts)
- Labels: organ-at-risk RTSTRUCT (lungs, heart, esophagus, spinal cord)
- negatives_value: anatomy/segmentation only (oncology RT patients)
- Citation: Yang, J., Sharp, G., Veeraraghavan, H., Van Elmpt, W., Dekker, A., Lustberg, T., & Gooding, M. (2017). Data from Lung CT Segmentation Challenge (LCTSC) (Version 3) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/K9/TCIA.2017.3R3FVZ08
- Verified from: collection page, NBIA getSeries LicenseName/LicenseURI fields

### Lung-PET-CT-Dx (`lung_pet_ct_dx`)

- URL: https://www.cancerimagingarchive.net/collection/lung-pet-ct-dx/
- DOI: 10.7937/TCIA.2020.NNC2-0461
- Provider: The Cancer Imaging Archive (TCIA), NCI
- License: CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/)
- Access: public (no registration)
- Redistribution: yes, attribution; commercial: yes; derivatives: yes
- Download: TCIA NBIA REST API v1 (getSeries / getSeriesSize / getImage?SeriesInstanceUID=), or TCIA Data Retriever with the .tcia manifest; no login
- Format: DICOM CT, PET + XML bbox; size: ~350 MB (123 GB CT / 355 pts)
- Labels: tumor bounding boxes (PASCAL-VOC XML); histology: adenocarcinoma/small-cell/large-cell/squamous
- negatives_value: low (all cancer); histology classification
- Citation: Li, P., Wang, S., Li, T., Lu, J., HuangFu, Y., & Wang, D. (2020). A Large-Scale CT and PET/CT Dataset for Lung Cancer Diagnosis (Lung-PET-CT-Dx) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/TCIA.2020.NNC2-0461
- Verified from: collection page, NBIA getSeries LicenseName/LicenseURI fields

## Pilot acquisition (Phase A)

Data root: `/home/mpetrick/repos/ThoraxGPT_from_Wish/data/` (a `data/.gitignore` containing `*` was added because the repo had no .gitignore). Total `du -sb data` = 6.67 GB (budget 9.5 GB).

| dataset | patients | series | bytes | notes |
|---|---|---|---|---|
| lidc_idri | 60 | 60 CT | 4.31 GB (8,293 files incl. labels) | 20 negatives for 'nodule >=3 mm' (10 no marks at all, 10 only <3 mm marks) + 40 positives, from single-CT-series patients in the smaller half of series sizes (99–203 slices, so mostly 2–2.5 mm slices); reader XML for all 60 extracted to `_labels/xml_selected/<SeriesUID>.xml` |
| nsclc_radiogenomics | 27 | 27 CT + 27 SEG | 2.36 GB (4,431 files) | patients whose SEG study has exactly one CT series, smallest first; label = tumour DICOM-SEG + clinical/genomic CSV + AIM |

Why NSCLC Radiogenomics as the external domain: CC BY 3.0 (commercial use + redistribution with attribution, same terms as LIDC, no NC/ND friction), explicitly planned in Vision §5.4, different label type (voxel tumour segmentation, histology/stage/mutations) and different site/scanners (Stanford/Palo Alto VA) — good for a held-out cross-dataset test. The COVID alternatives were either NC (RICORD-1A/1B) or not on NBIA (CT Images in COVID-19 = Aspera/NIfTI). COVID-19-AR (CC BY 4.0) is the best open non-nodule-abnormality add-on; NLST (CC BY 4.0) is the best open source of true negatives for Phase B.

### API endpoints that worked (no auth)

- `GET https://services.cancerimagingarchive.net/nbia-api/services/v1/getCollectionValues`
- `GET .../getSeries?Collection=LIDC-IDRI&Modality=CT` (returns ImageCount, FileSize, LicenseName/URI, CollectionURI per series)
- `GET .../getSeries?Collection=NSCLC%20Radiogenomics`
- `GET .../getSeriesSize?SeriesInstanceUID=<uid>` -> `[{TotalSizeInBytes, ObjectCount}]`
- `GET .../getImage?SeriesInstanceUID=<uid>` -> zip (`00000001.dcm`... + `LICENSE`), ~50% of unzipped size, ~4–5 MB/s per stream
- label files: `https://www.cancerimagingarchive.net/wp-content/uploads/<file>` (exact list in each `_acquisition.json`)

### Gotchas

- NBIA collection name is `NSCLC Radiogenomics` (space) while the web slug is `nsclc-radiogenomics`.
- getImage zips contain no LIDC XML; the XML comes only from `LIDC-XML-only.zip`, whose files are named by number, not patient — match on `<SeriesInstanceUid>` inside each XML (done; 60/60 matched).
- `getSeries` FileSize = unzipped bytes; transfer is about half that.
- `CT Images in COVID-19` is not served by NBIA (Aspera NIfTI only). `NLST` getSeries with PatientID returned an empty body — query by other filters.
- mosmed.ai reset connections and the DeepLesion NIH Box link returned 404 on 2026-10-15; their terms are only verified from the paper (MosMed) or unverified (DeepLesion).
- RadGenome-ChestCT: HF API says `gated: false`, license tag CC-BY-4.0, but card terms (copied from CT-RATE) forbid commercial use and redistribution -> treat as research-only. It has masks/reports only; volumes are CT-RATE (gated).
- Historical setup: the repository initially lacked `.gitignore`, so the research pass added `data/.gitignore` (`*`). The current repository ignores `data/`; preserve that protection.
- Selecting smallest series biases LIDC towards thicker slices; widen the size cap for Phase B.

### Historical scratchpad files

These names describe the acquisition research scratchpad. They are not maintained CLI
commands or scripts shipped at the repository root. Do not run a nonexistent `acquire.py`
from the checkout. The maintained port is `thoraxbench acquire` (see *Acquire an approved
dataset*). The stratified LIDC selector of the prototype is historical; the frozen pilot
`_selection.json` files keep its result.

- `acquire.py` — resumable downloader (httpx if available, else urllib); `python3 acquire.py --data-root DATA --dataset lidc_idri|nsclc_radiogenomics [--dry-run|--manifest-only] [--workers N]`
- `build_registry.py` — regenerates `datasets.json`; `xlsx_read.py` — stdlib xlsx reader
- per dataset in `data/raw/<id>/`: `_selection.json`, `_acquisition.json`, `_sha256.txt` (sha256sum -c format), `_LICENSE_SNAPSHOT.txt`, `_api_log.jsonl`, `_labels/`
