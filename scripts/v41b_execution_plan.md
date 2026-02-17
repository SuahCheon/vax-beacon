# Vax-Beacon v4.1b — Execution Plan (Updated)

**Objective:** Temporal-aware investigation guidance + MIS-C differentiation + DB patch1 validation
**Impact:** WHO classification may change (due to DB patch1 from v4.1a); Stage 5 reasoning + Stage 6 guidance quality improved
**Prerequisite:** v4.1a completed, DB patch1 (ddx_myocarditis.json v4.1a-patch1) already applied
**Baseline for comparison:** v4.1a 100-case results (`results/results_v41a_full_100_20260216_142410.json`)

## Context: What's Already Changed Since v4.1a

**DB patch1** (already applied to `knowledge/ddx_myocarditis.json`):
- GCM: `av_block_present` → `high_degree_av_block` (incomplete BBB/1도 AV block 제외)
- Toxin/ICI: `conduction_delay` — negative_keywords 강화 + TWO MANDATORY requirements (severity + ICI context)
- Verified on case 1413266: NCI 0.4→0.0, B2→A1 ✅

**Expected patch1 impact on 100-case run:**
- Cases with incomplete BBB/mild conduction findings → NCI 감소 가능 → WHO 변경 가능
- 이 변경은 v4.1b Phase 5 비교 시 별도 추적

---

## Pre-Execution (EVERY phase)

```bash
# Windows PowerShell
Get-ChildItem -Path . -Filter __pycache__ -Recurse -Directory | Remove-Item -Recurse -Force
Write-Host "pycache cleaned"
```

---

## Phase 1: Stage 4 Temporal Investigation Guidance (~30 min)

### File: `pipeline/stage4_temporal_auditor.py`

**1-1. Add `_build_investigation_guidance()` function** (insert before `run_stage4()`):

```python
def _build_investigation_guidance(temporal_zone: str) -> dict:
    """Map temporal zone to investigation intensity and requirements."""
    if temporal_zone == "STRONG_CAUSAL":
        return {
            "intensity": "STANDARD",
            "focus": "CONFOUNDING_EXCLUSION",
            "description": (
                "Strong causal window (0-7d). Standard diagnostics sufficient. "
                "Investigate alternatives only if clinical indicators present."
            ),
            "query_requirements": {
                "bridging_symptoms": "NOT_REQUIRED",
                "infection_history": "IF_PRODROMAL_PRESENT",
                "medication_review": "STANDARD",
            },
        }
    elif temporal_zone == "PLAUSIBLE":
        return {
            "intensity": "ENHANCED",
            "focus": "ACTIVE_DIFFERENTIATION",
            "description": (
                "Plausible but attenuated window (8-21d). Active differentiation "
                "required — investigate alternatives regardless of clinical indicators."
            ),
            "query_requirements": {
                "bridging_symptoms": "NOT_REQUIRED",
                "infection_history": "REQUIRED",
                "medication_review": "REQUIRED",
                "symptom_evolution": "RECOMMENDED",
            },
        }
    elif temporal_zone == "BACKGROUND_RATE":
        return {
            "intensity": "COMPREHENSIVE",
            "focus": "ALTERNATIVE_IDENTIFICATION",
            "description": (
                "Beyond mechanistic threshold (22-42d). Comprehensive alternative "
                "workup required. Bridging symptom verification CRITICAL."
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
            },
        }
    else:  # UNLIKELY or UNKNOWN
        return {
            "intensity": "COMPREHENSIVE",
            "focus": "ALTERNATIVE_IDENTIFICATION",
            "description": (
                "Outside plausible causal window or onset unknown. "
                "Comprehensive workup required. Verify onset date accuracy."
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
            },
        }
```

**1-2. Modify `run_stage4()` return dict** — add investigation guidance fields to `temporal_assessment`:

Find the existing return statement's `"temporal_assessment"` block and add 4 new fields:

```python
    # After computing temporal = _assess_temporal(...)
    # ADD THIS LINE:
    guidance = _build_investigation_guidance(temporal["temporal_zone"])

    # In the return dict, modify "temporal_assessment" to include:
    "temporal_assessment": {
        "vaccination_date": vax_date,
        "onset_date": onset_date,
        "days_to_onset": days_to_onset,
        "temporal_zone": temporal["temporal_zone"],
        "nam_2024_alignment": temporal["nam_alignment"],
        # NEW v4.1b fields:
        "investigation_intensity": guidance["intensity"],
        "investigation_focus": guidance["focus"],
        "investigation_description": guidance["description"],
        "query_requirements": guidance["query_requirements"],
    },
```

### Verification

```bash
python main.py --case 1286607   # Day 0 → STRONG_CAUSAL → STANDARD
python main.py --case 1090794   # Day 12 → PLAUSIBLE → ENHANCED  
python main.py --case 1499676   # Day 33 → BACKGROUND_RATE → COMPREHENSIVE
python main.py --case 1464028   # Day 54 → UNLIKELY → COMPREHENSIVE
```

**Check:**
- [ ] Stage 4 output has `investigation_intensity`, `investigation_focus`, `investigation_description`, `query_requirements`
- [ ] Stage 5 `who_category` identical to v4.1a for these cases
- [ ] BACKGROUND_RATE/UNLIKELY cases have `bridging_symptom_detail` in `query_requirements`

---

## Phase 2: Stage 5 Reasoning Enhancement (~20 min)

### File: `pipeline/stage5_causality_integrator.py`

**2-1. No change to `classify()`.** Only modify `run_stage5()` — add `investigation_context` to `combined_input`:

Find the existing `combined_input = {` block in `run_stage5()` and add:

```python
    combined_input = {
        "icsr": icsr_data,
        "stage2_brighton": brighton_data,
        "stage3_ddx": ddx_data,
        "stage4_temporal_known_ae": temporal_data,
        "condition_type": condition_type,
        "assigned_who_category": who_category,
        "assigned_who_label": _who_label(who_category),
        "decision_chain": decision_chain,
        # NEW v4.1b: investigation context for reasoning
        "investigation_context": {
            "intensity": temporal_data.get("temporal_assessment", {}).get("investigation_intensity"),
            "focus": temporal_data.get("temporal_assessment", {}).get("investigation_focus"),
            "description": temporal_data.get("temporal_assessment", {}).get("investigation_description"),
        },
    }
```

### File: `prompts/system_prompts.py`

**2-2. Add to `STAGE5_CAUSALITY_INTEGRATOR`** — insert before the `OUTPUT FORMAT` section:

```
==========================================================
TEMPORAL INVESTIGATION CONTEXT
==========================================================
When explaining the classification, reference the investigation context if provided:
- STANDARD intensity: Note that the strong temporal window supports causal inference
- ENHANCED intensity: Acknowledge that active differentiation is recommended
- COMPREHENSIVE intensity: Note that temporal relationship is weak and alternatives need investigation
Do NOT change the assigned classification based on this context.
```

### Verification

```bash
python main.py --case 1286607   # A1 — reasoning should mention "strong temporal window"
python main.py --case 1499676   # Check reasoning mentions "weak temporal" / "alternatives need investigation"
```

**Check:**
- [ ] `classify()` output unchanged
- [ ] LLM reasoning references investigation context appropriately

---

## Phase 3: Stage 6 Temporal-Aware + Gap-Aware Guidance (~1 hour)

### File: `pipeline/stage6_guidance_advisor.py`

**3-1. Add `_format_temporal_context()` helper** (insert after `_format_protocol_context()`):

```python
def _format_temporal_context(intensity: str, focus: str, query_reqs: dict) -> str:
    """Format temporal investigation guidance for prompt injection."""
    if not intensity:
        return ""

    lines = [
        f"=== TEMPORAL INVESTIGATION CONTEXT ===",
        f"Investigation intensity: {intensity}",
        f"Focus: {focus}",
        "",
        "Query requirements:",
    ]

    for key, value in query_reqs.items():
        if key == "bridging_symptom_detail":
            lines.append(f"  BRIDGING SYMPTOM QUERY (CRITICAL):")
            lines.append(f"    {value}")
        else:
            lines.append(f"  {key}: {value}")

    lines.append("=== END TEMPORAL CONTEXT ===")
    return "\n".join(lines)
```

**3-2. Modify `_run_normal()`** — extract temporal guidance and inject into prompt:

```python
def _run_normal(
    llm, icsr_data, brighton_data, ddx_data,
    temporal_data, causality_data, protocol,
) -> dict:
    """Normal flow: full pipeline completed with protocol-injected prompt."""
    combined_input = {
        "icsr": icsr_data,
        "stage2_brighton": brighton_data,
        "stage3_ddx": ddx_data,
        "stage4_temporal_known_ae": temporal_data,
        "stage5_causality": causality_data,
    }

    # Build the prompt with protocol + temporal context injected
    protocol_context = _format_protocol_context(protocol)
    
    # NEW v4.1b: temporal investigation context
    temporal_assessment = (temporal_data or {}).get("temporal_assessment", {})
    intensity = temporal_assessment.get("investigation_intensity", "STANDARD")
    focus = temporal_assessment.get("investigation_focus", "CONFOUNDING_EXCLUSION")
    query_reqs = temporal_assessment.get("query_requirements", {})
    temporal_context = _format_temporal_context(intensity, focus, query_reqs)

    prompt = STAGE6_GUIDANCE_ADVISOR.replace(
        "{protocol_context}", protocol_context
    ).replace(
        "{temporal_investigation_context}", temporal_context
    )

    result = llm.query_json(
        system_prompt=prompt,
        user_message=(
            "Identify investigative gaps and provide HITL guidance:\n\n"
            f"{json.dumps(combined_input, indent=2)}"
        ),
    )
    return result
```

**3-3. Add `_run_onset_unknown()` function:**

```python
def _run_onset_unknown(
    llm, icsr_data, brighton_data, ddx_data,
    temporal_data, causality_data, protocol,
) -> dict:
    """Onset unknown: Unclassifiable but full pipeline data available."""
    combined_input = {
        "icsr": icsr_data,
        "stage2_brighton": brighton_data,
        "stage3_ddx": ddx_data,
        "stage4_temporal_known_ae": temporal_data,
        "stage5_causality": causality_data,
    }

    # Protocol context still useful for DDx-based gaps
    protocol_context = _format_protocol_context(protocol)
    prompt = STAGE6_ONSET_UNKNOWN.replace("{protocol_context}", protocol_context)

    result = llm.query_json(
        system_prompt=prompt,
        user_message=(
            "Generate guidance for this onset-unknown Unclassifiable case:\n\n"
            f"{json.dumps(combined_input, indent=2)}"
        ),
    )
    return result
```

**3-4. Modify `run_stage6()` routing** — add onset_unknown path between early_exit and normal:

```python
def run_stage6(
    llm: LLMClient,
    icsr_data: dict,
    brighton_data: dict,
    ddx_data: dict = None,
    temporal_data: dict = None,
    causality_data: dict = None,
    knowledge_db: dict = None,
    early_exit: bool = False,
) -> dict:
    if early_exit:
        return _run_early_exit(llm, icsr_data, brighton_data)

    # Fetch protocol for dominant alternative
    dominant = ddx_data.get("dominant_alternative", "NONE") if ddx_data else "NONE"
    protocol = {}
    if knowledge_db and dominant != "NONE":
        protocols_db = knowledge_db.get("protocols", {})
        protocol = _get_protocol_for_dominant(dominant, protocols_db)

    # NEW v4.1b: onset unknown routing
    onset_unknown = (causality_data or {}).get("decision_chain", {}).get("onset_unknown", False)
    who_category = (causality_data or {}).get("who_category", "")

    if who_category == "Unclassifiable" and onset_unknown:
        return _run_onset_unknown(
            llm, icsr_data, brighton_data, ddx_data,
            temporal_data, causality_data, protocol,
        )

    return _run_normal(
        llm, icsr_data, brighton_data, ddx_data,
        temporal_data, causality_data, protocol,
    )
```

### File: `prompts/system_prompts.py`

**3-5. Modify `STAGE6_GUIDANCE_ADVISOR`** — add `{temporal_investigation_context}` placeholder and temporal-aware rules.

Insert `{temporal_investigation_context}` AFTER the existing `{protocol_context}` line, and add rules:

```python
STAGE6_GUIDANCE_ADVISOR = """You are a CIOMS 2025-compliant regulatory science advisor.
Generate a Human-in-the-Loop (HITL) guidance report for the surveillance officer.

You receive the COMPLETE pipeline output (Stages 1-5).

{protocol_context}

{temporal_investigation_context}

RULES FOR TEMPORAL-AWARE GUIDANCE:
- Check Stage 3 findings BEFORE recommending tests. Do NOT recommend tests
  for conditions already confirmed or excluded by Stage 3.
- Scale investigation scope to temporal intensity:
  - STANDARD: Only recommend tests for Stage 3-identified indicators
  - ENHANCED: Recommend tests even without Stage 3 indicators
  - COMPREHENSIVE: Full workup + bridging symptom query
- When bridging_symptoms is CRITICAL, include bridging symptom query as FIRST investigative gap
- Frame cardiac MRI as "GCM/ischemic exclusion + involvement extent assessment",
  NOT "vaccine vs viral pattern differentiation"

IMPORTANT: Check Stage 3 "dominant_alternative" and ...
(rest of existing prompt unchanged)
"""
```

**3-6. Add `STAGE6_ONSET_UNKNOWN` prompt** (new constant in `prompts/system_prompts.py`):

```python
STAGE6_ONSET_UNKNOWN = """You are a CIOMS 2025-compliant regulatory science advisor.
This case is classified as UNCLASSIFIABLE because the onset date is unknown,
making temporal assessment impossible. However, the full pipeline (Stages 1-5)
has been executed and DDx analysis is available.

You receive the COMPLETE pipeline output including Stage 3 DDx findings.

{protocol_context}

Your task: Generate guidance that PRIORITIZES onset date verification while
also including DDx-based investigation gaps.

Return ONLY valid JSON:
{
  "vaers_id": <integer>,
  "overall_risk_signal": "<HIGH/MEDIUM/LOW>",
  "onset_verification": {
    "priority": "CRITICAL",
    "query_text": "Contact reporter to establish exact symptom onset date. Ask: When did you FIRST notice any cardiac symptoms (chest pain, shortness of breath, palpitations, unusual fatigue)? Was this before or after vaccination? How many days after vaccination?",
    "impact": "Onset date is required for WHO AEFI temporal assessment. Once established, the case can be reclassified from Unclassifiable to a definitive WHO category."
  },
  "possible_categories_once_onset_known": {
    "if_strong_causal": "<what WHO category would result given current NCI and known_ae status>",
    "if_plausible": "<what WHO category would result>",
    "if_unlikely": "<what WHO category would result>"
  },
  "investigative_gaps": [
    {
      "gap": "<specific missing data>",
      "priority": "<CRITICAL/HIGH/MEDIUM/LOW>",
      "action": "<specific recommended action>",
      "impact_on_classification": "<how this could change the WHO category>"
    }
  ],
  "recommended_actions": ["<action1>", "<action2>", ...],
  "escalation_needed": <true/false>,
  "escalation_reason": "<reason or null>",
  "quality_flags": {
    "data_completeness": "<COMPLETE/PARTIAL/MINIMAL>",
    "diagnostic_certainty": "<HIGH/MEDIUM/LOW>",
    "temporal_clarity": "MISSING"
  },
  "officer_summary": "<2-3 sentence plain-language summary. State that onset date is unknown and must be verified before classification is possible. Mention what the likely classification would be if onset is within the expected window.>"
}

RULES:
- onset_verification MUST be the FIRST and highest-priority item
- Include DDx-based gaps from Stage 3 even though temporal assessment is incomplete
- Frame possible_categories based on current NCI score and known_ae status
- Keep officer_summary accessible and actionable
"""
```

### Verification

```bash
python main.py --case 1286607   # STRONG → STANDARD, minimal gaps
python main.py --case 1090794   # PLAUSIBLE → ENHANCED, broader gaps
python main.py --case 1499676   # BACKGROUND → COMPREHENSIVE + bridging CRITICAL
python main.py --case 1423060   # UNKNOWN onset → onset_verification CRITICAL
```

**Check:**
- [ ] STANDARD cases: fewer/focused investigation gaps
- [ ] COMPREHENSIVE cases: bridging symptom query as FIRST gap
- [ ] UNKNOWN onset cases: `onset_verification` field present, `possible_categories_once_onset_known` populated
- [ ] No "vaccine vs viral" MRI framing in any case
- [ ] Stage 6 import includes `STAGE6_ONSET_UNKNOWN` from prompts

---

## Phase 4: MIS-C Differentiation in Knowledge DB (~30 min)

### File: `knowledge/ddx_myocarditis.json` (currently v4.1a-patch1)

**4-1. Update `mis_c_criteria_met` differentiation_guide** in `covid19_related` subtype:

Find the existing `mis_c_criteria_met` indicator and replace its `differentiation_guide`:

```json
"differentiation_guide": "MIS-C can be triggered by BOTH SARS-CoV-2 infection AND mRNA vaccination. Key differentiators: (1) Nucleocapsid antibody positive → prior natural infection (vaccination produces only spike antibody) → infection-triggered MIS-C = alternative cause. (2) Nucleocapsid negative + recent vaccination → vaccine-triggered MIS-C-like presentation = vaccine causation. (3) Both vaccination AND recent infection history → requires clinical judgment on dominant trigger. TRUE only if multi-system inflammatory syndrome criteria met: persistent fever (>24h) + multi-organ involvement (≥2 of cardiac, GI, mucocutaneous, hematologic, neurologic) + elevated inflammatory markers (CRP, ferritin, D-dimer)."
```

**4-2. Add `sars_cov2_positive` indicator** to `covid19_related` → `clinical_features` → `primary_indicators` array:

Insert as a new entry in the `primary_indicators` list:

```json
{
    "finding": "sars_cov2_positive",
    "description": "Laboratory-confirmed SARS-CoV-2 infection (PCR, antigen, or nucleocapsid antibody positive) at or near the time of cardiac symptom onset",
    "extraction_keywords": [
        "COVID positive", "SARS-CoV-2 positive", "PCR positive",
        "antigen positive", "COVID test positive", "nucleocapsid positive",
        "COVID-19 confirmed", "coronavirus positive", "COVID diagnosed"
    ],
    "negative_keywords": [
        "COVID negative", "SARS negative", "PCR negative",
        "antigen negative", "no COVID", "COVID test negative",
        "COVID not detected", "nucleocapsid negative"
    ],
    "differentiation_guide": "Confirmed SARS-CoV-2 infection provides an alternative etiology for myocarditis through direct viral cardiotropic injury or post-infectious inflammatory response. If both vaccination and infection are temporally proximate, diagnostic ambiguity arises. Nucleocapsid antibody testing is the key differentiator: positive nucleocapsid indicates prior natural infection (mRNA vaccination produces only spike antibody, not nucleocapsid). A SARS-CoV-2 positive result concurrent with myocarditis onset is a strong indicator of COVID-related rather than vaccine-related etiology.",
    "weight": 0.5
}
```

**4-3. Update version:** Change `"version": "4.1a-patch1"` to `"version": "4.1b"`.

### File: `knowledge/investigation_protocols.json`

**4-4. Add to `covid19_related` → `investigations` array** — insert 2 new items:

```json
{
    "test": "SARS-CoV-2 nucleocapsid antibody",
    "priority": "HIGH",
    "rationale": "Differentiates prior natural infection from vaccination-only exposure. Nucleocapsid antibody is produced only after natural infection, not after mRNA vaccination (which produces only spike antibody).",
    "indication": "When MIS-C or post-infectious myocarditis is suspected AND patient was recently vaccinated",
    "expected_finding": "Positive = prior natural infection likely contributed; Negative = vaccine-triggered mechanism more likely",
    "differential_from_vaccine": "Nucleocapsid-negative patient with recent vaccination and MIS-C presentation supports vaccine-triggered mechanism rather than infection-triggered"
},
{
    "test": "MIS-C inflammatory panel (ferritin, D-dimer, fibrinogen, LDH)",
    "priority": "HIGH",
    "rationale": "MIS-C has a distinctive inflammatory pattern: markedly elevated ferritin (often >500), D-dimer, and fibrinogen with lymphopenia. This pattern differs from vaccine-induced myocarditis.",
    "indication": "Pediatric/young adult with multi-organ involvement post-vaccination or post-infection",
    "expected_finding": "Ferritin >500, D-dimer elevated, fibrinogen elevated with lymphopenia suggests MIS-C pattern",
    "differential_from_vaccine": "Vaccine myocarditis typically shows milder inflammatory markers without the MIS-C pattern of markedly elevated ferritin/D-dimer. Presence of MIS-C pattern warrants nucleocapsid testing to determine trigger."
}
```

**4-5. Update version:** Change `"version": "4.0"` to `"version": "4.1b"` in `investigation_protocols.json`.

### Verification

```bash
python main.py --case 1501224   # MIS-C-like case
```

**Check:**
- [ ] Stage 3B matches `sars_cov2_positive` and/or `mis_c_criteria_met` if applicable
- [ ] Stage 6 recommends nucleocapsid antibody testing
- [ ] Stage 6 officer_summary explains MIS-C infection vs vaccine differentiation

---

## Phase 5: 100-Case Run + Comparison (~1.5 hours)

### Run

```bash
Get-ChildItem -Path . -Filter __pycache__ -Recurse -Directory | Remove-Item -Recurse -Force
python main.py
```

→ `results/results_v41b_full_100_<timestamp>.json`

### Create `compare_v41a_v41b.py`

**This comparison is against v4.1a results**, with awareness that DB patch1 changes are included.

**Classification comparison:**
- WHO distribution (v4.1a vs v4.1b)
- Cases where WHO changed — categorize each as:
  - **DB patch1 effect**: NCI changed due to `high_degree_av_block` / `conduction_delay` keyword changes
  - **v4.1b effect**: Should be NONE (no classify() changes)
  - **LLM non-determinism**: NCI or onset drift unrelated to code changes
- NCI score changes: flag any case where `max_nci` changed

**Stage 6 quality metrics (NEW in v4.1b):**
- Bridging symptom query rate for BACKGROUND_RATE/UNLIKELY temporal zones (target: 100%)
- MRI framing: scan all Stage 6 outputs for "vaccine vs viral" (target: 0 instances)
- Investigation scope scaling: avg gap count by intensity (STANDARD < ENHANCED < COMPREHENSIVE)
- MIS-C cases: nucleocapsid antibody in recommendations (target: 100% of MIS-C suspects)
- Onset unknown cases: `onset_verification` field present (target: 100%)

**Comparison baselines:**
- v4.1a results: `results/results_v41a_full_100_20260216_142410.json`
- v4.1b results: `results/results_v41b_full_100_<timestamp>.json`

---

## v4.1b Modified Files Summary

| File | Change | Risk |
|---|---|---|
| `pipeline/stage4_temporal_auditor.py` | `_build_investigation_guidance()`, 4 new output fields | LOW — additive only |
| `pipeline/stage5_causality_integrator.py` | `investigation_context` in LLM input (**classify() UNCHANGED**) | LOW |
| `pipeline/stage6_guidance_advisor.py` | `_format_temporal_context()`, `_run_onset_unknown()`, routing logic | MEDIUM |
| `prompts/system_prompts.py` | Stage 5 temporal ref, Stage 6 `{temporal_investigation_context}` + temporal rules, `STAGE6_ONSET_UNKNOWN` prompt | MEDIUM |
| `knowledge/ddx_myocarditis.json` | MIS-C guide update + `sars_cov2_positive` indicator (version → 4.1b) | LOW — additive |
| `knowledge/investigation_protocols.json` | Nucleocapsid antibody + MIS-C panel (version → 4.1b) | LOW — additive |
| `compare_v41a_v41b.py` | NEW — comparison script | NONE |

### Unchanged (MUST NOT be modified)
- `pipeline/stage1_icsr_extractor.py`
- `pipeline/stage2_clinical_validator.py`
- `pipeline/stage3a_clinical_observer.py`
- `pipeline/stage3b_ddx_matcher.py`
- `pipeline/stage3c_plausibility.py`
- `pipeline/stage3d_nci_calculator.py`
- `pipeline/stage5_causality_integrator.py` → `classify()` function
- `config.py`, `data_loader.py`, `main.py`, `knowledge_loader.py`, `llm_client.py`

### Estimated Time: ~4 hours (Phase 1-4 coding ~2.5h + Phase 5 run ~1.5h)
