# Full Refactoring: Vax-Beacon v4.3 — GitHub Ready

## Overview

Complete cleanup of the Vax-Beacon repository for public GitHub release. Covers file organization, .gitignore, README rewrite, dead code removal, and project structure alignment.

## CRITICAL: Work in order. Commit after each major step.

---

## Step 1: Delete Junk Files

```bash
# Windows artifact
del NUL

# Empty directory
rmdir agents
```

## Step 2: Clean results/ — Keep Only Final v4.3

Keep ONLY these files in `results/`:
- `results_v4_full_100_20260216_215649.json` (final v4.3 100-case run)
- `summary_v4_full_100_20260216_215649.csv` (corresponding summary)

Also keep for version comparison (rename for clarity):
- `results_v30_final.json.json` → rename to `results_v30_100.json`
- `results_v31.json.json` → rename to `results_v31_100.json`
- `summary_v30_final.csv.csv` → rename to `summary_v30_100.csv`
- `summary_v31.csv.csv` → rename to `summary_v31_100.csv`

Delete ALL other files in results/ (all intermediate dev runs, single-case tests, etc).

After cleanup, results/ should contain exactly 6 files:
```
results/
├── results_v30_100.json
├── results_v31_100.json
├── results_v4_full_100_20260216_215649.json
├── summary_v30_100.csv
├── summary_v31_100.csv
└── summary_v4_full_100_20260216_215649.csv
```

## Step 3: Move Dev Scripts to scripts/

Move these from root to `scripts/`:
```bash
move analyze_full_100.py scripts\
move analyze_g2.py scripts\
move compare_v1_v2.py scripts\
move compare_v30_v31.py scripts\
move compare_v30_v31_v4.py scripts\
move compare_v40_v41a.py scripts\
move compare_v41a_v41b.py scripts\
move compare_v41a_v41b_r2.py scripts\
move compare_v41b_r2_r3.py scripts\
move compare_v41b_r3_v42.py scripts\
move verify_results.py scripts\
```

Move execution plans from docs/ to scripts/:
```bash
move docs\v41_execution_plan.md scripts\
move docs\v41b_execution_plan.md scripts\
move docs\v41b_r2_run_instruction.md scripts\
move docs\v41b_r2_validation_report.md scripts\
move docs\v41b_r3_patch_plan.md scripts\
move docs\v42_execution_plan.md scripts\
move docs\v43_execution_plan.md scripts\
move docs\db_review_execution_plan.md scripts\
move docs\db_review_framework.md scripts\
```

## Step 4: Move Legacy Pipeline Code

```bash
move pipeline\stage3_ddx_specialist.py pipeline\_legacy\stage3_ddx_v3.py
```

This is the old v3 monolithic Stage 3 (replaced by 3A-3D in v4). Keep in _legacy for reference.

## Step 5: Clean reports/

Delete generated reports (they'll be regenerated):
```bash
del reports\VAERS_1313197_v4.md
del reports\VAERS_1347846_v4.md
```

Keep `reports/` as empty directory with a `.gitkeep`.

## Step 6: Update .gitignore

Replace the entire .gitignore with:

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/

# Environment
.env
.venv/
venv/

# IDE
.vscode/
.idea/
.claude/

# OS
Thumbs.db
.DS_Store
NUL

# Generated outputs
reports/*.md
reports/*.docx

# Keep results/ tracked but ignore future dev runs
# Only committed files: v30, v31, v4.3 final runs
```

## Step 7: Reorganize docs/

After moving execution plans to scripts/, docs/ should contain only reference materials:

```
docs/
├── schema.json                          # Pipeline data schema
├── HexaVax-MAPS_ AI for Vaccine Safety.pdf  # Original design doc (historical)
├── Estimating diagnostic uncertainty....pdf   # Reference paper
└── VigiBase_Resource Profile Update....pdf    # Reference paper
```

This is fine as-is. No changes needed.

## Step 8: Clean __pycache__

```bash
# Remove all pycache directories
for /d /r . %d in (__pycache__) do @if exist "%d" rd /s /q "%d"
```

## Step 9: Rewrite README.md

Replace README.md entirely with the following content. This reflects the actual v4.3 architecture:

````markdown
# Vax-Beacon: Multi-Agent AEFI Causality Pipeline

AI-powered WHO AEFI causality assessment for myocarditis/pericarditis following mRNA COVID-19 vaccination. Built for the MedGemma PoC — currently running on Anthropic Claude API with planned migration to MedGemma/Gemma on Kaggle.

## Architecture

6-stage pipeline with Brighton-level gating and deterministic classification:

```
Stage 1 (LLM)     ICSR Extractor — narrative → structured JSON
Stage 2 (Code)     Brighton Validator — diagnostic certainty L1-L4 + pending-test override
                   ┌─ L1-L3: Full Pipeline ──────────────────────────┐
                   │  Stage 3A (LLM)   Clinical Observer             │
                   │  Stage 3B (Code)  DDx Matcher (Knowledge DB)    │
                   │  Stage 3C (LLM)   Plausibility Assessor         │
                   │  Stage 3D (Code)  NCI Calculator                │
                   │  Stage 4  (Code)  Temporal + Known AE Auditor   │
                   │  Stage 5  (Code+LLM) Causality Integrator       │
                   └─────────────────────────────────────────────────┘
                   └─ L4: Early Exit → Stage 6 directly
Stage 6 (LLM+DB)  Guidance Advisor — investigation protocols from Knowledge DB
Report  (Code)     Markdown/Word report renderer (no LLM)
```

### Key Design Principles

- **Mechanism-first:** Biological plausibility windows (22-day threshold) over purely temporal associations
- **Observe vs. compute:** LLMs observe and reason; deterministic code computes and classifies
- **Data quality gating:** Brighton L4 Early Exit prevents classification on insufficient evidence
- **Knowledge-driven:** Externalized domain knowledge in JSON (ddx + investigation protocols)

## Quick Start

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="your-key"    # Windows: set ANTHROPIC_API_KEY=your-key

# Single case analysis
python main.py --case 1347846

# Single case + Word report
python main.py --case 1347846 --docx

# Interactive mode (guided case selection)
python main.py -i

# Batch: all 100 cases
python main.py

# Batch: by group or sample
python main.py --group G2
python main.py --sample 2
```

## Project Structure

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
│   ├── stage1_icsr_extractor.py      # LLM: narrative → structured data
│   ├── stage2_clinical_validator.py  # Code: Brighton levels + pending override
│   ├── stage3a_clinical_observer.py  # LLM: raw finding extraction
│   ├── stage3b_ddx_matcher.py        # Code: keyword matching vs Knowledge DB
│   ├── stage3c_plausibility.py       # LLM: biological plausibility assessment
│   ├── stage3d_nci_calculator.py     # Code: Numerical Causality Index
│   ├── stage4_temporal_auditor.py    # Code: temporal + known AE (NAM 2024)
│   ├── stage5_causality_integrator.py # Code+LLM: deterministic WHO classification
│   ├── stage6_guidance_advisor.py    # LLM+DB: investigation guidance
│   └── _legacy/                      # Historical v3 code
│
├── prompts/
│   └── system_prompts.py             # All LLM system prompts
│
├── knowledge/
│   ├── ddx_myocarditis.json          # 7 subtypes with weighted indicators
│   └── investigation_protocols.json  # Etiology-specific investigation sequences
│
├── data/
│   └── vaers_100_cohort.csv          # Curated 100-case dataset (90 myo + 10 peri)
│
├── results/                          # Pipeline outputs (JSON + CSV)
├── reports/                          # Generated case reports (.md, .docx)
├── scripts/                          # Dev analysis scripts & execution plans
├── tests/                            # Unit tests
└── docs/                             # Reference materials & schema
```

## Regulatory Framework

| Standard | Application |
|----------|-------------|
| WHO AEFI Causality Assessment (2019) | Core decision algorithm (Steps 1-4) |
| Brighton Collaboration Criteria | Diagnostic certainty levels L1-L4 |
| NAM 2024 Evidence Review | Known-AE status + temporal windows for mRNA vaccines |
| Numerical Causality Index (NCI) | Quantitative alternative etiology scoring (0.0-1.0) |

## Validation

100-case validation across pipeline versions:

| Metric | v3.0 | v3.1 | v4.3 |
|--------|------|------|------|
| A1 (Vaccine-related) | 21 | 30 | TBD |
| B2 (Indeterminate) | 29 | 16 | TBD |
| C (Coincidental) | 17 | 21 | TBD |
| NCI Drift cases | — | 5/100 | Target: 0 |

## Model Configuration

| Environment | Model | Usage |
|-------------|-------|-------|
| Local dev | Claude Sonnet 4.5 (Anthropic API) | Current prototype |
| Kaggle submission | MedGemma 4B / Gemma-2-9B | Planned migration |

Swap via `LLMClient(backend="medgemma")` in `llm_client.py`.

## License

[TBD]
````

## Step 10: Update CLAUDE.md

Read the current CLAUDE.md. Update it to reflect v4.3 architecture accurately:
- Stage 3 is now 3A-3D (not monolithic)
- Stage 5 is deterministic (code classifies, LLM reasons)
- Knowledge DB exists
- Report renderer exists
- Interactive mode exists
- File structure matches the new layout

Do NOT rewrite from scratch — update the existing content to be accurate.

## Step 11: Final Verification

```bash
# Check no HexaVax references remain (except docs/historical PDF)
grep -r "HexaVax" --include="*.py" --include="*.md" --include="*.json" --include="*.mermaid" . | grep -v results/ | grep -v _legacy/ | grep -v docs/HexaVax

# Check project structure matches README
dir /s /b *.py | findstr /v __pycache__ | findstr /v _legacy

# Test pipeline still works
python main.py --case 1347846
python main.py --case 1313197

# Check report generation
dir reports\

# Verify results/ has exactly 6 files
dir results\
```

## Step 12: Git Commit

```bash
git add -A
git commit -m "refactor: full cleanup for GitHub release — v4.3 structure, README rewrite, dev artifacts removed"
```

## Summary of Changes

| Action | Files |
|--------|-------|
| Deleted | NUL, agents/, 150+ intermediate result files, generated reports |
| Moved to scripts/ | 11 compare/analyze scripts, 9 execution plan docs |
| Moved to _legacy/ | stage3_ddx_specialist.py |
| Renamed | 4 result files (v30/v31 with .json.json → clean names) |
| Rewritten | README.md (full v4.3 architecture) |
| Updated | .gitignore, CLAUDE.md |
| Unchanged | All pipeline code, prompts, knowledge DB, data, config |
