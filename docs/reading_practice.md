# How radiologists read chest CT — and what ThoraxBench should copy

Research note for ThoraxBench Local (Vision.md §9, §10, §12, §19, §28).
This self-made experimental tool is **not medical advice from a qualified healthcare
professional**. Findings and reference knowledge may be incorrect, incomplete or misleading.
Do not use outputs for diagnosis or treatment decisions.

Every factual item carries a source URL. Items marked **[unverified]** could not be confirmed
against a primary source during this pass. Preserve those labels. The clinical tables below
summarize research sources; they are not software-operator treatment instructions.

Before implementing a research recommendation:

1. Check the cited primary source.
2. Record the applicable population and exclusions.
3. Confirm whether the recommendation matches the current implementation.
4. Version and hash any result-affecting transform, prompt or threshold.
5. Verify it with synthetic tests before development experiments.

**Checkpoint:** no unverified threshold becomes a validated claim. If the source or patient
context is missing, keep the limitation explicit. Do not derive a care instruction from it.

Compiled 2026-10-15.

---

## 1. The reading workflow in practice

### 1.1 Acquisition and reconstruction the reader expects

- **Coverage.** A standard thoracic CT runs from the lung apices to the posterior costophrenic sulci. ACR–SABI–SPR–STR Practice Parameter for Thoracic CT, §A: https://gravitas.acr.org/PPTS/DownloadPreviewDocument?DocId=13
- **Slice thickness.** Axial images are usually reconstructed at about 3–5 mm with both a soft-tissue kernel and a high-spatial-frequency (lung or bone) kernel. A thickness of about 1.2 mm or less is preferable unless volumetric reconstructions (<1.25 mm, sharp kernel) are also created. Same source.
- **Multiplanar reformats.** Sagittal and coronal reconstructions at matched thickness are recommended, and multiplanar viewing is encouraged. Same source, §A and §F.
- **MIP and MinIP.** Contiguous or overlapping axial MIP images with a **5–10 mm slab** help detect lung nodules when read alongside thin slices. MinIP with a slab under 10 mm helps assess emphysema and air trapping. Same source, §A.
- **HRCT.** HRCT means slices of 1.5 mm or less (preferably 1 mm or less) with a high-spatial-frequency kernel. Optional prone images separate posterior lung disease from dependent atelectasis, and end-expiratory images show air trapping. ACR–SPR–STR HRCT Practice Parameter: https://gravitas.acr.org/PPTS/DownloadPreviewDocument?DocId=83
- **Lung cancer screening LDCT.** Slices of 2.5 mm or less (1.0 mm or less preferred), with reconstruction interval no larger than slice thickness. MIP "may be useful to increase the sensitivity" for nodules. The scanner or viewer must be able to produce MIP and MPR. ACR–STR LCS Practice Parameter: https://gravitas.acr.org/PPTS/DownloadPreviewDocument?DocId=38
- **Windowing.** "Anatomically appropriate window and level settings should be used to view the lung parenchyma, mediastinum, vasculature, chest wall, skeletal structures, any visible portions of the lower neck and upper abdomen, and implanted metallic devices." Thoracic CT PP §F (DocId=13 above).

### 1.2 Standard display windows (W = width, L = level, HU)

| Window | W / L | Resulting HU range | Used for | Source |
|---|---|---|---|---|
| Lung | 1500 / −600 | −1350 … +150 | Parenchyma, nodules, airways, pneumothorax, emphysema | https://radiopaedia.org/articles/windowing-ct |
| Mediastinum | 350 / 50 | −125 … +225 | Nodes, heart, pericardium, pleural fluid, great vessels | same |
| Vascular / heart (contrast) | 600 / 200 or 1000 / 400 | −100 … +500 / −100 … +900 | Contrast-enhanced vessels, calcified plaque | same |
| Bone | 1800 / 400 (spine bone) | −500 … +1300 | Ribs, spine, sternum, osseous lesions | same |
| Abdominal soft tissue | 400 / 50 | −150 … +250 | Upper abdomen on chest CT | same |
| Liver | 150 / 30 | −45 … +105 | Subtle liver lesions in the upper abdomen | same |
| Subdural (head) | 130–300 / 50–100 | — | Not relevant to chest; listed only for completeness | same |
| Brain | 80 / 40 | 0 … 80 | Not relevant to chest. MedGemma uses it as an RGB channel (below). | same; https://arxiv.org/pdf/2507.05201 |

Window values differ between institutions and vendors (same Radiopaedia page). **MedGemma's own CT encoding** maps three windows to RGB. Original MedGemma technical report (https://arxiv.org/pdf/2507.05201):

- R: "bone & lung", W 2250 / L −100
- G: soft tissue, W 350 / L 40
- B: brain, W 80 / L 40

The MedGemma 1.5 report describes axial 2D slices resized to 896×896 and at most 85 slices per volume (https://arxiv.org/pdf/2604.05081). Whether 1.5 keeps the same windows was **not confirmed**. Check this against the official CT notebook before freezing `medgemma_ct_v1`.

### 1.3 Reference HU values

| Material | HU | Source |
|---|---|---|
| Air | −1000 | https://radiopaedia.org/articles/hounsfield-unit |
| Lung parenchyma | −950 … −650 | same |
| Fat | −100 … −115 (subcutaneous) | same |
| Water | 0 | same |
| Muscle / liver (unenhanced) | 45–50 | same |
| Acute blood in pleural space | ~35–70 | https://radiopaedia.org/articles/hemothorax-1 |
| Trabecular bone | 300–800 | https://radiopaedia.org/articles/hounsfield-unit |
| Cortical bone | >1000 | same |
| Coronary calcium (Agatston) | ≥130 (weights: 130–199 = 1, 200–299 = 2, 300–399 = 3, ≥400 = 4) | https://radiopaedia.org/articles/agatston-score |
| Emphysema (inspiratory) | ≤ −950 | https://www.springermedicine.com/pdf/10.3348/jksr.2018.78.1.1 |
| Air trapping (expiratory) | ≤ −856 | https://pmc.ncbi.nlm.nih.gov/articles/PMC5736979 ; https://pubs.rsna.org/doi/10.1148/radiol.2017171519 |
| Pericardial cyst, simple | ≤10 (if >10 HU, consider MRI) | ACR white paper, Munden 2018: https://doi.org/10.1016/j.jacr.2018.04.029 |
| Adrenal lipid-rich adenoma | <10 (unenhanced) | https://radiopaedia.org/articles/management-of-incidental-adrenal-masses-american-college-of-radiology-white-paper-1 |
| Enostosis vs sclerotic metastasis | mean >885 HU favors bone island (95% sens / 96% spec, untreated mets) | Ulano et al. AJR 2016, summarized at https://www.auntminnie.com/clinical-news/ct/article/15615587/ct-separates-bone-mets-from-benign-lesions |

### 1.4 How readers scroll and search

- In eye-tracking work on chest CT nodule search, 24 radiologists split into **drillers** and **scanners**. Drillers hold the eyes on one region and scroll fast through depth. Scanners cover a whole level before moving on. Drillers found more nodules and covered more lung. Drew et al., J Vis 2013: https://pmc.ncbi.nlm.nih.gov/articles/PMC3736761
- In practice this means the lung is reviewed **region by region (e.g., per quadrant or lobe), scrolling through the full z-extent each time**, rather than reading one slice at a time. The method relies on **continuity between adjacent slices**. A nodule appears and disappears over a few slices, while a vessel continues and branches. Static, sparse slice samples cannot reproduce this cue. That makes a strong argument for MIP slabs (§1.1) when only a few images can be passed to a model.
- **Comparison with priors is mandatory where they exist.** Readers compare the images themselves, not only the prior reports, and compare against the oldest available scan to detect slow growth. ACR–STR LCS PP: https://gravitas.acr.org/PPTS/DownloadPreviewDocument?DocId=38. Lung-RADS assigns category 0 when priors are being retrieved, and defines nodule growth as an increase of at least 1.5 mm (https://radiopaedia.org/articles/lung-rads).
- Nodules are measured on lung windows. Lung-RADS uses the mean of long and short axis to one decimal place (same source). Fleischner uses the average of long and short axis, or volume (https://radiopaedia.org/articles/fleischner-society-pulmonary-nodule-recommendations-1).

### 1.5 Systematic search pattern / checklist

There is no single society-mandated order. The ACR practice parameter (DocId=13, §F) names the structures that must be reviewed with appropriate windows. The RSNA RadReport library provides peer-reviewed structured chest CT templates in text and XML (https://www.rsna.org/covid-19/RSNA-Structured-Reporting ; https://radreport.org). The checklist below merges those structures with the ACR incidental-finding white papers. Its section order is a common convention **[unverified as a formal standard]**.

| # | Region | Window(s) | What to look for (minimum) | Key thresholds |
|---|---|---|---|---|
| 0 | Technique / QC | — | Coverage apex→costophrenic sulci, slice thickness, kernel, contrast phase, motion, inspiration level | ACR PP DocId=13 |
| 1 | Lines, tubes, devices | Mediastinal + bone | ETT, CVC tip (target: cavoatrial junction / low SVC), pacemaker/ICD leads, chest drains, sternotomy wires, valves, stents, ports | https://radiopaedia.org/articles/cvc-position-on-chest-x-ray-summary ; https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4644031/ |
| 2 | Airways | Lung (+ MinIP) | Trachea/main bronchi patency, endoluminal nodules, bronchial wall thickening, bronchiectasis (bronchoarterial ratio >1.5, lack of tapering, bronchus within 1 cm of pleura), mucus plugging | https://radiopaedia.org/articles/bronchiectasis |
| 3 | Lung parenchyma | Lung (+ MIP 5–10 mm, coronal) | Nodules/masses (≤30 mm nodule, >30 mm mass), consolidation, GGO, atelectasis, emphysema type/grade, ILA/fibrosis, cysts/cavities, mosaic attenuation, septal thickening | Fleischner 2017, Lung-RADS v2022, Fleischner ILA 2020 |
| 4 | Pleura | Lung + mediastinal | Effusion (size, density), pneumothorax, thickening/plaques/masses | §2.7 below |
| 5 | Mediastinum & hila | Mediastinal | Lymph nodes (short axis; >10 mm historically abnormal, <15 mm incidental needs no work-up), masses by compartment, thyroid, thymus, esophagus, hiatal hernia | Munden 2018 |
| 6 | Heart & pericardium | Mediastinal | Heart size, pericardial effusion/thickening (>3–4 mm abnormal), coronary artery calcification (always report), valve calcification | Munden 2018 ; SCCT/STR 2016 |
| 7 | Great vessels | Mediastinal (+ vascular if contrast) | Aortic diameter (ascending, descending), aortic calcification, PA diameter (≥30 mm or ≥ ascending aorta = dilated), PE if contrast | Munden 2018 |
| 8 | Chest wall, axillae, breasts | Mediastinal | Axillary nodes, breast masses, soft-tissue masses, subcutaneous emphysema | ACR PP DocId=13 §F |
| 9 | Bones | Bone | Rib/sternal/vertebral fractures (incl. osteoporotic compression), lytic/sclerotic lesions | https://radiopaedia.org/articles/rib-fractures ; Bone-RADS https://link.springer.com/doi/10.1007/s00256-022-04022-8 |
| 10 | Upper abdomen & lower neck | Abdominal soft tissue / liver | Adrenal nodules, liver/kidney lesions, thyroid nodules, hiatal hernia, gallstones | ACR thyroid/adrenal white papers (§2.4–2.5) |
| 11 | Review areas | Lung | Apices, perihilar, retrocardiac, paramediastinal, lung bases/costophrenic angles, behind the diaphragm. **[unverified]** These areas are commonly taught as frequent miss sites. | — |

Vertebral fractures are a documented blind spot. They were present in 9.5% of patients on chest/abdominal CT, but only 14.6% were reported: https://www.qxmd.com/r/18164889

---

## 2. Guidelines the report must follow

### 2.1 Fleischner Society 2017 — incidental pulmonary nodules

Source: MacMahon et al., Radiology 2017, https://doi.org/10.1148/radiol.2017161659. Table summarized from https://radiopaedia.org/articles/fleischner-society-pulmonary-nodule-recommendations-1

**Scope.** The guideline applies to incidental nodules in adults ≥35 years. It does **not** apply to patients with known cancer, immunocompromised patients, or lung-cancer screening (use Lung-RADS there). High risk means an estimated cancer risk >5%. Risk factors include older age, heavy smoking, irregular or spiculated margins, and upper-lobe location.

**Solid nodules**

| Size (avg. diameter / volume) | Single, low risk | Single, high risk | Multiple, low risk | Multiple, high risk |
|---|---|---|---|---|
| <6 mm (<100 mm³) | No routine follow-up | Optional CT at 12 mo | No routine follow-up | Optional CT at 12 mo |
| 6–8 mm (100–250 mm³) | CT 6–12 mo, then consider CT 18–24 mo | CT 6–12 mo, then CT 18–24 mo | CT 3–6 mo, then consider CT 18–24 mo | CT 3–6 mo, then CT 18–24 mo |
| >8 mm (>250 mm³) | Consider CT 3 mo, PET/CT, or tissue sampling | same as low risk | CT 3–6 mo, then consider CT 18–24 mo | CT 3–6 mo, then CT 18–24 mo |

With multiple nodules, management follows the most suspicious nodule.

**Subsolid nodules**

| Type | <6 mm (<100 mm³) | ≥6 mm (>100 mm³) |
|---|---|---|
| Single pure ground-glass | No routine follow-up | CT 6–12 mo to confirm persistence, then CT every 2 years until 5 years |
| Single part-solid | No routine follow-up | CT 3–6 mo to confirm persistence; if unchanged and solid component <6 mm, annual CT for 5 years |
| Multiple | CT 3–6 mo; if stable, consider CT at 2 and 4 years | CT 3–6 mo; subsequent management based on the most suspicious nodule(s) |

The single part-solid row (<6 mm: no routine follow-up; solid part ≥6 mm is highly suspicious) is **[unverified]** in this pass. The Radiopaedia summary listed only the ≥6 mm part-solid row. Check it against the primary paper.

### 2.2 Lung-RADS v2022 (screening LDCT only)

Source: https://radiopaedia.org/articles/lung-rads ; ACR Lung-RADS page https://www.acr.org/Clinical-Resources/Clinical-Tools-and-Reference/Reporting-and-Data-Systems/Lung-RADS

| Cat. | Meaning (malignancy prob.) | Key criteria (baseline unless noted) | Management |
|---|---|---|---|
| 0 | Incomplete | Priors being retrieved, incomplete lung imaging, or findings suggesting infection/inflammation | Comparison, or LDCT in 1–3 mo |
| 1 | Negative (<1%) | No nodules, or benign calcification / fat-containing nodules | Annual LDCT |
| 2 | Benign (<1%) | Solid <6 mm; new solid <4 mm; part-solid <6 mm; GGN <30 mm (or ≥30 mm stable/slow-growing); juxtapleural smooth solid <10 mm; subsegmental airway nodule | Annual LDCT |
| 3 | Probably benign (1–2%) | Solid 6–<8 mm; new solid 4–<6 mm; part-solid ≥6 mm with solid part <6 mm; new part-solid <6 mm; GGN ≥30 mm or new | LDCT in 6 mo |
| 4A | Suspicious (5–15%) | Solid 8–<15 mm; growing solid <8 mm; new solid 6–<8 mm; part-solid with solid part 6–<8 mm; segmental/proximal airway nodule; thick-walled/multilocular cyst | LDCT in 3 mo; PET/CT if solid part ≥8 mm |
| 4B | Very suspicious (>15%) | Solid ≥15 mm; new/growing solid ≥8 mm; solid part ≥8 mm; persistent proximal airway nodule | Diagnostic CT, PET/CT and/or tissue sampling |
| 4X | Very suspicious | Cat 3/4 plus additional suspicious features (spiculation, GGN doubling in 1 year, enlarged nodes) | As 4B |
| S | Modifier | Clinically significant non-lung-cancer finding (e.g., "3S") | Per ACR incidental-finding guidance |

### 2.3 ACR white paper — mediastinal and cardiovascular incidental findings (Munden 2018)

Source: https://doi.org/10.1016/j.jacr.2018.04.029 (full text read via https://rebuild.professionalradiology.com/media/user/resources/PIIS1546144018305301.pdf)

- **Mediastinal lymph nodes.** Measure the short axis. Nodes have historically been called abnormal at ≥10 mm short axis. Committee consensus: **incidental nodes <15 mm short axis, with no other findings, need no further evaluation.** Prevalence of incidental enlarged nodes on screening CT is about 1–6%.
- **Mediastinal masses.** Localize to the prevascular, visceral, or paravertebral compartment and characterize texture (cystic vs solid). Posterior masses go to MRI. Prevalence is about 0.4–0.9%.
- **Pericardium.** 15–30 mL of fluid is normal and up to 50 mL may be physiologic. Normal thickness is ≤2 mm; >3–4 mm is abnormal. Report fluid estimated >50 mL. A simple cyst ≤10 HU needs no work-up.
- **Thoracic aorta.** Mean ascending diameter is 34.1 ± 3.9 mm in men and 31.9 ± 3.5 mm in women. Mean descending diameter is 25.8 ± 3.0 mm in men and 23.1 ± 2.6 mm in women. Above the upper limit of normal = "dilated/ectatic". **Aneurysm ≈ ≥5.0 cm ascending, ≥4.0 cm descending.** ≥5.5 cm is high rupture risk, and the threshold is ≥5.0 cm in Marfan or Ehlers–Danlos syndrome. Aortic findings appear incidentally in up to 3.4% of chest CTs.
- **Coronary artery calcification (CAC).** Report it on all CTs, gated or not. Use Agatston or a visual grade (none / mild / moderate / heavy-severe). Heavy CAC should be further evaluated. Prevalence: 53% of non-cardiac CTs in patients without known CAD; 41% of patients >40 years.
- **Main pulmonary artery.** ≥3.0 cm, or ≥ the ascending aorta diameter, should be reported as dilated.
- **Updated surgical thresholds.** The 2022 ACC/AHA guideline lowers the threshold for sporadic ascending aneurysm to 5.0 cm in selected patients at expert centers. Rapid growth (≥0.3 cm/yr over 2 years or ≥0.5 cm in 1 year) is an indication for surgery. https://www.acc.org/Latest-in-Cardiology/ten-points-to-remember/2022/11/01/12/21/2022-Guideline-on-Aortic-Disease-2-gl-ad

### 2.4 Coronary calcium on non-gated CT (CAC-DRS / SCCT-STR)

- SCCT/STR 2016 guideline (Hecht et al., J Cardiovasc Comput Tomogr 2017): report CAC on all non-contrast, non-cardiac chest CT. https://doi.org/10.1016/j.jcct.2016.11.003
- CAC-DRS: Agatston categories A0 (0), A1 (1–99), A2 (100–299), A3 (≥300). Visual categories V0–V3 (none / mild / moderate / severe) may be used on non-gated scans. A modifier N gives the number of vessels involved. https://radiopaedia.org/articles/coronary-artery-calcium-data-and-reporting-system-cac-drs
- UK BSCI/BSCCT/BSTI consensus: report CAC on all non-gated thoracic CT as none / mild / moderate / severe, and advise assessment of modifiable risk factors. https://pmc.ncbi.nlm.nih.gov/articles/PMC7774698
- Visual scoring on non-gated chest CT: sensitivity 83–90% and specificity 100% vs dedicated calcium scoring, κ 0.89–0.95. https://www.dicardiology.com/content/visual-ordinal-scoring-coronary-artery-calcium-chest-ct

### 2.5 Other incidental-finding guidance relevant on chest CT

- **Thyroid nodule (ACR, Hoang 2015).** Recommend ultrasound for a nodule ≥1.5 cm at age ≥35, or ≥1 cm at age <35, or with suspicious features (local invasion, abnormal nodes). Measure in the axial plane; use the largest nodule. https://radiopaedia.org/articles/69951
- **Adrenal nodule (ACR, Mayo-Smith 2017).** <1 cm: no work-up. <10 HU unenhanced or macroscopic fat: benign. 1–4 cm, indeterminate, no cancer history: <2 cm consider adrenal CT at 12 mo; 2–4 cm adrenal-protocol CT. Stable ≥1 year: no follow-up. https://radiopaedia.org/articles/management-of-incidental-adrenal-masses-american-college-of-radiology-white-paper-1 ; https://wiki.radiology.wisc.edu/images/f/f1/Management_of_Incidental_Adrenal_Masses_A_White_Paper_of_the_ACR_Incidental_Findings_Committee.pdf
- **Interstitial lung abnormalities (Fleischner 2020, Hatabu).** Non-dependent ground-glass or reticular abnormality, distortion, traction bronchiectasis, honeycombing, or non-emphysematous cysts involving ≥5% of a lung zone in people without suspected ILD. Subtypes are non-subpleural, subpleural non-fibrotic, and subpleural fibrotic (the last progresses more often). Prevalence is 4–9% of smokers and 2–7% of non-smokers aged >60. https://pmc.ncbi.nlm.nih.gov/articles/PMC7970441/
- **ACR lung-findings white paper (Munden 2021).** Covers incidental lung findings in asymptomatic adults ≥35, including ILA and lung cysts. https://doi.org/10.1016/j.jacr.2021.04.014 ; https://pubmed.ncbi.nlm.nih.gov/34246574/
- **Bone lesions (Bone-RADS, Society of Skeletal Radiology 2022).** 1 = leave alone; 2 = different modality; 3 = follow-up imaging; 4 = biopsy/oncology referral. Separate CT algorithms exist for lucent and sclerotic/mixed lesions. https://link.springer.com/doi/10.1007/s00256-022-04022-8

### 2.6 Disease-specific grading criteria

**Emphysema**
- Types: centrilobular (upper zones, smoking), panlobular (lower zones, α1-antitrypsin deficiency), paraseptal (subpleural, bullae, pneumothorax risk). https://radiopaedia.org/articles/emphysema
- Fleischner visual grading (Lynch 2015, https://pmc.ncbi.nlm.nih.gov/articles/PMC4613878):
  - Centrilobular: trace / mild / moderate / confluent / advanced destructive
  - Paraseptal: mild / substantial
  - Panlobular: separate category
- **[unverified]** Zone percentages for the centrilobular grades: trace <0.5% of a zone, mild 0.5–5%, moderate >5% with discrete lucencies, then confluent and advanced destructive.
- Quantitative: %LAA-950 = share of lung voxels ≤ −950 HU on inspiratory CT. This is the most widely accepted threshold, chosen over −960 or −970 HU for noise robustness. https://www.springermedicine.com/pdf/10.3348/jksr.2018.78.1.1
- Bands used in COPDGene-type studies: <5% = none/minimal, 5–<10% = mild, ≥10% = emphysema-predominant. https://respiratory-research.biomedcentral.com/articles/10.1186/s12931-014-0127-9/tables/1 ; https://experts.arizona.edu/en/publications/non-emphysematous-chronic-obstructive-pulmonary-disease-is-associ/
- %LAA-950 depends on dose, kernel, and slice thickness, so treat it as reconstruction-dependent.

**Bronchiectasis**
- Bronchoarterial ratio >1.5 = bronchiectasis (1–1.5 can be normal, e.g., at altitude). Also lack of tapering, and a bronchus visible within 1 cm of the costal pleura.
- Morphology: cylindrical, varicose, cystic. https://radiopaedia.org/articles/bronchiectasis

**Lymph nodes**
- Short axis is the standard. Upper limit of normal is 10 or 15 mm depending on context. https://radiopaedia.org/articles/lymphadenopathy ; Munden 2018

**Cardiomegaly**
- Cardiothoracic ratio ≥0.5 on PA radiograph or CT (StatPearls, https://www.ncbi.nlm.nih.gov/books/NBK542296/).
- On axial CT: maximal transverse cardiac diameter (outer myocardium) divided by maximal inner thoracic diameter. It correlates with radiograph CTR (r = 0.80). The CT threshold is not well validated (AUC 0.70 for LVH). https://vivo.weill.cornell.edu/display/pubid22261772
- Treat cardiomegaly on CT as a soft, subjective finding.

**Pleural effusion size (Moy et al., Chest 2012)**
- Small = first anteroposterior quartile of the hemithorax, moderate = second, large = third or fourth.
- For borderline cases, AP depth at the midclavicular line: ≤3 cm small, ≤10 cm moderate.
- Volume correlates: small <20%, moderate 20–40%, large >40% of hemithorax volume.
- https://www.auntminnie.com/clinical-news/ct/article/15604281/technique-categorizes-pleural-effusion-size-at-ct
- Rough volume from maximal depth: 2 cm ≈ 200 mL, 4 cm ≈ 500 mL, 6 cm ≈ 800 mL, 8 cm ≈ 1100 mL, 10 cm ≈ 1400 mL. https://radiopaedia.org/articles/pleural-effusion
- CT cannot separate transudate from exudate by density. Fluid at about 35–70 HU suggests haemothorax. https://radiopaedia.org/articles/hemothorax-1

**Pericardial effusion size (by depth)**
- <5 mm (~50–100 mL); 5–10 mm (100–250 mL); 10–20 mm (250–500 mL); >20 mm (>500 mL).
- Simplified grades: small <10 mm, moderate 10–20 mm, large >20 mm.
- https://radiopaedia.org/articles/pericardial-effusion

**Cavity wall thickness (Woodring)**
- ≤4 mm is usually benign; >15 mm is usually malignant; the range in between overlaps. https://radiopaedia.org/articles/pulmonary-cavity-1

**Pleural thickening — malignant features (Leung 1990)**
- Circumferential, nodular, parietal >1 cm, mediastinal pleural involvement.
- Specificity 88–100%; any criterion gives 72% sensitivity and 83% specificity.
- https://pubmed.ncbi.nlm.nih.gov/2106209/ ; https://pmc.ncbi.nlm.nih.gov/articles/PMC7717031

**Pneumothorax**
- Size conventions are radiograph-based: BTS <2 cm vs ≥2 cm at the hilum; ACCP 3 cm apex-to-cupola. https://radiopaedia.org/articles/pneumothorax
- BTS 2023 allows conservative management of minimally symptomatic primary spontaneous pneumothorax regardless of size. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11037506/
- CT signs of tension: contralateral mediastinal shift and ipsilateral diaphragm depression or inversion. https://pmc.ncbi.nlm.nih.gov/articles/PMC7066360/figure/Fig7

---

## 3. Implications for ThoraxBench preprocessing

The following are research implementation proposals, not a claim that every feature is
implemented. Each proposed deterministic transform starts from the canonical HU volume
(Vision §9.3). Use [the architecture](architecture.md) and [the plan](plan.md) to check scope.
The later upstream-notebook check in [model research](model_cards.md#5-official-medgemma-15-ct-preprocessing-reference)
supersedes the unconfirmed MedGemma window recipe retained in this historical note.

1. **Select an adapter-specific rendering.**
   - For separate labeled images, use lung 1500/−600, mediastinum 350/50 and bone 1800/400.
   - Add abdomen 400/50 for upper-abdomen slices.
   - For `medgemma_ct_v1`, verify the official notebook's RGB recipe before implementation.
     The original proposed values here were 2250/−100, 350/40 and 80/40; the later notebook
     check records 2048/0, 350/40 and 80/40. Keep this distinction in provenance.
   - Do not mix encodings within one study. These are adapter-specific Vision S3 variants.
2. **Build a body mask and a lung mask by thresholding.**
   - Body: HU > −500, largest 3D component, holes filled.
   - Lung: HU < −400 inside the body mask, with air outside the body and the trachea/main bronchi removed (largest connected low-density components touching the slice border are excluded; components above the carina are dropped).
   - Hu et al. 2001 (https://doi.org/10.1109/42.929615) is the canonical threshold-plus-morphology approach. The exact −400/−500 HU cut-off is a design choice **[unverified as Hu et al.'s value]**. Log the chosen threshold.
3. **Use anatomy-anchored slice selection (Vision S2 and S4).** From the lung mask, derive:
   - z_apex: first slice with lung voxels
   - z_base: last slice with lung voxels
   - z_carina: where the airway splits into two components
   - z_max_lung: largest lung cross-section
   - z_heart: largest soft-tissue (0–100 HU) area between the lungs
   - z_dome: where diaphragm/liver appears inside the lung outline
   Include the selected anchors plus uniform samples between apex and base.
   Add 2–3 slices below the bases for the upper abdomen (adrenals, liver).
   Record source slice indices and the model-image order separately. Map `evidence_images`
   only when the recorded view supports that association; never invent a mapping.
4. **Add an anatomy-coverage QC check (Vision §9.5).**
   - Flag `incomplete_coverage` if the lung mask touches the first or last slice (the apex or bases were cut off).
   - Flag `thick_slices` if slice thickness is >3 mm. Small nodules and GGNs become unreliable, and Lung-RADS assumes ≤2.5 mm.
   - Record kernel, contrast (aorta mean HU >150 in a central blood-pool ROI ⇒ contrast-enhanced **[heuristic, unverified]**), and inspiration (lung volume from the mask).
5. **Use MIP slabs for nodule-oriented inputs.** Render axial **MIP slabs of 5–10 mm** on the lung window (ACR PP DocId=13; detection plateaus around 10 mm and falls with thicker slabs, https://research.utwente.nl/en/publications/deep-learning-based-pulmonary-nodule-detection-effect-of-slab-thi/ ; https://arxiv.org/pdf/1904.05956). A set of contiguous 10 mm MIP slabs covers a 300 mm lung in about 30 images, which fits MedGemma's 85-slice cap. Sparse single thin slices do not, because they can miss nodules between samples. Use **MinIP <10 mm** for emphysema and airways.
6. **Add coronal (and optionally sagittal) reformats.** Render 3–5 coronal slices at matched thickness: trachea/carina level, mid-heart, and posterior lungs, on lung and mediastinal windows. These show the craniocaudal distribution (upper-zone emphysema, basal fibrosis), effusion height, and diaphragm, which are hard to see from axial samples.
7. **Compute deterministic quantitative features as side-channel evidence.** These are not a diagnosis. Keep them out of the model prompt in the first experiments (or test as a prompt variant), so model and rule outputs can be compared fairly.
   - `%LAA-950` inside the lung mask: emphysema. Bands <5 / 5–10 / ≥10%. Note the kernel/thickness dependence.
   - Lung-mask voxels in −700…−300 HU as % of lung: GGO burden proxy **[heuristic]**.
   - Lung voxels > −100 HU (excluding vessels and ROIs touching the mediastinum, after a morphological opening): consolidation/atelectasis proxy **[heuristic]**.
   - Dependent pleural fluid: voxels 0–20 HU between lung mask and chest wall, below the lung (posterior). Report AP depth in mm, mapped to Moy quartiles and depth thresholds of 3 cm and 10 cm.
   - Pericardial fluid: 0–20 HU rim around the heart, maximum depth in mm (<10 / 10–20 / >20 mm).
   - 0–20 HU is a working simple-fluid window **[not found in an authoritative source]**. Blood is 35–70 HU, so also report the 20–70 HU band separately.
   - Calcification ≥130 HU (Agatston, https://radiopaedia.org/articles/agatston-score) within ROIs: (a) a coronary region around the heart surface (approximate; non-gated, so motion blur), and (b) aortic wall. Output an Agatston-like score and a V0–V3 visual proxy, together with the slice thickness used.
   - Air outside lung but inside the thorax/body: pleural air (pneumothorax candidate) and subcutaneous/mediastinal emphysema. Use a threshold < −900 HU between lung mask and chest wall **[heuristic]**.
   - Metal > ~2000–3000 HU (Radiopaedia: metal >3000 HU): device present, plus count of components.
   - Cardiothoracic ratio on the axial slice with maximal cardiac width. Report it with an explicit "soft finding" caveat.
   - Aortic diameter needs aorta segmentation (e.g., TotalSegmentator). Mark it as a phase-2 feature rather than threshold-only.
8. **Keep HU semantics.** Store the windowed renderings, but record the window, the slab, and the exact z-range per image in the manifest, so every `evidence_images` index can be traced to anatomy (Vision §9.4, §11).

## 4. Implications for prompting (Vision §19)

1. **Use a fixed checklist order matching §1.5.**
   Order: technique/quality → devices → airways → lungs → pleura → mediastinum/hila →
   heart/pericardium → great vessels → chest wall → bones → upper abdomen.
   Ask for a verdict per region. Keep coverage auditable and test whether this reduces
   “satisfaction of search” (stopping after the first finding).
2. **Required negatives.** For every ontology label, the model must output present / absent / uncertain. Pertinent negatives are compulsory for the high-stakes labels: pneumothorax, pleural effusion, pericardial effusion, consolidation, mass, aortic abnormality, and fracture. A missing answer is scored as "not assessed", not as absent.
3. **Tell the model which image is which.** Caption each image with window name, plane, slab thickness, and z-position (mm from apex, or "carina level"). Without this, a lung-window image cannot be checked for mediastinal findings, and a 10 mm MIP of a vessel can be mistaken for a nodule.
4. **Measurement caution.**
   - Do not ask the model for sizes in mm unless pixel spacing is shown on the image (a scale bar) or stated in the prompt.
   - Prefer categorical size bins tied to guidelines: nodule <6 / 6–8 / >8 mm / mass >30 mm; effusion small / moderate / large; aorta normal / dilated / aneurysmal.
   - Wherever a deterministic measurement exists (§3.7), the measurement wins over the model's estimate.
5. **Separate observation from interpretation (two-pass, Vision P4).**
   Pass 1 lists observations with evidence references. Pass 2 maps observations to labels.
   Derive educational guideline categories (Fleischner/Lung-RADS/CAC-DRS) from structured
   fields with explicit assumptions. Record missing eligibility/context. Do not present
   a code-derived category as a validated patient recommendation.
6. **Context limits.** Tell the model whether contrast was given (dissection and PE cannot be assessed without it; Munden 2018), and whether slices are thick or the scan is low-dose. Require `uncertain` or `abstain` when the needed window or plane is missing.
7. **Urgent flags.** List the emergency findings explicitly (tension pneumothorax, large pneumothorax, large pericardial effusion with mass effect, aortic dissection/rupture signs, malpositioned tube/line) and require `urgent_flags` to be filled independently of the label list.
