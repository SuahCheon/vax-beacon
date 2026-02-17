# Rename Stage 4 & Stage 5 Agents

## Overview

Rename two pipeline agents for consistency:
- Stage 4: "Temporal Auditor" → **"Auditor"** (Known AE + Temporal)
- Stage 5: "Causality Integrator" → **"Causality Assessor"**

Also standardize Stage 4 description order: Known AE first, then Temporal.

## CRITICAL: Do NOT change JSON result keys

The internal dict keys `stage4_temporal` and `stage5_causality` must remain unchanged everywhere. Only change:
- Filenames
- Import paths
- Display strings (print, comments, docstrings)
- Documentation

This preserves compatibility with existing result files and report_renderer.py parsing.

## Step 1: Rename Files

```bash
# Stage 4
mv pipeline/stage4_temporal_auditor.py pipeline/stage4_auditor.py

# Stage 5
mv pipeline/stage5_causality_integrator.py pipeline/stage5_causality_assessor.py
```

## Step 2: Update main.py

### Imports (change paths only)
```python
# OLD
from pipeline.stage4_temporal_auditor import run_stage4
from pipeline.stage5_causality_integrator import run_stage5

# NEW
from pipeline.stage4_auditor import run_stage4
from pipeline.stage5_causality_assessor import run_stage5
```

### Console output strings
```python
# OLD
print(f"  [Stage 4] Temporal+KnownAE Auditor (Rule)..."

# NEW
print(f"  [Stage 4] Auditor — Known AE + Temporal (Rule)..."
```

```python
# OLD
print(f"  [Stage 5] Causality Integrator (LLM)..."

# NEW
print(f"  [Stage 5] Causality Assessor (Code+LLM)..."
```

### Docstring/comments in main.py
Update the module docstring stage mapping:
```python
# OLD
Stage 4 (Rule) → Step 2: Known AE & Time [Temporal + Known AE]
Stage 5 (Code + LLM) → Step 3 & 4: Deterministic Classification + Explanation

# NEW
Stage 4 (Rule) → Step 2: Known AE + Temporal [Auditor]
Stage 5 (Code + LLM) → Step 3 & 4: Causality Assessment [Assessor]
```

Update any other comments referencing "Temporal Auditor" or "Causality Integrator".

### DO NOT change these dict keys:
- `result["stages"]["stage4_temporal"]` — keep as-is
- `result["stages"]["stage5_causality"]` — keep as-is

## Step 3: Update pipeline file docstrings

### pipeline/stage4_auditor.py (renamed file)
Update the module docstring at the top:
```python
# OLD
"""
Vax-Beacon v4 | Stage 4: Temporal Auditor (Rule-based)
...
"""

# NEW
"""
Vax-Beacon v4 | Stage 4: Auditor — Known AE + Temporal (Rule-based)
...
"""
```

### pipeline/stage5_causality_assessor.py (renamed file)
```python
# OLD
"""
Vax-Beacon v4 | Stage 5: Causality Integrator (Deterministic + LLM)
...
"""

# NEW
"""
Vax-Beacon v4 | Stage 5: Causality Assessor (Deterministic + LLM)
...
"""
```

## Step 4: Update prompts/system_prompts.py

Search for "Causality Integrator" and replace with "Causality Assessor".
Search for "Temporal Auditor" and replace with "Auditor".

Only change display text / role descriptions. Do NOT change any JSON schema keys or field names referenced in prompts.

## Step 5: Update report_renderer.py

Search for any display strings referencing old names:
- "Temporal Auditor" → "Auditor"
- "Causality Integrator" → "Causality Assessor"

Do NOT change the dict key access patterns like:
- `result["stages"]["stage4_temporal"]` — KEEP
- `result["stages"]["stage5_causality"]` — KEEP

## Step 6: Update README.md

Replace the stage table to match:
```
Stage 4  (Code)     Auditor — Known AE + Temporal
Stage 5  (Code+LLM) Causality Assessor
```

Ensure the 6-agent summary reads:
> Extractor → Validator → DDx Specialist → Auditor → Assessor → Advisor

## Step 7: Update CLAUDE.md

Same replacements as README. Ensure consistency.

## Step 8: Update assets/*.mermaid

If the mermaid diagrams reference "Temporal Auditor" or "Causality Integrator", update them.

## Step 9: Clean __pycache__

```bash
Remove-Item -Recurse -Force .\pipeline\__pycache__
Remove-Item -Recurse -Force .\__pycache__
Remove-Item -Recurse -Force .\prompts\__pycache__
```

## Step 10: Verify

```bash
# No old names in active code (exclude scripts/, _legacy/, results/)
grep -rn "Temporal Auditor\|temporal_auditor\|Causality Integrator\|causality_integrator" --include="*.py" --include="*.md" --include="*.mermaid" . | grep -v scripts/ | grep -v _legacy/ | grep -v results/ | grep -v __pycache__

# Should return 0 results

# Verify JSON keys are untouched
grep -rn "stage4_temporal\|stage5_causality" main.py report_renderer.py
# Should show dict key access patterns still intact

# Test
python main.py --case 1347846
python main.py --case 1313197
```

Both should run without import errors and display new agent names in console output.

## Step 11: Git commit

```bash
git add -A
git commit -m "rename: Stage 4 Auditor + Stage 5 Causality Assessor — filenames, display, docs"
```

## Summary

| What Changes | What Stays |
|-------------|------------|
| Filenames (2 files) | JSON keys (`stage4_temporal`, `stage5_causality`) |
| Import paths in main.py | Dict access patterns everywhere |
| Console print strings | Result file structure |
| Docstrings & comments | scripts/ execution plans |
| README, CLAUDE.md, mermaid | _legacy/ code |
| System prompt role text | report_renderer key parsing |
