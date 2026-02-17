# Vax-Beacon Cohort Curation Guide

**Version:** 1.0  
**Date:** 2026-02-17  
**Cohort:** N=100 (Myocarditis 90 + Pericarditis 10)  
**Source:** VAERS 2021 (January–November)

---

## 1. Cohort Design Rationale

### Why 100 Cases?

The Vax-Beacon PoC cohort was designed to validate a multi-agent causality assessment pipeline across the full spectrum of clinical complexity, not to represent epidemiological prevalence. The cohort prioritizes **diagnostic diversity** over statistical power:

- **Balanced group representation**: Equal 30-30-30 split across myocarditis complexity tiers (G1/G2/G3) ensures the pipeline is tested against classic presentations, confounded cases, and severe cases equally.
- **Pericarditis control arm**: 10 isolated pericarditis cases test the pipeline's ability to distinguish an AE with INSUFFICIENT evidence (NAM 2024) from myocarditis with ESTABLISHED evidence.
- **Manageable for iterative development**: 100 cases allow full-cohort validation runs (~55 min) between pipeline versions while maintaining clinical depth per case.

### Selection Criteria

Cases were selected from the VAERS 2021 dataset (January–November) with the following criteria:

| Criterion | Myocarditis | Pericarditis |
|-----------|-------------|--------------|
| Vaccine | COVID-19 (mRNA or viral vector) | COVID-19 (mRNA) |
| MedDRA PT | Myocarditis | Pericarditis |
| Exclusion | Myopericarditis coded as pericarditis (reclassified) | Cases with concurrent troponin elevation suggesting myocardial involvement |
| Narrative | Sufficient clinical detail for multi-stage assessment | Brighton-qualifying clinical evidence |
| Distribution | Balanced across G1/G2/G3 severity tiers | 7 clean + 3 confounded |

---

## 2. Data Source & Extraction Pipeline

### Source Data

| Component | Description |
|-----------|-------------|
| Raw VAERS | `vaers_jan_nov_2021.csv` (~1 GB, full 2021 VAERS dump) |
| Myocarditis metadata | `Myocarditis_90_Final.csv` (manually curated with group, severity, clinical summary) |
| Pericarditis metadata | `pericarditis_isolated_all.json` (candidate pool with Brighton evidence) |
| Extraction script | `scripts/extract_cohort.py` |

### Extraction Process

```
Raw VAERS (1GB) ──→ Filter by VAERS_ID ──→ Merge with curated metadata ──→ vaers_100_cohort.csv
                         ↑                         ↑
                 Myocarditis_90_Final.csv    pericarditis_isolated_all.json
                 (90 IDs + G1/G2/G3)        (10 IDs + clean/confounded)
```

### Output Schema

The final `vaers_100_cohort.csv` contains all original VAERS columns plus 8 curated metadata columns:

| Column | Description |
|--------|-------------|
| `condition_type` | `myocarditis` or `pericarditis` |
| `group` | G1, G2, G3 (myocarditis) or clean, confounded (pericarditis) |
| `curated_age` | Verified age |
| `curated_sex` | Verified sex |
| `curated_onset_days` | Days from vaccination to symptom onset (manually verified from narrative) |
| `curated_key_evidence` | Key diagnostic evidence present (e.g., "Cardiac MRI, Troponin, EKG") |
| `curated_severity` | Severity indicators or confounder description |
| `curated_summary` | Brief clinical narrative summary |

---

## 3. Group Classification Definitions

### Myocarditis Groups (N=90)

#### G1 — Classic Vaccine-Associated Presentation (N=30)

**Definition:** Cases matching the typical mRNA vaccine-induced myocarditis profile with minimal confounding.

**Characteristics:**
- Young male (median age 17), predominantly after dose 2
- Onset within 0–5 days (strong causal window)
- Troponin elevation with chest pain
- Self-limiting course, generally good prognosis
- No significant alternative etiology identified

**Expected pipeline behavior:** Most should classify as A1 if Brighton ≥ L3 and onset ≤ 7 days. Cases with insufficient diagnostic data (L4) should early-exit to Unclassifiable.

#### G2 — Confounder Present (N=30)

**Definition:** Cases where a plausible alternative etiology or clinical confounder exists alongside the temporal vaccine association.

**Confounders include:**

| Confounder Type | Count | Examples |
|-----------------|-------|---------|
| Viral etiology | 15 | Active viral infection, positive viral serology |
| Cancer | 4 | Active malignancy, chemotherapy-related |
| Rheumatoid/Autoimmune | 3 | RA, SLE, polymyositis |
| COVID-19 positive | 3 | Active or recent SARS-CoV-2 infection |
| Medication-related | 1 | Lithium cardiotoxicity |
| Other | 4 | Mixed confounders |

**Expected pipeline behavior:** Pipeline must weigh alternative etiology (NCI score) against temporal association. Expected mix of A1 (confounder weak), B2 (confounder moderate), and C (confounder strong or temporal inconsistent).

#### G3 — Severe / Complex Presentation (N=30)

**Definition:** Cases with significant morbidity indicators suggesting fulminant disease or requiring critical care intervention.

**Severity indicators:**

| Indicator | Count | Description |
|-----------|-------|-------------|
| Reduced EF | 13 | LVEF < 55% (range 15–57%) |
| VT/VF | 7 | Ventricular tachycardia or fibrillation |
| ECMO | 5 | Extracorporeal membrane oxygenation required |
| Cardiac arrest | 4 | Documented cardiac arrest |
| Cardiogenic shock | 3 | Hemodynamic instability requiring support |
| Heart block | 3 | Advanced conduction abnormalities |
| Fulminant | 3 | Rapidly progressive myocarditis |
| Inotrope support | 2 | Dobutamine or other inotropic agents |

**Expected pipeline behavior:** Severity ≠ causality. Severe presentations often suggest alternative etiologies (GCM, fulminant viral) rather than vaccine-induced myocarditis (which is typically mild/self-limiting). Expected higher C rates due to NCI-driven alternative identification.

### Pericarditis Groups (N=10)

#### Clean — Isolated Pericarditis Without Confounders (N=7)

**Definition:** Well-documented pericarditis cases with Brighton-qualifying evidence and no significant comorbidities that could independently cause pericarditis.

**IDs:** 925542, 966794, 977955, 1128543, 1147729*, 1333796, 1361389

*Note: VAERS 1147729 was tagged as pericarditis in the cohort but cardiac MRI excluded pericarditis and confirmed isolated myocarditis. The pipeline correctly reclassified this case via narrative analysis (Stage 1 extraction).

**Expected pipeline behavior:** All should classify as C because isolated pericarditis has INSUFFICIENT evidence for causal association with mRNA vaccines per NAM 2024.

#### Confounded — Pericarditis With Autoimmune/Oncologic Comorbidity (N=3)

**Definition:** Pericarditis cases where pre-existing conditions (SLE, cancer) independently predispose to pericardial inflammation.

| VAERS ID | Confounder |
|----------|------------|
| 1314908 | SLE/Lupus |
| 1023768 | Cancer (age 86) |
| 1437261 | SLE, Sjögren's syndrome, Cancer |

**Expected pipeline behavior:** C classification expected both because pericarditis is not a known AE and because confounders provide plausible alternative causation.

---

## 4. Case Registry

### 4.1 Myocarditis — G1 Classic (N=30)

| VAERS ID | Age | Sex | Vaccine | Dose | Onset (d) | Brighton | WHO | NCI |
|----------|-----|-----|---------|------|-----------|----------|-----|-----|
| 1262194 | 16 | M | Pfizer | 2 | 2 | L3 | A1 | 0.0 |
| 1310544 | 21 | M | Moderna | UNK | 3 | L3 | A1 | 0.0 |
| 1321207 | 18 | M | Pfizer | UNK | 5 | L4 | UC | 0.0 |
| 1327087 | 18 | M | Pfizer | 2 | 2 | L4 | UC | 0.0 |
| 1333399 | 25 | M | Moderna | 2 | 3 | L2 | A1 | 0.0 |
| 1347238 | 25 | M | Moderna | 2 | 3 | L1 | C | 1.0 |
| 1382523 | 19 | M | Pfizer | 1 | 3 | L3 | A1 | 0.0 |
| 1382955 | 15 | M | Pfizer | 2 | 2 | L4 | UC | 0.0 |
| 1386123 | 15 | M | Pfizer | 1 | 2 | L3 | A1 | 0.0 |
| 1396077 | 17 | M | Pfizer | 2 | 1 | L4 | UC | 0.0 |
| 1397727 | 12 | M | Pfizer | 2 | 1 | L3 | A1 | 0.0 |
| 1400188 | 15 | M | Pfizer | 2 | 2 | L4 | UC | 0.0 |
| 1400232 | 14 | M | Pfizer | UNK | 2 | L2 | A1 | 0.0 |
| 1400865 | 23 | M | Pfizer | 2 | 1 | L3 | A1 | 0.0 |
| 1403701 | 25 | M | Moderna | 2 | 3 | L4 | UC | 0.0 |
| 1412996 | 15 | M | Pfizer | UNK | 1 | L4 | UC | 0.0 |
| 1413266 | 21 | M | Pfizer | 2 | 2 | L3 | A1 | 0.0 |
| 1413465 | 15 | M | Pfizer | 2 | 2 | L2 | B2 | 0.5 |
| 1415281 | 15 | M | Pfizer | 2 | 3 | L3 | A1 | 0.0 |
| 1419924 | 15 | M | Pfizer | 2 | 2 | L4 | UC | 0.0 |
| 1431066 | 17 | M | Pfizer | 2 | 3 | L2 | A1 | 0.0 |
| 1434274 | 15 | M | Pfizer | UNK | 1 | L4 | UC | 0.0 |
| 1464592 | 17 | M | Pfizer | 2 | 3 | L2 | A1 | 0.0 |
| 1490272 | 13 | M | Pfizer | UNK | 2 | L2 | A1 | 0.2 |
| 1501224 | 15 | M | Pfizer | 1 | 0 | L3 | B2 | 0.6 |
| 1511080 | 19 | M | Pfizer | 2 | 1 | L3 | C | 0.0 |
| 1515531 | 17 | M | Pfizer | UNK | 1 | L3 | A1 | 0.0 |
| 1549179 | 14 | M | Pfizer | 2 | 3 | L1 | A1 | 0.0 |
| 1689697 | 17 | M | Pfizer | 2 | 4 | L4 | UC | 0.0 |
| 1705028 | 18 | M | Pfizer | 1 | 2 | L3 | A1 | 0.0 |

### 4.2 Myocarditis — G2 Confounder (N=30)

| VAERS ID | Age | Sex | Vaccine | Dose | Onset (d) | Brighton | WHO | NCI | Confounder |
|----------|-----|-----|---------|------|-----------|----------|-----|-----|------------|
| 983362 | 25 | F | Moderna | 1 | 5 | L2 | A1 | 0.35 | Viral etiology |
| 1219721 | 44 | M | Moderna | 2 | 3 | L2 | A1 | 0.0 | Viral etiology |
| 1259694 | 69 | F | Pfizer | UNK | 13 | L1 | C | 0.0 | Rheumatoid |
| 1296631 | 71 | F | Moderna | UNK | 5 | L1 | A1 | 0.0 | Cancer |
| 1313197 | 63 | F | Pfizer | 1 | 4 | L4 | UC | 0.0 | Rheumatoid |
| 1326494 | 17 | M | Pfizer | 2 | 1 | L2 | A1 | 0.3 | Viral etiology |
| 1327571 | 16 | M | Pfizer | 2 | 0 | L4 | UC | 0.0 | Viral etiology |
| 1341730 | 18 | M | Pfizer | UNK | 1 | L3 | A1 | 0.0 | Viral etiology |
| 1349546 | 22 | M | Pfizer | 2 | -4 | L4 | UC | 0.0 | Viral etiology |
| 1354460 | 19 | M | Pfizer | UNK | 3 | L3 | A1 | 0.0 | Lithium |
| 1382634 | 13 | F | Pfizer | 2 | 1 | L3 | A1 | 0.0 | Viral etiology |
| 1394458 | 25 | M | Pfizer | 2 | 17 | L4 | UC | 0.0 | COVID-19 positive |
| 1395737 | 15 | M | Pfizer | 2 | 20 | L3 | A1 | 0.0 | Viral etiology |
| 1412506 | UNK | M | Pfizer | 2 | UNK | L1 | A1 | 0.2 | Viral etiology |
| 1430395 | 14 | M | Pfizer | 2 | 3 | L2 | B2 | 0.4 | Viral etiology |
| 1437909 | 49 | F | Moderna | 2 | 0 | L3 | C | 1.0 | Cancer |
| 1464028 | 28 | M | Moderna | 1 | 54 | L2 | C | 0.0 | Viral etiology |
| 1482907 | UNK | M | Pfizer | 2 | UNK | L1 | A1 | 0.0 | Viral etiology |
| 1482909 | UNK | M | Pfizer | 2 | UNK | L1 | A1 | 0.0 | Viral etiology |
| 1489813 | 64 | M | Pfizer | 1 | 0 | L1 | B2 | 0.4 | Viral etiology |
| 1490549 | 47 | F | Moderna | 2 | 1 | L3 | C | 0.8 | COVID-19 positive |
| 1498145 | 18 | M | Pfizer | 2 | 42 | L3 | C | 0.4 | Viral etiology |
| 1499689 | 35 | M | Pfizer | 1 | 23 | L2 | C | 0.2 | Viral etiology |
| 1591514 | 30 | M | Moderna | 1 | 3 | L4 | UC | 0.0 | Cancer |
| 1592056 | 59 | F | Pfizer | 2 | 0 | L3 | A1 | 0.0 | Viral + Rheumatoid |
| 1636617 | 12 | M | Pfizer | 2 | 3 | L3 | A1 | 0.0 | Viral etiology |
| 1645372 | 51 | F | Moderna | 1 | 14 | L4 | UC | 0.0 | Cancer |
| 1708522 | 16 | M | Pfizer | 2 | 1 | L1 | A1 | 0.0 | Viral etiology |
| 1793549 | 37 | M | Moderna | 1 | 1 | L3 | A1 | 0.35 | COVID-19 positive |
| 1795077 | 63 | F | Moderna | 1 | 1 | L4 | UC | 0.0 | Cancer |

### 4.3 Myocarditis — G3 Severe (N=30)

| VAERS ID | Age | Sex | Vaccine | Dose | Onset (d) | Brighton | WHO | NCI | Severity Indicator |
|----------|-----|-----|---------|------|-----------|----------|-----|-----|--------------------|
| 1088210 | 46 | F | Pfizer | 1 | 18 | L4 | UC | 0.0 | ECMO; Impella; Fulminant |
| 1090794 | 20 | F | Pfizer | 2 | 12 | L2 | B2 | 0.4 | Severe (unspecified) |
| 1105807 | 21 | F | Moderna | 2 | 1 | L3 | A1 | 0.0 | EF 45% |
| 1262397 | 16 | M | Pfizer | 2 | 3 | L2 | A1 | 0.0 | Heart block |
| 1263276 | 29 | M | Pfizer | 2 | 50 | L1 | C | 1.0 | VT |
| 1280493 | 16 | M | Pfizer | 2 | 0 | L1 | A1 | 0.35 | EF 50% |
| 1286607 | 35 | M | Pfizer | 2 | 0 | L1 | A1 | 0.0 | EF 55% |
| 1299305 | UNK | U | Pfizer | 2 | UNK | L1 | A1 | 0.0 | EF 52% |
| 1343980 | 22 | M | Janssen | 1 | 26 | L3 | C | 0.8 | EF 30% |
| 1347846 | 31 | M | Moderna | 2 | 3 | L1 | C | 0.8 | EF 34% |
| 1350637 | 16 | M | Pfizer | 2 | 1 | L1 | A1 | 0.0 | Heart block |
| 1350946 | 26 | M | Pfizer | 2 | 1 | L1 | C | 0.8 | EF 51% |
| 1354522 | 38 | F | Pfizer | 2 | 3 | L1 | A1 | 0.0 | EF 60% |
| 1357322 | 29 | M | Pfizer | 2 | 41 | L4 | UC | 0.0 | ECMO; Cardiogenic shock |
| 1423060 | 22 | M | Moderna | 2 | UNK | L1 | UC | 0.5 | VT |
| 1474640 | 23 | M | Moderna | 2 | 3 | L3 | A1 | 0.0 | EF 57% |
| 1499676 | 26 | M | Moderna | 2 | 33 | L3 | C | 0.0 | EF 52% |
| 1515244 | 27 | F | Janssen | UNK | 59 | L4 | UC | 0.0 | ECMO; Fulminant |
| 1592526 | 15 | F | Pfizer | 2 | 3 | L3 | A1 | 0.2 | EF 64% |
| 1645384 | 66 | F | Moderna | 1 | 77 | L4 | UC | 0.0 | ECMO; Cardiac arrest; Cardiogenic shock |
| 1661275 | UNK | F | Pfizer | 1 | UNK | L3 | C | 1.0 | ECMO; Fulminant; EF 15% |
| 1666411 | 71 | M | Pfizer | 2 | 37 | L3 | C | 0.0 | VT |
| 1692252 | UNK | M | Pfizer | 1 | UNK | L3 | C | 0.5 | VT |
| 1704121 | 26 | M | Pfizer | UNK | 1 | L2 | A1 | 0.0 | EF 40% |
| 1712137 | 57 | F | Moderna | 1 | 3 | L4 | UC | 0.0 | Heart block; VT |
| 1735422 | 27 | F | Pfizer | 1 | 13 | L4 | UC | 0.0 | Inotropes; VF; Cardiac arrest; Cardiogenic shock |
| 1740551 | 44 | M | Moderna | 1 | 4 | L1 | A1 | 0.0 | EF 40% |
| 1790502 | 38 | F | Moderna | 1 | UNK | L4 | UC | 0.0 | VT |
| 1828901 | 17 | F | Pfizer | 2 | 36 | L2 | C | 1.0 | VT; Cardiac arrest; EF 40% |
| 1829441 | 63 | M | Pfizer | 1 | 5 | L1 | C | 1.0 | Dobutamine; EF 35% |

### 4.4 Pericarditis (N=10)

| VAERS ID | Age | Sex | Vaccine | Dose | Onset (d) | Group | Brighton | WHO | NCI | Confounder |
|----------|-----|-----|---------|------|-----------|-------|----------|-----|-----|------------|
| 925542 | 30 | M | Pfizer | 1 | 4 | clean | L1 | C | 0.0 | — |
| 966794 | 55 | M | Moderna | 1 | 11 | clean | L1 | C | 0.0 | — |
| 977955 | 54 | M | Pfizer | 2 | 13 | clean | L1 | C | 0.0 | — |
| 1023768 | 86 | M | Moderna | 2 | 5 | confounded | L1 | C | 0.0 | Cancer |
| 1128543 | 41 | M | Moderna | 2 | 29 | clean | L1 | C | 0.0 | — |
| 1147729* | 18 | M | Pfizer | 2 | 2 | clean | L3 | A1 | 0.0 | — |
| 1314908 | 53 | F | Pfizer | 1 | 0 | confounded | L1 | C | 0.0 | SLE/Lupus |
| 1333796 | 81 | F | Pfizer | UNK | 5 | clean | L1 | C | 0.0 | — |
| 1361389 | 43 | F | Pfizer | UNK | 1 | clean | L1 | C | 0.0 | — |
| 1437261 | 64 | F | Moderna | 2 | 9 | confounded | L1 | C | 0.5 | SLE, Sjögren's, Cancer |

*VAERS 1147729: Tagged as pericarditis in cohort, but cardiac MRI excluded pericarditis and confirmed isolated myocarditis. Pipeline correctly reclassified via narrative analysis. Classified as A1 through the myocarditis pathway.

---

## 5. Benchmark Results Summary (v4.3)

### Overall WHO Category Distribution

| WHO Category | Count | % | Description |
|--------------|-------|---|-------------|
| A1 | 43 | 43% | Consistent with causal association |
| B2 | 5 | 5% | Indeterminate |
| C | 27 | 27% | Coincidental |
| Unclassifiable | 25 | 25% | Insufficient data (Brighton L4 early exit) |

### WHO Distribution by Group

| Group | A1 | B2 | C | UC | Total |
|-------|----|----|---|----|-------|
| G1 Classic | 16 | 2 | 2 | 10 | 30 |
| G2 Confounder | 15 | 2 | 6 | 7 | 30 |
| G3 Severe | 11 | 1 | 10 | 8 | 30 |
| Pericarditis clean | 1* | 0 | 6 | 0 | 7 |
| Pericarditis confounded | 0 | 0 | 3 | 0 | 3 |

*VAERS 1147729 reclassified as myocarditis by pipeline.

### Key Observations

1. **Data Quality Gating (24% early exit):** 24 cases with Brighton L4 correctly routed to Unclassifiable, preventing speculative causality assessment on insufficient data.

2. **Alternative Etiology Detection:** 27 cases identified with plausible alternative causes (NCI > 0). 14 of 27 C classifications were NCI-driven; 13 were temporal-driven.

3. **Severity ≠ Causality:** G3 cases show the highest C rate (33%) because severe presentations (ECMO, VT, cardiac arrest) suggest non-vaccine etiologies (GCM, fulminant viral) rather than typically mild vaccine-induced myocarditis.

4. **Pericarditis Pathway Validated:** 9/10 pericarditis cases correctly classified as C due to INSUFFICIENT evidence level. The one A1 (1147729) was correctly reclassified as myocarditis.

5. **Bridging Symptom Guidance:** Cases in the background rate zone (22–42 days) receive CRITICAL-priority bridging symptom queries — e.g., VAERS 1499676 (Day 33, NCI 0.0) classified as C but with actionable guidance to verify earlier symptom onset.

### Demographics Summary

| Metric | Value |
|--------|-------|
| Age | Mean 30.4, Median 22.5, Range 12–86 |
| Sex | Male 73%, Female 26%, Unknown 1% |
| Onset | Mean 8.6 days, Median 3.0 days |
| Vaccine | Pfizer 71%, Moderna 27%, Janssen 2% |
| Brighton L1 | 29 cases |
| Brighton L2 | 16 cases |
| Brighton L3 | 31 cases |
| Brighton L4 | 24 cases |

---

## 6. Regulatory & Scientific Framework

| Standard | Application in Vax-Beacon |
|----------|--------------------------|
| WHO AEFI Causality Assessment (2019) | Core decision algorithm (Q1–Q5 decision tree) |
| Brighton Collaboration | Diagnostic certainty levels (L1–L4) for myocarditis/pericarditis |
| NAM 2024 Evidence Review | Established AE evidence level, mechanistic windows (0–7d strong, 8–21d plausible, 22–42d background) |
| Nordic Cohort Data | Domain-specific clinical pattern knowledge for DDx |

### Key Regulatory Distinctions

- **Myocarditis + mRNA vaccine:** ESTABLISHED causal association (NAM 2024) → eligible for A1 if temporal criteria met
- **Pericarditis + mRNA vaccine:** INSUFFICIENT evidence (NAM 2024) → defaults to C regardless of temporal proximity
- **Myocarditis + viral vector (Janssen):** No established causal pair in current registry → treated as unknown AE

---

*Document generated for Vax-Beacon v4.3 — Multi-Agent AEFI Causality Pipeline*
