# Vax-Beacon Execution Plans: v4.1a → v4.1b → v4.2

**Created:** 2026-02-16
**Prerequisite:** v4.0 baseline confirmed (SCAD patch + Stage 2 "negative" patch applied, 100-case results verified)

---
---

# v4.1a — Classification Logic Fixes

**Objective:** Fix onset extraction gaps + handle UNKNOWN onset correctly
**Impact:** WHO classification changes expected
**Baseline:** v4.0 100-case results

## Pre-Execution (EVERY phase)
```bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; echo "pycache cleaned"
```

---

### Phase 1: Stage 1 Onset Extraction Enhancement (~40 min)

#### File: `prompts/system_prompts.py` — STAGE1_ICSR_EXTRACTOR

**Problem:** Stage 1 prompt says "NEVER fill in data that is not explicitly stated." This causes LLM to miss onset dates expressed as relative terms ("3 days after", "about a week later") even though these are explicitly stated — just not as calendar dates.

**Fix:** Add onset-specific extraction rules to Stage 1 prompt:

```
ONSET DATE EXTRACTION RULES:
- Explicit date ("symptoms started 5/17/2021") → onset_date = "2021-05-17"
- Relative expression with specific number ("3 days after vaccination") 
  → days_to_onset = 3, onset_date = calculate from vaccination_date if available
- Relative expression with approximate number ("about a week later", "approximately 2 weeks")
  → days_to_onset = best estimate (7, 14), onset_approximate = true
- Vague expression ("shortly after", "some time later") 
  → days_to_onset = null, onset_date = null, onset_approximate = null
- No mention of timing → days_to_onset = null, onset_date = null

When both VAERS structured fields (ONSET_DATE, NUMDAYS) AND narrative contain 
timing information, prefer the MORE SPECIFIC source. If VAERS fields are empty 
but narrative contains timing, extract from narrative.
```

**Add field to ICSR schema:**
```json
"event": {
    "onset_date": "<YYYY-MM-DD or null>",
    "days_to_onset": "<float or null>",
    "onset_approximate": "<true/false/null>",
    ...
}
```

#### File: `pipeline/stage4_temporal_auditor.py`

**Consume `onset_approximate`:** When onset_approximate=true, add flag:
```python
if event.get("onset_approximate"):
    flags.append("APPROXIMATE_ONSET: Onset date estimated from narrative, verify exact date")
```

This flag flows to Stage 5 reasoning and Stage 6 guidance without changing classification logic.

#### Verification
```bash
# Test with cases that have narrative-only onset info
python main.py --case 1790502   # "after second dose" — still early exit (Brighton L4)
python main.py --case 1423060   # Check if onset is extractable from narrative
```
- Check Stage 1 output for `onset_approximate` field
- Check Stage 4 for APPROXIMATE_ONSET flag where applicable

---

### Phase 2: Stage 5 Decision Tree — UNKNOWN Onset Path (~30 min)

#### File: `pipeline/stage5_causality_integrator.py`

**Change `classify()` — add Rule 1.5:**

```python
def classify(brighton_level, max_nci, known_ae, temporal_met, temporal_zone,
             who_step1_conclusion, epistemic_uncertainty=0.0):
    dc = { ... }  # existing

    # Rule 0: Brighton L4 → Unclassifiable
    if brighton_level > 3:
        return "Unclassifiable", dc

    # Rule 1: Definite alternative → C (even without onset date)
    if max_nci >= 0.7:
        dc["q2_definite_other_cause"] = True
        return "C", dc

    # NEW Rule 1.5: Onset unknown → Unclassifiable
    if temporal_zone == "UNKNOWN":
        dc["onset_unknown"] = True
        return "Unclassifiable", dc

    # Rules 2-4: unchanged
    ...
```

**Rationale:**
- NCI ≥ 0.7 → C regardless of onset (definite other cause is definite)
- All other UNKNOWN onset → Unclassifiable (temporal assessment is essential for WHO AEFI)
- This does NOT early-exit; Stages 3-6 all run, Stage 6 provides onset query guidance

#### File: `prompts/system_prompts.py` — STAGE5_CAUSALITY_INTEGRATOR

Add to prompt:
```
When the assigned classification is Unclassifiable due to unknown onset date:
- Explain that onset date is missing, making temporal assessment impossible
- Note which WHO categories would be possible once onset is known
- Do NOT change the assigned classification
```

#### Verification
```bash
python main.py --case 1286607   # A1 → still A1 (onset known)
python main.py --case 1313197   # C → still C (onset known)
python main.py --case 1423060   # UNKNOWN onset → check new behavior
```

---

### Phase 3: Unit Tests (~20 min)

#### File: `tests/test_classify.py` (NEW)

```python
from pipeline.stage5_causality_integrator import classify

def test_unknown_onset():
    """Onset unknown → Unclassifiable."""
    cat, dc = classify(3, 0.0, True, False, "UNKNOWN", "NO_ALTERNATIVE")
    assert cat == "Unclassifiable"
    assert dc["onset_unknown"] == True

    cat, dc = classify(3, 0.0, False, False, "UNKNOWN", "NO_ALTERNATIVE")
    assert cat == "Unclassifiable"

def test_unknown_onset_high_nci():
    """NCI >= 0.7 → C even with unknown onset."""
    cat, dc = classify(3, 0.8, True, False, "UNKNOWN", "DEFINITE_OTHER_CAUSE")
    assert cat == "C"

def test_brighton_l4():
    assert classify(4, 0.0, True, True, "STRONG_CAUSAL", "NO_ALTERNATIVE")[0] == "Unclassifiable"

def test_known_ae_strong_low_nci():
    assert classify(3, 0.0, True, True, "STRONG_CAUSAL", "NO_ALTERNATIVE")[0] == "A1"

def test_known_ae_strong_high_nci():
    assert classify(3, 0.5, True, True, "STRONG_CAUSAL", "POSSIBLE_OTHER_CAUSE")[0] == "B2"

def test_known_ae_unlikely():
    assert classify(3, 0.0, True, False, "UNLIKELY", "NO_ALTERNATIVE")[0] == "C"

def test_not_known_ae_temporal_low_nci():
    assert classify(3, 0.0, False, True, "STRONG_CAUSAL", "NO_ALTERNATIVE")[0] == "B1"

def test_not_known_ae_temporal_high_nci():
    assert classify(3, 0.5, False, True, "STRONG_CAUSAL", "POSSIBLE_OTHER_CAUSE")[0] == "B2"

def test_not_known_ae_no_temporal():
    assert classify(3, 0.0, False, False, "UNLIKELY", "NO_ALTERNATIVE")[0] == "C"

def test_nci_threshold():
    assert classify(3, 0.7, True, True, "STRONG_CAUSAL", "DEFINITE_OTHER_CAUSE")[0] == "C"

def test_determinism():
    results = set()
    for _ in range(10):
        cat, _ = classify(3, 0.35, True, True, "STRONG_CAUSAL", "WEAK_ALTERNATIVE")
        results.add(cat)
    assert len(results) == 1

if __name__ == "__main__":
    import sys
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        try:
            t()
            print(f"  PASS: {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL: {t.__name__} — {e}")
            sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
```

```bash
python tests/test_classify.py
```

---

### Phase 4: 100-Case Run + Comparison (~1.5 hours)

```bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
python main.py
```
→ `results/results_v41a_full_100_<timestamp>.json`

#### Create `compare_v40_v41a.py`:

**Compare:**
- WHO classification distribution (v4.0 vs v4.1a)
- Cases where WHO changed — list each with reason
- Onset extraction improvement: cases where `days_to_onset` was null in v4.0 but populated in v4.1a
- UNKNOWN onset cases: count before/after
- `onset_approximate` flag distribution

**Expected changes:**
- Some UNKNOWN onset cases may get onset extracted → classification changes
- Remaining UNKNOWN onset cases → Unclassifiable (instead of B2 or other)
- All cases with known onset → identical classification to v4.0

---

### v4.1a Modified Files

| File | Change | Risk |
|---|---|---|
| `prompts/system_prompts.py` | Stage 1 onset rules, Stage 5 UNKNOWN explanation | MEDIUM |
| `pipeline/stage5_causality_integrator.py` | classify() UNKNOWN path | **MEDIUM — classification change** |
| `pipeline/stage4_temporal_auditor.py` | APPROXIMATE_ONSET flag | LOW — additive |
| `tests/test_classify.py` | NEW | NONE |
| `compare_v40_v41a.py` | NEW | NONE |

### Unchanged
- Stage 2, Stage 3 (3A/3B/3C/3D), Stage 6, Knowledge DB, config.py, main.py, data_loader.py

### Estimated Time: ~3 hours

---
---

# v4.1b — Output Quality Improvement

**Objective:** Temporal-aware investigation guidance + MIS-C differentiation
**Impact:** WHO classification unchanged; Stage 5 reasoning + Stage 6 guidance quality improved
**Prerequisite:** v4.1a 100-case results confirmed
**Baseline:** v4.1a results

## Pre-Execution
```bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; echo "pycache cleaned"
```

---

### Phase 1: Stage 4 Temporal Investigation Guidance (~30 min)

#### File: `pipeline/stage4_temporal_auditor.py`

**Add `_build_investigation_guidance()`:**

```python
def _build_investigation_guidance(temporal_zone: str) -> dict:
    if temporal_zone == "STRONG_CAUSAL":
        return {
            "intensity": "STANDARD",
            "focus": "CONFOUNDING_EXCLUSION",
            "description": "Strong causal window (0-7d). Standard diagnostics sufficient. "
                           "Investigate alternatives only if clinical indicators present.",
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
            "description": "Plausible but attenuated window (8-21d). Active differentiation "
                           "required — investigate alternatives regardless of clinical indicators.",
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
            "description": "Beyond mechanistic threshold (22-42d). Comprehensive alternative "
                           "workup required. Bridging symptom verification CRITICAL.",
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
            "description": "Outside plausible causal window or onset unknown. "
                           "Comprehensive workup required. Verify onset date accuracy.",
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

**Add to `run_stage4()` output:**
```python
guidance = _build_investigation_guidance(temporal["temporal_zone"])

"temporal_assessment": {
    # ... existing fields ...
    "investigation_intensity": guidance["intensity"],
    "investigation_focus": guidance["focus"],
    "investigation_description": guidance["description"],
    "query_requirements": guidance["query_requirements"],
}
```

#### Verification
```bash
python main.py --case 1286607   # Day 0 → STANDARD
python main.py --case 1090794   # Day 12 → ENHANCED
python main.py --case 1499676   # Day 33 → COMPREHENSIVE
python main.py --case 1464028   # Day 54 → COMPREHENSIVE
```
- New fields in Stage 4 output
- Stage 5 classify() output identical to v4.1a

---

### Phase 2: Stage 5 Reasoning Enhancement (~20 min)

#### File: `pipeline/stage5_causality_integrator.py`

**No change to classify().** Only pass investigation_context to LLM:

```python
combined_input = {
    # ... existing ...
    "investigation_context": {
        "intensity": temporal_data.get("temporal_assessment", {}).get("investigation_intensity"),
        "focus": temporal_data.get("temporal_assessment", {}).get("investigation_focus"),
        "description": temporal_data.get("temporal_assessment", {}).get("investigation_description"),
    }
}
```

#### File: `prompts/system_prompts.py` — STAGE5_CAUSALITY_INTEGRATOR

Add:
```
When explaining the classification, reference the investigation context:
- STANDARD intensity: Note that the strong temporal window supports causal inference
- ENHANCED intensity: Acknowledge that active differentiation is recommended
- COMPREHENSIVE intensity: Note that temporal relationship is weak and alternatives need investigation
Do NOT change the assigned classification based on this context.
```

---

### Phase 3: Stage 6 Temporal-Aware + Gap-Aware Guidance (~1 hour)

#### File: `pipeline/stage6_guidance_advisor.py`

**Step 1:** Add `_format_temporal_context()` helper (formats intensity/focus/query_requirements for prompt injection)

**Step 2:** Update `_run_normal()` to extract temporal guidance from Stage 4 and inject into prompt:
```python
temporal_assessment = temporal_data.get("temporal_assessment", {})
intensity = temporal_assessment.get("investigation_intensity", "STANDARD")
focus = temporal_assessment.get("investigation_focus", "CONFOUNDING_EXCLUSION")
query_reqs = temporal_assessment.get("query_requirements", {})

temporal_context = _format_temporal_context(intensity, focus, query_reqs)
protocol_context = _format_protocol_context(protocol)

prompt = STAGE6_GUIDANCE_ADVISOR.replace(
    "{protocol_context}", protocol_context
).replace(
    "{temporal_investigation_context}", temporal_context
)
```

**Step 3:** Add `_run_onset_unknown()` for Unclassifiable (onset unknown) cases:
- NOT early exit — full pipeline data available
- Generate guidance with onset_verification as CRITICAL priority
- Include DDx-based gaps from Stage 3
- Explain which WHO categories become possible once onset is known

**Step 4:** Update `run_stage6()` routing:
```python
if early_exit:
    return _run_early_exit(...)

who_category = causality_data.get("who_category", "")
onset_unknown = (causality_data or {}).get("decision_chain", {}).get("onset_unknown", False)

if who_category == "Unclassifiable" and onset_unknown:
    return _run_onset_unknown(...)

return _run_normal(...)
```

#### File: `prompts/system_prompts.py`

**Add `{temporal_investigation_context}` placeholder to STAGE6_GUIDANCE_ADVISOR** + temporal-aware rules:
```
RULES FOR TEMPORAL-AWARE GUIDANCE:
- Check Stage 3 findings BEFORE recommending tests. Do NOT recommend tests 
  for conditions already confirmed or excluded by Stage 3.
- Scale investigation scope to temporal intensity:
  - STANDARD: Only recommend tests for Stage 3-identified indicators
  - ENHANCED: Recommend tests even without Stage 3 indicators
  - COMPREHENSIVE: Full workup + bridging symptom query
- When bridging_symptoms is CRITICAL, include as FIRST investigative gap
- Frame MRI as "GCM/ischemic exclusion + involvement extent",
  NOT "vaccine vs viral pattern differentiation"
```

**Add `STAGE6_ONSET_UNKNOWN` prompt:**
- Explains Unclassifiable reason (onset unknown)
- onset_verification as CRITICAL priority with specific query text
- DDx-based gaps from Stage 3 (still relevant even without temporal assessment)
- Possible WHO categories once onset is established

#### Verification
```bash
python main.py --case 1286607   # STRONG → STANDARD, minimal gaps
python main.py --case 1090794   # PLAUSIBLE → ENHANCED, broader gaps
python main.py --case 1499676   # BACKGROUND → COMPREHENSIVE + bridging CRITICAL
python main.py --case 1423060   # UNKNOWN → onset_verification CRITICAL
```
- STANDARD: fewer investigation gaps than ENHANCED
- COMPREHENSIVE: bridging symptom query as first gap
- UNKNOWN: onset_verification present + DDx gaps included
- No "vaccine vs viral" MRI framing

---

### Phase 4: MIS-C Differentiation (~30 min)

#### File: `knowledge/ddx_myocarditis.json`

Update `covid19_related` subtype:

**`mis_c_criteria_met` indicator — update `differentiation_guide`:**
```
"MIS-C can be triggered by BOTH SARS-CoV-2 infection AND mRNA vaccination. 
Key differentiators:
- Nucleocapsid antibody positive → prior infection (vaccination produces 
  only spike antibody) → infection-triggered MIS-C = alternative cause
- Nucleocapsid negative + recent vaccination → vaccine-triggered MIS-C-like 
  = vaccine causation
- Both vaccination AND infection history → requires clinical judgment
TRUE only if multi-system inflammatory syndrome criteria met (fever + 
multi-organ involvement + elevated inflammatory markers)."
```

**Add new indicator `sars_cov2_positive`** under `covid19_related`:
```json
{
    "finding": "sars_cov2_positive",
    "extraction_keywords": ["COVID positive", "SARS-CoV-2 positive", "PCR positive", 
                            "antigen positive", "COVID test positive", "nucleocapsid positive",
                            "COVID-19 confirmed"],
    "negative_keywords": ["COVID negative", "SARS negative", "PCR negative", 
                          "antigen negative", "no COVID", "COVID test negative"],
    "weight": 0.5,
    "differentiation_guide": "Confirmed SARS-CoV-2 infection provides an alternative 
        etiology for myocarditis (direct viral injury or post-infectious inflammation). 
        If both vaccination and infection are recent, this creates diagnostic ambiguity. 
        Nucleocapsid antibody testing can help differentiate: positive nucleocapsid 
        suggests natural infection, while vaccination produces only spike antibody."
}
```

#### File: `knowledge/investigation_protocols.json`

Add to `covid19_related` protocol investigations:
```json
{
    "test": "SARS-CoV-2 nucleocapsid antibody",
    "priority": "HIGH",
    "rationale": "Differentiates prior infection from vaccination-only exposure. Nucleocapsid antibody is produced only after natural infection, not after mRNA vaccination (which produces only spike antibody).",
    "indication": "When MIS-C or post-infectious myocarditis is suspected AND patient was recently vaccinated",
    "expected_finding": "Positive = prior infection likely contributed; Negative = vaccine-triggered more likely",
    "differential_from_vaccine": "Nucleocapsid-negative patient with recent vaccination and MIS-C presentation supports vaccine-triggered mechanism"
},
{
    "test": "MIS-C inflammatory panel (ferritin, D-dimer, fibrinogen, LDH)",
    "priority": "HIGH",
    "rationale": "MIS-C has distinctive inflammatory pattern: markedly elevated ferritin, D-dimer, and fibrinogen with lymphopenia",
    "indication": "Pediatric/young adult with multi-organ involvement post-vaccination or post-infection",
    "expected_finding": "Ferritin >500, D-dimer elevated, fibrinogen elevated with lymphopenia suggests MIS-C pattern",
    "differential_from_vaccine": "Vaccine myocarditis typically shows milder inflammatory markers without the MIS-C pattern of ferritin/D-dimer elevation"
}
```

#### Verification
```bash
python main.py --case 1501224   # MIS-C-like, check Stage 6 guidance
```
- Stage 6 should recommend nucleocapsid antibody testing
- officer_summary should explain MIS-C infection vs vaccine differentiation

---

### Phase 5: 100-Case Run + Comparison (~1.5 hours)

```bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
python main.py
```
→ `results/results_v41b_full_100_<timestamp>.json`

#### Create `compare_v41a_v41b.py`:

**Classification comparison:**
- WHO distribution: expect IDENTICAL to v4.1a (no classify() changes)
- NCI scores: may have minor changes if new `sars_cov2_positive` marker affects scoring
- If any WHO changed, investigate and explain

**Stage 6 quality metrics:**
- Bridging symptom query rate for BACKGROUND_RATE/UNLIKELY (target: 100%)
- MRI framing: scan for "vaccine vs viral" (target: 0 instances)
- Investigation scope: avg gap count STANDARD < ENHANCED < COMPREHENSIVE
- MIS-C cases: nucleocapsid antibody in recommendations (target: 100% of MIS-C suspects)
- Onset unknown: onset_verification field present

---

### v4.1b Modified Files

| File | Change | Risk |
|---|---|---|
| `pipeline/stage4_temporal_auditor.py` | `_build_investigation_guidance()`, new output fields | LOW — additive |
| `pipeline/stage5_causality_integrator.py` | investigation_context in LLM input (classify unchanged) | LOW |
| `pipeline/stage6_guidance_advisor.py` | `_format_temporal_context()`, `_run_onset_unknown()`, routing | MEDIUM |
| `prompts/system_prompts.py` | Stage 5 temporal ref, Stage 6 temporal placeholder + ONSET_UNKNOWN prompt | MEDIUM |
| `knowledge/ddx_myocarditis.json` | MIS-C differentiation + `sars_cov2_positive` indicator | LOW — additive |
| `knowledge/investigation_protocols.json` | MIS-C investigation items | LOW — additive |
| `compare_v41a_v41b.py` | NEW | NONE |

### Unchanged
- Stage 1, Stage 2, Stage 3 (3A/3B/3C/3D), classify() logic, config.py, data_loader.py

### Estimated Time: ~4 hours

---
---

# v4.2 — Brighton Early Exit Architecture Change

**Objective:** Provide Stage 6 guidance even for Brighton Level 4 early exit cases
**Impact:** No classification change; Unclassifiable cases get richer guidance
**Prerequisite:** v4.1b confirmed
**Baseline:** v4.1b results

## Pre-Execution
```bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; echo "pycache cleaned"
```

---

### Phase 1: Architecture Design (~30 min)

**Current flow (Brighton L4):**
```
Stage 1 → Stage 2 (L4) → early_exit=True → Stage 6 (EARLY_EXIT prompt only)
```
Stage 3, 4, 5 are skipped entirely. Stage 6 only has Stage 1+2 data.

**Proposed flow (Brighton L4):**
```
Stage 1 → Stage 2 (L4) → Stage 3 (DDx still runs) → Stage 6 (enriched EARLY_EXIT)
```

**Design decision needed:** How far should Brighton L4 cases go?

Option A: Run Stage 3 only (DDx findings available for guidance)
- Pro: Stage 6 can say "if diagnosis is confirmed, here's what to investigate for DDx"
- Con: Stage 4/5 without confirmed diagnosis is questionable

Option B: Run Stages 3+4 (DDx + temporal)
- Pro: More complete picture
- Con: Temporal assessment without confirmed diagnosis has uncertain clinical meaning

Option C: Run Stages 3+4+5 (full pipeline, mark as "provisional")
- Pro: Complete analysis available
- Con: Produces a WHO classification for an unconfirmed diagnosis — misleading

**Recommended: Option A** — Stage 3 DDx only, because:
- DDx findings are clinically meaningful even without confirmed diagnosis
- Temporal assessment without diagnosis is questionable
- WHO classification for unconfirmed case would be misleading
- Stage 6 can frame as "IF diagnosis is confirmed, these DDx considerations apply"

---

### Phase 2: main.py Pipeline Modification (~30 min)

#### File: `main.py`

Change early exit handling:

```python
# Current
if brighton_data.get("early_exit"):
    stage6_result = run_stage6(llm, icsr_data, brighton_data, early_exit=True)
    # skip stages 3-5

# Proposed
if brighton_data.get("early_exit"):
    # Still run Stage 3 for DDx context
    stage3_result = run_stage3(llm, icsr_data, brighton_data, knowledge_db)
    
    # Skip Stage 4, 5
    stage6_result = run_stage6(
        llm, icsr_data, brighton_data, 
        ddx_data=stage3_result,
        knowledge_db=knowledge_db,
        early_exit=True,
    )
```

---

### Phase 3: Stage 6 Early Exit Enhancement (~1 hour)

#### File: `pipeline/stage6_guidance_advisor.py`

Update `_run_early_exit()` to accept optional ddx_data:

```python
def _run_early_exit(llm, icsr_data, brighton_data, ddx_data=None):
    combined_input = {
        "icsr": icsr_data,
        "stage2_brighton": brighton_data,
    }
    
    if ddx_data:
        combined_input["stage3_ddx_provisional"] = ddx_data
    
    prompt = STAGE6_EARLY_EXIT_ENRICHED if ddx_data else STAGE6_EARLY_EXIT
    
    result = llm.query_json(
        system_prompt=prompt,
        user_message=f"Generate Early Exit report:\n\n{json.dumps(combined_input, indent=2)}",
    )
    return result
```

#### File: `prompts/system_prompts.py`

Add `STAGE6_EARLY_EXIT_ENRICHED` prompt:
- Explains Brighton L4 (insufficient diagnostic evidence)
- Lists missing tests for Brighton reclassification
- IF Stage 3 DDx data is present: "Provisional DDx analysis identified these considerations..."
- Frame as conditional: "IF myocarditis is confirmed, the following DDx should be investigated..."
- Include Knowledge DB protocol for any provisional dominant alternative

---

### Phase 4: 100-Case Run + Comparison (~1.5 hours)

```bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
python main.py
```

#### Create `compare_v41b_v42.py`:

**Classification comparison:**
- WHO distribution: expect IDENTICAL (no classify() changes)
- Brighton L4 cases: still Unclassifiable (no change)
- Non-L4 cases: completely unchanged

**Early exit quality metrics:**
- Brighton L4 cases with DDx data in Stage 6 output (target: 100%)
- Provisional dominant alternative identified for L4 cases
- Diagnostic deficiencies now include DDx-specific tests ("if confirmed, test for X")
- Compare officer_summary quality: generic vs DDx-informed

---

### v4.2 Modified Files

| File | Change | Risk |
|---|---|---|
| `main.py` | Run Stage 3 for Brighton L4 before Stage 6 | **MEDIUM — flow change** |
| `pipeline/stage6_guidance_advisor.py` | `_run_early_exit()` accepts ddx_data, routing | MEDIUM |
| `prompts/system_prompts.py` | `STAGE6_EARLY_EXIT_ENRICHED` prompt | LOW |
| `compare_v41b_v42.py` | NEW | NONE |

### Unchanged
- Stage 1, Stage 2, Stage 3 logic, Stage 4, Stage 5, Knowledge DB, config.py

### Estimated Time: ~3.5 hours

---
---

# Summary Timeline

| Version | Scope | Classification Impact | Time |
|---|---|---|---|
| **v4.1a** | Stage 1 onset extraction + Stage 5 UNKNOWN path | YES — onset changes | ~3h |
| **v4.1b** | Stage 4/6 temporal guidance + MIS-C differentiation | NO — output quality only | ~4h |
| **v4.2** | Brighton L4 early exit enrichment | NO — guidance quality only | ~3.5h |
| **Total** | | | **~10.5h** |

Each version gets a 100-case run + comparison against its predecessor.
