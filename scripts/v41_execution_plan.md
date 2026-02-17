# Vax-Beacon v4.1 Execution Plan

**Created:** 2025-02-16
**Prerequisite:** v4.0 100-case results confirmed, three-way comparison complete
**Objective:** Temporal zone-aware investigation guidance in Stage 6

---

## Background

### Problem Identified During v4.0 Review

v4.0 Stage 6 generates investigation guidance based on:
1. Stage 3 DDx findings (what was found / not found)
2. Knowledge DB protocols (disease-specific tests)

But it does NOT account for **temporal zone**, which should significantly affect:
- **Scope** of investigation (how broadly to search for alternatives)
- **Type** of queries (bridging symptoms for late-onset cases)
- **Urgency framing** (standard confirmation vs active differentiation)

### Clinical Rationale

The same A1 classification at Day 3 vs Day 15 requires very different follow-up:
- **Day 3 (STRONG_CAUSAL):** Vaccine causation is strong. Just confirm basic diagnostics and exclude obvious confounders.
- **Day 15 (PLAUSIBLE):** Vaccine causation plausible but attenuated. Need active differentiation — viral panel regardless of prodromal symptoms, autoimmune markers at lower threshold, MRI for GCM/ischemic exclusion + myocardial involvement extent (NOT for vaccine vs viral pattern differentiation — Lake Louise cannot reliably distinguish these as both are lymphocytic).
- **Day 30 (BACKGROUND_RATE):** Beyond mechanistic threshold. Comprehensive alternative workup required. CRITICAL: verify bridging symptoms — patient may have had mild symptoms from Day 3 that worsened, which would shift actual onset into STRONG_CAUSAL window.
- **Day 50+ (UNLIKELY):** Vaccine causation nearly excluded. Focus on identifying actual cause. Verify onset accuracy.

### Key Insight: Bridging Symptoms

For BACKGROUND_RATE (22-42d) and UNLIKELY (>42d) cases, the single most impactful query is:
> "Were there any cardiac symptoms (chest pain, dyspnea, palpitations, fatigue) between vaccination date and formal diagnosis date?"

If bridging symptoms are confirmed from Day 0-7, the actual onset falls within STRONG_CAUSAL window, potentially reclassifying the case.

### Key Insight: MRI Limitations

Cardiac MRI (Lake Louise criteria) is strong for diagnosing myocarditis presence, but LIMITED for distinguishing vaccine-induced vs viral myocarditis — both are lymphocytic and produce overlapping LGE patterns. MRI is useful for:
- GCM exclusion (diffuse/patchy mid-wall pattern)
- Ischemic exclusion (subendocardial pattern)
- Myocardial involvement extent assessment
- NOT for "vaccine vs viral" pattern differentiation

Stage 6 guidance must frame MRI recommendations accurately.

---

## Phase 1: Stage 4 Enhancement (30 min)

### File: `pipeline/stage4_temporal_auditor.py`

Add `_build_investigation_guidance()` function and include its output in Stage 4 results.

#### New Function

```python
def _build_investigation_guidance(temporal_zone: str) -> dict:
    """
    Determine investigation intensity and focus based on temporal zone.
    
    This does NOT specify individual tests — that is Stage 6's job,
    which combines this guidance with Stage 3's actual findings/gaps.
    """
    if temporal_zone == "STRONG_CAUSAL":
        return {
            "intensity": "STANDARD",
            "focus": "CONFOUNDING_EXCLUSION",
            "description": (
                "Strong causal window (0-7d). Standard diagnostics sufficient. "
                "Investigate alternative causes only if clinical indicators present."
            ),
            "query_requirements": {
                "bridging_symptoms": "NOT_REQUIRED",
                "infection_history": "IF_PRODROMAL_PRESENT",
                "medication_review": "STANDARD",
            }
        }
    elif temporal_zone == "PLAUSIBLE":
        return {
            "intensity": "ENHANCED",
            "focus": "ACTIVE_DIFFERENTIATION",
            "description": (
                "Plausible but attenuated window (8-21d). Active differentiation "
                "required — investigate alternative causes regardless of clinical "
                "indicators. Both vaccine causation and alternatives need substantiation."
            ),
            "query_requirements": {
                "bridging_symptoms": "NOT_REQUIRED",
                "infection_history": "REQUIRED",
                "medication_review": "REQUIRED",
                "symptom_evolution": "RECOMMENDED",
            }
        }
    elif temporal_zone == "BACKGROUND_RATE":
        return {
            "intensity": "COMPREHENSIVE",
            "focus": "ALTERNATIVE_IDENTIFICATION",
            "description": (
                "Beyond mechanistic threshold (22-42d). Comprehensive alternative "
                "workup required. Bridging symptom verification is CRITICAL — "
                "may shift actual onset into causal window."
            ),
            "query_requirements": {
                "bridging_symptoms": "CRITICAL",
                "bridging_symptom_detail": (
                    "Query reporter: Were there ANY cardiac symptoms (chest pain, "
                    "dyspnea, palpitations, exercise intolerance, unusual fatigue) "
                    "between vaccination and formal diagnosis? If symptoms began "
                    "within 0-7 days post-vaccination, actual onset may fall within "
                    "STRONG_CAUSAL window, warranting temporal reclassification."
                ),
                "infection_history": "REQUIRED",
                "medication_review": "REQUIRED",
                "baseline_disease_change": "REQUIRED",
            }
        }
    else:  # UNLIKELY or UNKNOWN
        return {
            "intensity": "COMPREHENSIVE",
            "focus": "ALTERNATIVE_IDENTIFICATION",
            "description": (
                "Outside plausible causal window (>42d). Vaccine causation highly "
                "unlikely. Focus on identifying actual cause. Verify onset date accuracy."
            ),
            "query_requirements": {
                "bridging_symptoms": "CRITICAL",
                "bridging_symptom_detail": (
                    "Query reporter: Verify actual first symptom date. Were there "
                    "ANY cardiac symptoms between vaccination and reported onset? "
                    "Accurate onset dating is essential for temporal assessment."
                ),
                "infection_history": "REQUIRED",
                "medication_review": "REQUIRED",
                "baseline_disease_change": "REQUIRED",
            }
        }
```

#### Output Change

Add to `temporal_assessment` in `run_stage4()` return value:

```python
"temporal_assessment": {
    # ... existing fields ...
    "investigation_intensity": guidance["intensity"],
    "investigation_focus": guidance["focus"],
    "investigation_description": guidance["description"],
    "query_requirements": guidance["query_requirements"],
}
```

#### Backward Compatibility
- New fields are additive — Stage 5 classify() does not use them (no logic change)
- Stage 5 reasoning LLM can reference them for richer explanation
- Stage 6 consumes them for guidance generation

### Verification
- Run `--case 1313197` (Day 2 → STRONG_CAUSAL → STANDARD intensity)
- Run a case with onset Day 10-15 → PLAUSIBLE → ENHANCED intensity  
- Run a case with onset Day 25+ → BACKGROUND_RATE → COMPREHENSIVE + bridging symptoms CRITICAL
- Verify Stage 4 output has new fields
- Verify Stage 5 classify() unchanged (same WHO categories as v4.0)

---

## Phase 2: Stage 5 Reasoning Enhancement (20 min)

### File: `pipeline/stage5_causality_integrator.py`

No change to `classify()`. Only change the LLM input to include investigation context for richer reasoning.

#### Change in `run_stage5()`

```python
combined_input = {
    # ... existing fields ...
    "investigation_context": {
        "intensity": temporal_data.get("temporal_assessment", {}).get("investigation_intensity"),
        "focus": temporal_data.get("temporal_assessment", {}).get("investigation_focus"),
        "description": temporal_data.get("temporal_assessment", {}).get("investigation_description"),
    }
}
```

#### Prompt Update: `prompts/system_prompts.py` STAGE5_CAUSALITY_INTEGRATOR

Add instruction for LLM to reference investigation_context in reasoning:

```
When explaining the classification, reference the investigation context:
- STANDARD intensity: Note that the strong temporal window supports causal inference
- ENHANCED intensity: Acknowledge that active differentiation is recommended
- COMPREHENSIVE intensity: Note that temporal relationship is weak and alternatives need investigation
Do NOT change the assigned classification based on this context.
```

### Verification
- Same 3 test cases
- Verify classify() output identical to v4.0
- Verify reasoning_summary references temporal context appropriately

---

## Phase 3: Stage 6 Temporal-Aware Guidance (1 hour)

### File: `pipeline/stage6_guidance_advisor.py`

This is the core change. Stage 6 now combines THREE inputs for investigation guidance:
1. **Stage 3 gaps** — what was found and what was not found
2. **Stage 4 intensity/focus** — how broadly to investigate
3. **Knowledge DB protocols** — disease-specific tests (already implemented in v4.0)

#### Logic

```python
def _run_normal(llm, icsr_data, brighton_data, ddx_data,
                temporal_data, causality_data, protocol):
    
    # Extract temporal investigation guidance (NEW in v4.1)
    temporal_assessment = temporal_data.get("temporal_assessment", {})
    intensity = temporal_assessment.get("investigation_intensity", "STANDARD")
    focus = temporal_assessment.get("investigation_focus", "CONFOUNDING_EXCLUSION")
    query_reqs = temporal_assessment.get("query_requirements", {})
    
    # Format temporal context for prompt injection
    temporal_context = _format_temporal_context(intensity, focus, query_reqs)
    
    # Build combined prompt with both protocol and temporal context
    prompt = STAGE6_GUIDANCE_ADVISOR.replace(
        "{protocol_context}", protocol_text
    ).replace(
        "{temporal_investigation_context}", temporal_context
    )
    
    # ... rest of LLM call ...
```

#### New Helper Function

```python
def _format_temporal_context(intensity: str, focus: str, query_reqs: dict) -> str:
    """Format temporal investigation guidance for prompt injection."""
    lines = [
        f"=== TEMPORAL INVESTIGATION CONTEXT ===",
        f"Investigation Intensity: {intensity}",
        f"Investigation Focus: {focus}",
        f"",
    ]
    
    if intensity == "STANDARD":
        lines.append(
            "The temporal relationship is strong (0-7 days). "
            "Focus on confirming basic diagnostics and excluding obvious confounders. "
            "Only recommend alternative-cause investigations if Stage 3 identified "
            "specific clinical indicators."
        )
    elif intensity == "ENHANCED":
        lines.append(
            "The temporal relationship is plausible but attenuated (8-21 days). "
            "Recommend active differentiation: viral panel regardless of prodromal "
            "symptoms, autoimmune markers at lower threshold, MRI for GCM/ischemic "
            "exclusion and myocardial involvement extent. Do NOT frame MRI as "
            "'vaccine vs viral pattern differentiation' — both are lymphocytic "
            "with overlapping patterns."
        )
    elif intensity == "COMPREHENSIVE":
        lines.append(
            "The temporal relationship is beyond the mechanistic threshold (22+ days). "
            "Recommend comprehensive alternative workup. All relevant tests from the "
            "DDx protocol should be recommended regardless of clinical indicators."
        )
    
    # Query requirements
    bridging = query_reqs.get("bridging_symptoms", "NOT_REQUIRED")
    if bridging == "CRITICAL":
        lines.append("")
        lines.append("CRITICAL QUERY — BRIDGING SYMPTOMS:")
        detail = query_reqs.get("bridging_symptom_detail", "")
        if detail:
            lines.append(detail)
        lines.append(
            "Include this as a CRITICAL-priority investigative gap. "
            "If bridging symptoms are confirmed, temporal reclassification may be warranted."
        )
    
    infection = query_reqs.get("infection_history", "")
    if infection == "REQUIRED":
        lines.append("")
        lines.append(
            "Query reporter about any infection episodes between vaccination and onset. "
            "Include as HIGH-priority gap."
        )
    
    lines.append("=== END TEMPORAL CONTEXT ===")
    return "\n".join(lines)
```

### Prompt Update: `prompts/system_prompts.py` STAGE6_GUIDANCE_ADVISOR

Add `{temporal_investigation_context}` placeholder and instructions:

```
{temporal_investigation_context}

RULES FOR TEMPORAL-AWARE GUIDANCE:
- Check Stage 3 findings BEFORE recommending tests. Do NOT recommend tests 
  for conditions already confirmed or excluded by Stage 3.
- Scale investigation scope to the temporal intensity level:
  - STANDARD: Only recommend tests for Stage 3-identified indicators
  - ENHANCED: Recommend tests even without specific Stage 3 indicators
  - COMPREHENSIVE: Recommend full workup + bridging symptom query
- When bridging_symptoms is CRITICAL, include it as the FIRST investigative gap
- Frame MRI recommendations as "GCM/ischemic exclusion + involvement extent",
  NOT as "vaccine vs viral pattern differentiation"
```

### Verification
- Test with cases from each temporal zone
- Verify STANDARD cases have fewer investigation recommendations than ENHANCED
- Verify COMPREHENSIVE cases include bridging symptom query as CRITICAL gap
- Verify MRI is framed correctly (not as vaccine vs viral differentiation)
- Verify no redundant recommendations (e.g., viral panel not recommended when Stage 3 already confirmed viral PCR)

---

## Phase 4: Integration Testing (1 hour)

### 4-1. Single Case Tests

```bash
# STRONG_CAUSAL case — expect STANDARD intensity, minimal extra investigations
python main.py --case 1286607

# PLAUSIBLE case — expect ENHANCED intensity, viral panel + autoimmune markers
# (identify a case with onset Day 8-21 from summary CSV)
python main.py --case <PLAUSIBLE_CASE>

# BACKGROUND_RATE case — expect COMPREHENSIVE + bridging symptoms CRITICAL
# (identify a case with onset Day 22+ from summary CSV)
python main.py --case <BACKGROUND_CASE>

# UNLIKELY case — expect COMPREHENSIVE + bridging symptoms CRITICAL
python main.py --case <UNLIKELY_CASE>
```

### 4-2. Full 100-Case Run

```bash
python main.py
```
→ `results/results_v41_full_100_<timestamp>.json`

### 4-3. v4.0 vs v4.1 Comparison

Create `compare_v40_v41.py`:
- WHO classification distribution (should be IDENTICAL — classify() unchanged)
- NCI scores (should be IDENTICAL — Stage 3 unchanged)
- Stage 6 output quality metrics:
  - Bridging symptom query rate for BACKGROUND_RATE/UNLIKELY cases (target: 100%)
  - MRI framing accuracy (no "vaccine vs viral" language)
  - Investigation scope correlation with temporal zone
  - Redundancy check (no tests recommended for already-confirmed findings)

### 4-4. Reproducibility Confirmation
- Run 1313197 three times → verify identical WHO category + identical investigation_intensity

---

## Modified Files Summary

| File | Change | Risk |
|---|---|---|
| `pipeline/stage4_temporal_auditor.py` | Add `_build_investigation_guidance()`, new output fields | LOW — additive only |
| `pipeline/stage5_causality_integrator.py` | Pass investigation_context to LLM input | LOW — classify() unchanged |
| `pipeline/stage6_guidance_advisor.py` | Consume temporal context, format and inject into prompt | MEDIUM — prompt change |
| `prompts/system_prompts.py` | Add temporal context placeholder + rules to Stage 5 and 6 prompts | MEDIUM — prompt change |
| `compare_v40_v41.py` | NEW — comparison script | NONE |

## Unchanged Files
- `pipeline/stage1_icsr_extractor.py` — no change
- `pipeline/stage2_clinical_validator.py` — no change
- `pipeline/stage3a_clinical_observer.py` — no change
- `pipeline/stage3b_ddx_matcher.py` — no change
- `pipeline/stage3c_plausibility.py` — no change
- `pipeline/stage3d_nci_calculator.py` — no change
- `knowledge/ddx_myocarditis.json` — no change
- `knowledge/investigation_protocols.json` — no change
- `knowledge_loader.py` — no change
- Stage 5 `classify()` decision tree — NO CHANGE (classification logic frozen)

## CLAUDE.md Update

After v4.1 implementation, update CLAUDE.md to reflect:
- Stage 4 output now includes investigation_intensity/focus/query_requirements
- Stage 6 consumes temporal context alongside protocol context
- MRI guidance framing policy

---

## Estimated Time

| Phase | Task | Time |
|---|---|---|
| 1 | Stage 4 enhancement | 30 min |
| 2 | Stage 5 reasoning | 20 min |
| 3 | Stage 6 temporal-aware guidance | 1 hour |
| 4 | Integration testing | 1 hour |
| **Total** | | **~2.5 hours** |
