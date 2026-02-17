"""
Vax-Beacon v4 | Stage 3C: Plausibility Assessor (LLM)
==========================================================
Focused LLM evaluation of ONLY the markers matched in Stage 3B.
By evaluating fewer markers with specific differentiation guidance,
reproducibility is improved over v3.1's all-38-marker approach.

Input:  Original narrative + 3A output + 3B candidates + differentiation_guide
Output: Per-marker 4-dimensional assessment (backward compatible with v3.1)
        All 38 clinical markers + 3 nuance markers included;
        unmatched markers are set to present=false.
"""

import json
from llm_client import LLMClient


# All clinical markers from NCI_WEIGHT_MATRIX (excluding narrative_nuance)
_ALL_CLINICAL_MARKERS = [
    # viral_etiology
    "fever_reported", "uri_symptoms", "gi_symptoms", "myalgia_arthralgia",
    "positive_viral_pcr", "lymphocytosis",
    # giant_cell_myocarditis
    "rapid_heart_failure", "av_block_present", "ventricular_arrhythmia",
    "cardiogenic_shock", "giant_cells_on_biopsy",
    # eosinophilic_myocarditis
    "peripheral_eosinophilia", "new_medication_history",
    "hypersensitivity_rash", "eosinophils_on_biopsy",
    # toxin_ici_myocarditis
    "ici_therapy_active", "concurrent_myositis", "conduction_delay",
    "new_chemotherapy", "elevated_ck",
    # ischemic_heart_disease
    "age_over_50", "prior_cad_history", "focal_st_changes",
    "positive_catheterization", "diabetes_hypertension", "smoking_history",
    # covid19_related
    "active_covid19", "recent_covid_infection", "mis_c_criteria_met",
    "mis_a_criteria_met", "elevated_d_dimer",
    # autoimmune_inflammatory
    "known_autoimmune_dx", "positive_ana_dsdna", "systemic_inflammation",
    "granulomas_on_biopsy",
]

_NUANCE_MARKERS = [
    "reporter_uncertainty", "alternative_suspected", "lack_of_testing",
]

_DEFAULT_ABSENT = {
    "present": False,
    "is_acute_concordant": False,
    "plausibility": "none",
    "biological_rationale": "Not identified in narrative.",
}


def _build_evaluation_prompt(stage3b_output: dict, ddx_db: dict) -> str:
    """Build the focused evaluation prompt for matched markers only."""
    candidates = stage3b_output.get("ddx_candidates", [])
    nuance_obs = stage3b_output.get("narrative_nuance_observations", [])

    sections = []

    # Build per-candidate marker evaluation sections
    for candidate in candidates:
        subtype = candidate["subtype"]
        label = candidate["label"]
        matched = candidate["matched_indicators"]

        marker_instructions = []
        for m in matched:
            marker_instructions.append(
                f"  - {m['finding']} (weight={m['weight']})\n"
                f"    Matched from observation: \"{m['source_observation']}\"\n"
                f"    Context quote: \"{m['source_context']}\"\n"
                f"    DIFFERENTIATION GUIDE: {m['differentiation_guide']}"
            )

        sections.append(
            f"[{label} — {subtype}]\n"
            f"Evaluate these matched markers:\n"
            + "\n".join(marker_instructions)
        )

    # Narrative nuance section
    if nuance_obs:
        nuance_items = []
        for obs in nuance_obs:
            nuance_items.append(
                f"  - Observation: \"{obs.get('finding', '')}\"\n"
                f"    Context: \"{obs.get('context', '')}\""
            )
        sections.append(
            "[Narrative Nuance]\n"
            "Evaluate these narrative uncertainty markers:\n"
            "  - reporter_uncertainty: Reporter/clinician expresses uncertainty about cause\n"
            "  - alternative_suspected: Narrative mentions possible non-vaccine cause\n"
            "  - lack_of_testing: Narrative states viral/other testing was NOT done\n"
            "Based on these observations:\n"
            + "\n".join(nuance_items)
        )

    return "\n\n".join(sections)


STAGE3C_SYSTEM_PROMPT = """You are a Senior Cardiac Pathologist and Pharmacovigilance Expert.

You are evaluating a FOCUSED set of clinical markers that were identified by keyword
matching in a VAERS myocarditis/pericarditis case. Your task is to determine whether
each matched marker is TRULY present and clinically plausible as a cause of ACUTE
myocarditis, using the differentiation guides provided.

For EACH marker listed below, provide a 4-dimensional assessment:
  1. "present": Is this finding TRULY present in the narrative? (true/false)
     The keyword matcher may have produced false positives — verify carefully.
  2. "is_acute_concordant": Can this finding cause ACUTE myocardial inflammation? (true/false)
     Chronic conditions or remote exposures are NOT acute-concordant.
  3. "plausibility": Biological plausibility as an acute myocarditis cause
     ("high"/"moderate"/"low"/"none")
  4. "biological_rationale": 2-3 sentence justification explaining:
     - IF INCLUDED: Why biologically plausible for the current acute event
     - IF EXCLUDED: Why this is NOISE (pathological mismatch, temporal implausibility)

=== CRITICAL DIFFERENTIATION RULES ===
- READ the DIFFERENTIATION GUIDE for each marker carefully. It tells you exactly
  how to distinguish between different causes.
- For risk-factor markers (age_over_50, diabetes_hypertension, smoking_history):
  is_acute_concordant=true but plausibility="low" (risk factor, not direct cause)
- For narrative nuance markers (reporter_uncertainty, alternative_suspected, lack_of_testing):
  If present, set is_acute_concordant=true and plausibility="moderate"
- For myalgia_arthralgia: TRUE only if PRODROMAL, not post-vaccine reactogenicity
- For focal_st_changes: TRUE only for SINGLE CORONARY TERRITORY (see guide)
- For positive_viral_pcr: TRUE only for CONFIRMED positive test result
- For systemic_inflammation: TRUE only for EXTRA-CARDIAC multi-organ inflammation
- For rapid_heart_failure: Assess GCM (refractory, progressive) vs vaccine (self-limited, recovery)
- For lymphocytosis: TRUE only when lab results confirm actual lymphocyte elevation

=== OUTPUT FORMAT ===
Respond ONLY with valid JSON. Use the exact marker names as keys:
{
  "marker_name": {
    "present": true/false,
    "is_acute_concordant": true/false,
    "plausibility": "high/moderate/low/none",
    "biological_rationale": "..."
  },
  ...
}

Include ONLY the markers listed in the evaluation section below.
Do NOT add markers that are not listed.
"""


def run_stage3c(
    llm: LLMClient,
    original_narrative: str,
    stage3a_output: dict,
    stage3b_output: dict,
    ddx_db: dict,
) -> dict:
    """
    Stage 3C: Focused plausibility assessment of matched markers.

    Args:
        llm: LLM client instance
        original_narrative: Raw VAERS case text
        stage3a_output: Output from Stage 3A
        stage3b_output: Output from Stage 3B (DDx candidates + matched markers)
        ddx_db: Loaded ddx_myocarditis.json content

    Returns:
        Dict of all 38+3 markers in v3.1 cleaned_findings format
    """
    # Build the focused evaluation section
    evaluation_section = _build_evaluation_prompt(stage3b_output, ddx_db)

    # Collect all marker names that need LLM evaluation
    markers_to_evaluate = set()
    for candidate in stage3b_output.get("ddx_candidates", []):
        for m in candidate["matched_indicators"]:
            markers_to_evaluate.add(m["finding"])

    # Add nuance markers if observations exist
    nuance_obs = stage3b_output.get("narrative_nuance_observations", [])
    if nuance_obs:
        markers_to_evaluate.update(_NUANCE_MARKERS)

    user_message = (
        "Evaluate the matched clinical markers for this VAERS report.\n\n"
        "=== ORIGINAL NARRATIVE ===\n"
        f"{original_narrative}\n\n"
        "=== STAGE 3A CLINICAL OBSERVATIONS ===\n"
        f"{json.dumps(stage3a_output.get('clinical_observations', {}), indent=2)}\n\n"
        "=== MARKERS TO EVALUATE ===\n"
        f"{evaluation_section}\n"
    )

    # LLM evaluation of matched markers only
    llm_findings = llm.query_json(
        system_prompt=STAGE3C_SYSTEM_PROMPT,
        user_message=user_message,
    )

    # Build complete 38+3 marker output (backward compatible with v3.1)
    cleaned_findings = {}

    # Fill all clinical markers
    for marker in _ALL_CLINICAL_MARKERS:
        if marker in llm_findings and marker in markers_to_evaluate:
            val = llm_findings[marker]
            if isinstance(val, dict):
                cleaned_findings[marker] = {
                    "present": bool(val.get("present", False)),
                    "is_acute_concordant": bool(val.get("is_acute_concordant", False)),
                    "plausibility": str(val.get("plausibility", "none")).lower(),
                    "biological_rationale": str(val.get("biological_rationale", "")),
                }
            else:
                cleaned_findings[marker] = dict(_DEFAULT_ABSENT)
        else:
            # Not matched in 3B → absent
            cleaned_findings[marker] = dict(_DEFAULT_ABSENT)

    # Fill narrative nuance markers
    for marker in _NUANCE_MARKERS:
        if marker in llm_findings and marker in markers_to_evaluate:
            val = llm_findings[marker]
            if isinstance(val, dict):
                cleaned_findings[marker] = {
                    "present": bool(val.get("present", False)),
                    "is_acute_concordant": bool(val.get("is_acute_concordant", True)),
                    "plausibility": str(val.get("plausibility", "none")).lower(),
                    "biological_rationale": str(val.get("biological_rationale", "")),
                }
            else:
                cleaned_findings[marker] = dict(_DEFAULT_ABSENT)
        else:
            cleaned_findings[marker] = dict(_DEFAULT_ABSENT)

    return cleaned_findings
