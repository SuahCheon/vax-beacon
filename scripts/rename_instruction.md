# Rename Vax-Beacon → Vax-Beacon

The project is being renamed from "Vax-Beacon" to "Vax-Beacon". 
Full name: "Vax-Beacon: Multi-Agent AEFI Causality Pipeline"

## Scope

Rename all references in code, docs, prompts, and configs. Do NOT rename result files or legacy files — only source code and documentation.

## Step 1: Clean __pycache__

```
Remove-Item -Recurse -Force .\__pycache__, .\pipeline\__pycache__, .\prompts\__pycache__
```

## Step 2: Source Code — String Replacements

Apply these replacements across ALL files listed below:

| Old | New |
|-----|-----|
| `Vax-Beacon` | `Vax-Beacon` |
| `vax-beacon` | `vax-beacon` |
| `Vax_Beacon` | `Vax_Beacon` |
| `vax_beacon` | `vax_beacon` |
| `VAX_BEACON` | `VAX_BEACON` |

### Files to update (check each one):

**Core:**
- `main.py` — version string, print statements, banner
- `config.py` — any project name references
- `CLAUDE.md` — all mentions
- `README.md` — title, description, all mentions

**Pipeline:**
- `pipeline/stage1_icsr_extractor.py`
- `pipeline/stage2_clinical_validator.py`
- `pipeline/stage3a_clinical_observer.py`
- `pipeline/stage3b_ddx_matcher.py`
- `pipeline/stage3c_plausibility.py`
- `pipeline/stage3d_nci_calculator.py`
- `pipeline/stage3_ddx_specialist.py`
- `pipeline/stage4_temporal_auditor.py`
- `pipeline/stage5_causality_integrator.py`
- `pipeline/stage6_guidance_advisor.py`

**Prompts:**
- `prompts/system_prompts.py` — all system prompt strings

**Support:**
- `llm_client.py`
- `data_loader.py`
- `knowledge_loader.py`

**Docs:**
- `docs/v43_execution_plan.md`
- `docs/v42_execution_plan.md`
- `docs/v41_execution_plan.md`
- `docs/v41b_execution_plan.md`
- `scripts/v4_execution_plan.md`
- `scripts/RUN_INSTRUCTIONS.md`

**Assets:**
- `assets/architecture_detailed.mermaid`
- `assets/architecture_pipeline.mermaid`

**Comparison scripts (headers/comments only, not result filenames):**
- `compare_v30_v31.py`
- `compare_v30_v31_v4.py`
- `compare_v40_v41a.py`
- `compare_v41a_v41b.py`
- `compare_v41a_v41b_r2.py`
- `compare_v41b_r2_r3.py`
- `compare_v41b_r3_v42.py`
- `analyze_full_100.py`
- `analyze_g2.py`
- `verify_results.py`

## Step 3: Do NOT Rename

- `results/` folder contents — keep all result filenames as-is for traceability
- `pipeline/_legacy/` — keep as historical reference
- `.env` — keep as-is
- `data/vaers_100_cohort.csv` — keep as-is

## Step 4: Knowledge DB check

- `knowledge/ddx_myocarditis.json` — check if version field contains old name
- `knowledge/investigation_protocols.json` — same check

## Step 5: Verify

After all replacements:
```bash
grep -r "HexaVax" --include="*.py" --include="*.md" --include="*.json" --include="*.mermaid" . | grep -v results/ | grep -v _legacy/ | grep -v __pycache__/
```
This should return 0 results (excluding results/ and _legacy/).

## Step 6: Test

```bash
python main.py --case 1347846
```
Verify the output runs without errors and prints "Vax-Beacon" in the banner/summary.

## Step 7: Git commit

```bash
git add -A
git commit -m "rename: Vax-Beacon → Vax-Beacon across entire codebase"
```
