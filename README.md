# Vax-Beacon: Multi-Agent AEFI Causality Pipeline (PoC)

**Vax-Beacon** is an intelligent decision-support pipeline designed to enhance the quality of Causality Assessment for Adverse Events Following Immunization (AEFI). It acts as a bridge between the sophisticated insights of **High-Cost Active Surveillance** (e.g., Nordic Cohort Studies) and the practical needs of **Field-Level Passive Surveillance**.

## Project Status: Dual-Backend (Claude + MedGemma 4B)
* **Cloud Backend:** Anthropic Claude 3.5 Sonnet / Haiku (API)
* **Local Backend:** Google MedGemma 4B (`google/medgemma-1.5-4b-it`, 4-bit quantization, ~3.2 GB VRAM)
* **Architecture:** Hybrid Code+LLM pipeline — LLMs observe and reason, deterministic code computes and classifies

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

## Validation Results (N=100)
Validated against 100 curated VAERS reports (myocarditis/pericarditis cohort).

### Claude 3.5 Sonnet (Cloud API)
| WHO Category | Cases | % |
|:---|:---|:---|
| A1 (Consistent) | 41 | 41% |
| C (Coincidental) | 27 | 27% |
| Unclassifiable | 25 | 25% |
| B2 (Indeterminate) | 5 | 5% |
| Error | 2 | 2% |

### MedGemma 4B (Local, 4-bit quantization)
98/100 cases completed (2 timeout). Results: `results/benchmark_medgemma_final.csv`

| WHO Category | Cases | % |
|:---|:---|:---|
| Unclassifiable | 47 | 48% |
| A1 (Consistent) | 21 | 21% |
| C (Coincidental) | 21 | 21% |
| B2 (Indeterminate) | 9 | 9% |

**Agreement rate:** 54.1% (Claude vs MedGemma on matched 98 cases).
MedGemma classifies more conservatively, especially on data-sparse cases (temporal zone UNKNOWN).

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

## Local Execution (MedGemma 4B)

### Requirements
* Python 3.10+, CUDA-capable GPU (6+ GB VRAM recommended)
* Hugging Face access token with MedGemma model agreement

### Setup
```bash
pip install -r requirements.txt
```

### Run
```bash
# Windows
set HF_TOKEN=hf_your_token_here
python main.py --backend medgemma                     # All 100 cases
python main.py --backend medgemma --case 1347846      # Single case
python main.py --backend medgemma --resume            # Resume interrupted batch
python main.py -i                                     # Interactive mode

# Linux/Mac
HF_TOKEN=hf_your_token_here python main.py --backend medgemma
```

### MedGemma Hybrid Architecture
MedGemma 4B uses a Code+LLM hybrid approach to compensate for the smaller model size:

* **Stage 1:** Code extracts structured VAERS fields (demographics, vaccine, timeline); LLM only analyzes narrative for clinical data. Keyword fallback catches abbreviations (cTnI, TTE, CMR, LGE, etc.)
* **Stage 2:** Fully deterministic Brighton classification with enhanced string logic (positive ECG/MRI findings override "normal sinus rhythm" phrases)
* **Stage 3A:** LLM generates open-ended clinical observations (category-grouped)
* **Stage 3B-3D:** Deterministic DDx matching and NCI scoring
* **Stage 5:** Code classifies via WHO decision tree; LLM only generates reasoning narrative
* **Stage 6:** Code-only guidance templates with Knowledge DB injection (no LLM for MedGemma)

### Known Limitations
* ~2% timeout rate on long literature-series narratives (>4000 words)
* Higher Unclassifiable rate vs Claude due to conservative temporal zone classification
* Context window limitations on MedGemma 4B (~8K tokens effective)