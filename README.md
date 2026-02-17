# Vax-Beacon: Multi-Agent AEFI Causality Pipeline (PoC)

**Vax-Beacon** is an intelligent decision-support pipeline designed to enhance the quality of Causality Assessment for Adverse Events Following Immunization (AEFI). It acts as a bridge between the sophisticated insights of **High-Cost Active Surveillance** (e.g., Nordic Cohort Studies) and the practical needs of **Field-Level Passive Surveillance**.

## 🚀 Project Status: MedGemma Readiness
* **Current Core:** Anthropic Claude 3.5 Sonnet / Haiku (Hybrid Pipeline)
* **Target Environment:** Kaggle MedGemma Impact Challenge (Migration to MedGemma 27B/4B in progress)
* **Objective:** This system is architected to maximize the performance of medically-tuned LLMs like **MedGemma** through a **Tiered Intelligence** framework.

---

## 🛠 Architecture
Vax-Beacon digitalizes the WHO AEFI algorithm across a 6-stage pipeline, specializing in **Clinical Retro-reasoning** to improve data integrity at the source.

1.  **Stage 1 (Extractor):** Transforms unstructured narratives into structured JSON.
2.  **Stage 2 (Validator):** Determines **Brighton Levels L1-L4** using deterministic code.
    * *If L4 (Insufficient Evidence) is detected, the system triggers an **Early Exit** to Stage 6 for immediate investigation guidance.*
3.  **Stage 3 (DDx Engine):** Addresses **WHO Q1 (Alternative Etiology)**. Evaluates 7+ differential diagnoses to calculate a **Non-Causal Index (NCI)**.
4.  **Stage 4 (Auditor):** Analyzes temporal and mechanistic windows based on **NAM 2024** criteria.
5.  **Stage 5 (Assessor):** Determines final WHO Categories and generates clinical reasoning.
6.  **Stage 6 (Advisor):** Provides **Investigation Protocols** and **Bridging Symptom** guides for field officers.

---

## 📊 Validation Results (N=100)
Validated against 100 curated VAERS reports, Vax-Beacon demonstrates its role as a rigorous **Scientific Filter**:

* **Rigorous Filtering (24% Early Exit):** Successfully halted 24% of ineligible cases (L4) to prevent speculative reasoning and demand better field data.
* **Alternative Detection (27% Success):** Identified strong alternative etiologies in 27% of cases, significantly reducing misclassification risks.
* **Actionable Guidance (100% Issuance):** Generated tailored investigation protocols for every case to improve report quality.

### WHO Category Distribution
* **A1 (Consistent):** 43%
* **C (Coincidental):** 27%
* **Unclassifiable:** 25%
* **B2 (Indeterminate):** 5%

---

## 💡 Case Showcase: The "Beacon" in Action
An example of how Vax-Beacon guides field investigators to capture missing evidence.

> **Case ID: VAERS 1499676 (Myocarditis after Moderna 2nd dose)**
> * **Status:** Onset reported at **33 days** post-vaccination (Background Rate Zone).
> * **Vax-Beacon Guidance:**
>     > *"The reported onset (33 days) is outside the typical vaccine-induced window. Before excluding causality, **re-interview the reporter for any mild 'bridging symptoms' (e.g., mild chest pressure, palpitations, fatigue)** that may have occurred within the first 7 days post-vaccination. If symptoms during this gap are confirmed, the classification may be upgraded from 'Coincidental' to 'Consistent'."*
> * **Value:** Instead of a binary rejection, the AI identifies the **missing piece of the puzzle** required to establish a scientific link.

---

## 🧬 Regulatory & Scientific Framework
| Standard | Application |
| :--- | :--- |
| **WHO AEFI (2019)** | Core Decision Algorithm (Optimized for Myocarditis PoC) |
| **Brighton Collaboration** | Diagnostic Certainty Levels |
| **NAM 2024** | Mechanistic Windows & Established AE Evidence |
| **Nordic Cohort Data** | Domain-Specific Clinical Pattern Knowledge |

---

## 🔮 Future Roadmap: Tiered Intelligence with MedGemma
We are preparing for a full migration to the MedGemma ecosystem on Kaggle:
* **Heavy Reasoning:** **MedGemma 27B** (Powering Stage 3 DDx and Stage 5 Causality Synthesis)
* **Edge Guidance:** **MedGemma 4B** (Optimized for Stage 1 Parsing and Stage 6 Real-time Field Reporting)