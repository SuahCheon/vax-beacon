# Vax-Beacon v4.3 — Claude Code Instructions

## Project Overview

Vax-Beacon is a 6-stage multi-agent pipeline that evaluates causality of myocarditis/pericarditis from VAERS (Vaccine Adverse Event Reporting System) data. It implements the WHO AEFI causality assessment algorithm.

### v4 Core Design

1. **Stage 3 Two-Pass**: Observe(3A) → Match(3B) → Assess(3C) → Calculate(3D), 2 LLM calls + 2 Code steps
2. **Stage 5 Deterministic**: Code classifies via decision tree, LLM only explains
3. **Knowledge DB**: Domain knowledge in JSON (`knowledge/`), LLM references at runtime
4. **Stage 2 Pending Override (v4.3)**: Tests that were ordered but not completed → not treated as positive
5. **Brighton L4 Early Exit**: Insufficient diagnostic evidence → Unclassifiable with structured guidance
6. **Report Renderer**: Code-only Markdown/Word report generation (no LLM)
7. **Interactive Mode**: `python main.py -i` for guided case selection

---

## Architecture

```
Stage 1 (LLM)     ICSR Extractor — narrative → structured JSON
Stage 2 (Code)     Brighton Validator — L1-L4 + pending-test override
                   ├─ L1-L3: Full Pipeline
                   │  Stage 3A (LLM)   Clinical Observer (open-ended, category-grouped)
                   │  Stage 3B (Code)   DDx Matcher (keyword matching vs Knowledge DB)
                   │  Stage 3C (LLM)   Plausibility Assessor (focused on matched markers only)
                   │  Stage 3D (Code)   NCI Calculator (deterministic scoring)
                   │  Stage 4  (Code)   Auditor — Known AE + Temporal (NAM 2024)
                   │  Stage 5  (Code+LLM) Causality Assessor
                   └─ L4: Early Exit → Stage 6 directly
Stage 6 (LLM+DB)  Guidance Advisor — investigation protocols from Knowledge DB
Report  (Code)     Markdown/Word report renderer (no LLM)
```

---

## File Structure

```
vax-beacon/
├── main.py                    # Pipeline orchestrator + interactive mode
├── config.py                  # Constants, thresholds, API config
├── llm_client.py              # Swappable LLM backend (Anthropic → MedGemma)
├── data_loader.py             # VAERS CSV parsing
├── knowledge_loader.py        # Knowledge DB loader
├── report_renderer.py         # Markdown/Word report generator (no LLM)
│
├── pipeline/
│   ├── stage1_icsr_extractor.py
│   ├── stage2_clinical_validator.py   # Includes _is_pending_status() override
│   ├── stage3a_clinical_observer.py   # LLM: open-ended observation
│   ├── stage3b_ddx_matcher.py         # Code: keyword matching
│   ├── stage3c_plausibility.py        # LLM: plausibility assessment
│   ├── stage3d_nci_calculator.py      # Code: NCI scoring + merge_stage3()
│   ├── stage4_auditor.py
│   ├── stage5_causality_assessor.py   # Code: classify() + LLM: explain
│   ├── stage6_guidance_advisor.py     # LLM+DB: normal + brighton_exit + onset_unknown
│   └── _legacy/                       # Historical v3 code (do not modify)
│
├── prompts/
│   └── system_prompts.py              # All LLM system prompts
│
├── knowledge/
│   ├── ddx_myocarditis.json           # 7 DDx subtypes with weighted indicators
│   └── investigation_protocols.json   # Etiology-specific investigation sequences
│
├── data/
│   └── vaers_100_cohort.csv           # Curated 100-case dataset
│
├── results/                           # Pipeline outputs (committed: v30, v31, v4.3)
├── reports/                           # Generated case reports (.md, .docx) — gitignored
├── scripts/                           # Dev scripts, comparison tools, execution plans
└── docs/                              # Reference materials & schema
```

---

## Key Implementation Details

### Stage 2: Brighton Validator
- `_is_pending_status()` detects "ordered", "pending", "not completed" etc. in free-text clinical fields
- Overrides `cardiac_mri_positive`, `ecg_abnormal`, `echo_abnormal` to `false` for pending tests
- `pending_overrides` field in output records which fields were overridden

### Stage 3: Two-Pass DDx
- 3A: Open-ended category-grouped observation (NOT a 38-marker checklist)
- 3B: Deterministic keyword matching against `ddx_myocarditis.json`
- 3C: LLM evaluates only matched markers (focused attention → improved reproducibility)
- 3D: Deterministic NCI calculation, narrative_nuance handling

### Stage 5: Deterministic Classification
- `classify()` function implements WHO decision tree (code only)
- LLM only generates `reasoning` for the already-decided classification
- Decision chain: Brighton → NCI threshold → Known AE → Temporal → WHO category

### Stage 6: Three Modes
- **Normal flow**: Full guidance with Knowledge DB protocol injection
- **Brighton exit** (`early_exit=True`): Structured guidance for L4 cases
- **Onset unknown**: Standardized Unclassifiable output

### Report Renderer
- `report_renderer.py`: Pure code, no LLM calls
- `render_report(result)` → Markdown file
- `render_docx(md_path)` → Word document (requires python-docx)
- Separate templates for full pipeline and early exit cases

### Interactive Mode
- `python main.py -i` launches guided CLI workflow
- Case selection: browse, VAERS ID, filter by group, filter by condition
- Post-pipeline: report format selection (MD / MD+DOCX / skip)

---

## CLI Usage

```bash
python main.py                        # Run all 100 cases
python main.py --case 1347846         # Single case
python main.py --case 1347846 --docx  # Single case + Word report
python main.py -i                     # Interactive mode
python main.py --group G2             # Group filter
python main.py --sample 2             # N cases per group
```

---

## Coding Rules

1. **Language:** All code, comments, docstrings, prompts, and output in English
2. **Encoding:** Explicit `encoding="utf-8"` on all file I/O
3. **Error Handling:** On error in any Stage, record in `result["errors"]` and continue
4. **Backward Compatibility:** Stage 3 output structure MUST match keys expected by Stage 4/5
5. **Legacy Preservation:** Old files go to `_legacy/`, never delete
6. **Determinism:** LLMs observe and reason; deterministic code computes and classifies

## Result File Locations

```
results/results_v30_100.json              # v3.0 100-case results
results/results_v31_100.json              # v3.1 100-case results
results/results_v4_full_100_20260216_215649.json  # v4.3 final 100-case results
```
