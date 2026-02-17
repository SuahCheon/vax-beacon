"""
Vax-Beacon v3 | Stage 3: DDx Specialist (Logic-Augmented + Plausibility Filter)
==================================================================================
WHO AEFI Step 1: "Is there another definite cause for this event?"

Three-Layer Hybrid Architecture:
  Layer 1-3 (LLM Observer): Extracts 3-dimensional clinical markers
    - present: Is the marker found in the narrative? (Boolean)
    - is_acute_concordant: Can this cause ACUTE myocarditis? (Boolean)
    - plausibility: Biological plausibility level (high/moderate/low/none)
  Layer 4 (Code Calculator): NCI Weight Matrix with Plausibility Gate
    - Only markers passing BOTH acute_concordant AND plausibility >= moderate
      receive weight contribution
  Layer 5 (Code Threshold): WHO Step 1 conclusion

Design Principles:
  - Strict Decoupling: LLM observes & classifies, code calculates
  - Noise Reduction: Chronic conditions filtered from acute inflammation assessment
  - Mechanistic Specificity: Myocarditis subtypes with pathology-specific weights
  - Full Auditability: Every marker → gate decision → weight → score traceable

Reference: Brighton Collaboration, WHO AEFI Manual, Table 1 "Types of Myocarditis"
"""

import json
from llm_client import LLMClient


# ============================================================
# NCI WEIGHT MATRIX (Regulatory Knowledge Base)
# ============================================================
# Weights are ONLY applied if the marker passes the Plausibility Gate:
#   1. present = True
#   2. is_acute_concordant = True
#   3. plausibility in ("high", "moderate")

NCI_WEIGHT_MATRIX = {
    # --- Viral Myocarditis (Lymphocytic) ---
    "viral_etiology": {
        "fever_reported": 0.2,
        "uri_symptoms": 0.2,
        "gi_symptoms": 0.2,
        "myalgia_arthralgia": 0.15,
        "positive_viral_pcr": 0.8,
        "lymphocytosis": 0.15,
    },

    # --- Giant Cell Myocarditis (GCM) ---
    "giant_cell_myocarditis": {
        "rapid_heart_failure": 0.6,
        "av_block_present": 0.5,
        "ventricular_arrhythmia": 0.5,
        "cardiogenic_shock": 0.4,
        "giant_cells_on_biopsy": 1.0,
    },

    # --- Eosinophilic Myocarditis (EM) ---
    "eosinophilic_myocarditis": {
        "peripheral_eosinophilia": 0.7,
        "new_medication_history": 0.3,
        "hypersensitivity_rash": 0.2,
        "eosinophils_on_biopsy": 1.0,
    },

    # --- Toxin-induced / ICI Myocarditis ---
    "toxin_ici_myocarditis": {
        "ici_therapy_active": 0.8,
        "concurrent_myositis": 0.5,
        "conduction_delay": 0.4,
        "new_chemotherapy": 0.4,
        "elevated_ck": 0.3,
    },

    # --- Ischemic Heart Disease (CAD/MI) ---
    # Note: age_over_50 is a RISK FACTOR, not a cause of acute myocarditis.
    # Weight=0 means it's recorded for audit but does NOT contribute to NCI.
    "ischemic_heart_disease": {
        "age_over_50": 0.0,             # Risk factor only — recorded, not scored
        "prior_cad_history": 0.7,
        "focal_st_changes": 0.5,
        "positive_catheterization": 1.0,
        "diabetes_hypertension": 0.0,   # Risk factor only — recorded, not scored
        "smoking_history": 0.0,         # Risk factor only — recorded, not scored
    },

    # --- COVID-19 Related Myocarditis ---
    "covid19_related": {
        "active_covid19": 0.8,
        "recent_covid_infection": 0.4,
        "mis_c_criteria_met": 0.6,
        "mis_a_criteria_met": 0.6,
        "elevated_d_dimer": 0.2,
    },

    # --- Pre-existing / Autoimmune ---
    "autoimmune_inflammatory": {
        "known_autoimmune_dx": 0.7,
        "positive_ana_dsdna": 0.5,
        "systemic_inflammation": 0.3,
        "granulomas_on_biopsy": 0.9,
    },

    # --- Narrative Nuance (Clinical Doubt) ---
    # These bypass the plausibility gate (they are meta-markers, not pathologies)
    "narrative_nuance": {
        "reporter_uncertainty": 0.3,
        "alternative_suspected": 0.2,
        "lack_of_testing": 0.1,
    },
}

# Build marker registry
ALL_MARKERS = []
MARKER_CATEGORIES = {}
for category, markers in NCI_WEIGHT_MATRIX.items():
    for marker in markers:
        ALL_MARKERS.append(marker)
        MARKER_CATEGORIES[marker] = category

# Narrative nuance markers bypass the plausibility gate
NUANCE_MARKERS = set(NCI_WEIGHT_MATRIX["narrative_nuance"].keys())


# ============================================================
# NCI ENGINE (Deterministic Calculator + Plausibility Gate)
# ============================================================

class NCIEngine:
    """
    Deterministic engine with Biological Plausibility Gate.

    Gate logic per marker:
      IF category == narrative_nuance:
        → Apply weight if present == True (no gate)
      ELSE:
        → Apply weight ONLY if ALL THREE conditions met:
          1. present == True
          2. is_acute_concordant == True
          3. plausibility in ("high", "moderate")
    """

    @staticmethod
    def calculate(llm_findings: dict) -> dict:
        """
        Compute category-level NCI scores with plausibility filtering.

        Args:
            llm_findings: dict of {marker_name: {present, is_acute_concordant, plausibility, biological_rationale}}

        Returns:
            Dict with per-category scores, gate decisions, and overall assessment.
        """
        category_scores = {}

        for category, markers in NCI_WEIGHT_MATRIX.items():
            score = 0.0
            passed_markers = []
            filtered_markers = []
            absent_markers = []

            for marker, weight in markers.items():
                finding = llm_findings.get(marker, {})

                # Handle both 3-dimensional and simple boolean (fallback)
                if isinstance(finding, bool):
                    finding = {"present": finding, "is_acute_concordant": True,
                               "plausibility": "moderate" if finding else "none",
                               "biological_rationale": "Legacy boolean conversion"}

                present = finding.get("present", False)

                if not present:
                    absent_markers.append(marker)
                    continue

                # Narrative nuance bypasses the gate
                if marker in NUANCE_MARKERS:
                    score += weight
                    passed_markers.append({
                        "marker": marker,
                        "weight": weight,
                        "gate": "BYPASS (nuance)",
                        "rationale": finding.get("biological_rationale", ""),
                    })
                    continue

                # === PLAUSIBILITY GATE ===
                is_acute = finding.get("is_acute_concordant", False)
                plausibility = finding.get("plausibility", "none")

                if is_acute and plausibility in ("high", "moderate"):
                    # GATE PASSED — apply weight
                    score += weight
                    passed_markers.append({
                        "marker": marker,
                        "weight": weight,
                        "gate": f"PASSED (acute={is_acute}, plausibility={plausibility})",
                        "rationale": finding.get("biological_rationale", ""),
                    })
                else:
                    # GATE FILTERED — present but not plausible for acute myocarditis
                    filtered_markers.append({
                        "marker": marker,
                        "weight_blocked": weight,
                        "gate": f"FILTERED (acute={is_acute}, plausibility={plausibility})",
                        "rationale": finding.get("biological_rationale", ""),
                    })

            capped_score = round(min(score, 1.0), 2)

            category_scores[category] = {
                "nci_score": capped_score,
                "markers_passed": passed_markers,
                "markers_filtered": filtered_markers,
                "markers_absent": absent_markers,
                "pass_count": len(passed_markers),
                "filter_count": len(filtered_markers),
            }

        # --- Overall assessment (exclude narrative_nuance from max) ---
        clinical_scores = {k: v for k, v in category_scores.items()
                          if k != "narrative_nuance"}
        if clinical_scores:
            max_category = max(clinical_scores, key=lambda k: clinical_scores[k]["nci_score"])
            max_nci = clinical_scores[max_category]["nci_score"]
        else:
            max_category = "none"
            max_nci = 0.0

        # Narrative nuance — DECOUPLED from NCI (v3.1)
        # DESIGN DECISION (v3.1): Narrative nuance (reporter uncertainty,
        # lack of testing, alternative suspected) represents EPISTEMIC GAPS,
        # not clinical evidence of alternative causation. Per WHO AEFI:
        # "other cause" requires POSITIVE evidence, not absence of testing.
        #
        # Nuance is now:
        #   - EXCLUDED from NCI adjusted calculation
        #   - PASSED THROUGH as epistemic_uncertainty for Stage 5 context
        #   - CONSUMED by Stage 6 to prioritize investigative gaps
        #
        # Impact: 8 cases previously A1→B2 due to nuance inflation are restored.
        nuance_score = category_scores.get("narrative_nuance", {}).get("nci_score", 0)

        # WHO Step 1 conclusion — based on CLINICAL NCI ONLY
        if max_nci >= 0.7:
            conclusion = "DEFINITE_OTHER_CAUSE"
        elif max_nci >= 0.4:
            conclusion = "POSSIBLE_OTHER_CAUSE"
        elif max_nci >= 0.2:
            conclusion = "WEAK_ALTERNATIVE"
        else:
            conclusion = "NO_ALTERNATIVE"

        # Total filtered count (noise reduction metric)
        total_filtered = sum(v["filter_count"] for v in category_scores.values())

        return {
            "category_scores": category_scores,
            "max_nci_score": max_nci,
            "max_nci_adjusted": max_nci,  # v3.1: No nuance inflation, adjusted = clinical
            "narrative_nuance_modifier": nuance_score,
            "epistemic_uncertainty": nuance_score,  # v3.1: Passed to Stage 5/6 as context
            "dominant_category": max_category,
            "who_step1_conclusion": conclusion,
            "noise_filtered_count": total_filtered,
        }


# ============================================================
# LLM MARKER EXTRACTION PROMPT (3-Dimensional)
# ============================================================

MARKER_EXTRACTION_PROMPT = """You are a Senior Cardiac Pathologist and Pharmacovigilance Expert.
Your task is to identify clinical markers in the following vaccine safety report
and evaluate their BIOLOGICAL PLAUSIBILITY as causes of ACUTE myocarditis/pericarditis.

For EACH marker, provide a 4-dimensional assessment:
  1. "present": Is this marker found in the narrative? (true/false)
  2. "is_acute_concordant": Can this finding cause ACUTE myocardial inflammation? (true/false)
  3. "plausibility": Biological plausibility as an acute myocarditis cause ("high"/"moderate"/"low"/"none")
  4. "biological_rationale": Epidemiological justification (2-3 sentences) explaining:
     - IF INCLUDED: Why this factor is biologically plausible for the current acute event
       (mechanism of action, temporal relevance, dose-response relationship)
     - IF EXCLUDED: Why this factor is NOISE — explain the pathological mismatch
       (e.g., chronic vs acute pathway, temporal implausibility, mechanism incompatibility)
     This rationale will be directly embedded in the regulatory audit report.

=== GUIDELINES FOR NOISE REDUCTION ===
- PATHOLOGICAL CONCORDANCE: If a condition primarily causes CHRONIC cardiomyopathy
  or fibrosis (e.g., chronic alcohol use, remote chemotherapy >1yr ago, old radiation),
  mark is_acute_concordant = false. Acute myocarditis requires ACUTE inflammatory trigger.
- TEMPORAL FIT: Only exposures within a biologically relevant window (<30 days)
  are acute-concordant. Remote events (months/years ago) are NOT.
- AGE vs DISEASE: Being old (age_over_50=true) is a RISK FACTOR, not a cause.
  Mark is_acute_concordant=true (it's relevant) but plausibility="low" (alone insufficient).

=== MARKERS TO EXTRACT ===

[Viral Etiology]
- fever_reported: Fever/pyrexia at or around symptom onset
- uri_symptoms: Upper respiratory symptoms (cough, rhinorrhea, sore throat)
- gi_symptoms: GI symptoms (diarrhea, vomiting, abdominal pain)
- myalgia_arthralgia: Muscle/joint pain as PRODROMAL symptom (NOT post-vaccine reactogenicity)
- positive_viral_pcr: Confirmed positive viral test (PCR, antigen, culture)
- lymphocytosis: Elevated lymphocyte count

[Giant Cell Myocarditis]
- rapid_heart_failure: Rapidly progressive heart failure
- av_block_present: Atrioventricular block or conduction abnormality
- ventricular_arrhythmia: Ventricular tachycardia or fibrillation
- cardiogenic_shock: Hemodynamic collapse requiring pressors/mechanical support
- giant_cells_on_biopsy: Multinucleated giant cells on biopsy

[Eosinophilic Myocarditis]
- peripheral_eosinophilia: Elevated eosinophil count
- new_medication_history: New medication started recently (hypersensitivity-linked)
- hypersensitivity_rash: Allergic rash or skin manifestations
- eosinophils_on_biopsy: Eosinophilic infiltrate on biopsy

[Toxin / ICI Myocarditis]
- ici_therapy_active: Currently on immune checkpoint inhibitors
- concurrent_myositis: Myositis co-occurrence
- conduction_delay: AV or interventricular conduction delay
- new_chemotherapy: Recent cardiotoxic chemotherapy (e.g., anthracyclines within 6 months)
- elevated_ck: Creatine kinase elevation

[Ischemic Heart Disease]
- age_over_50: Patient age over 50 (RECORD ONLY — risk factor, not a cause of acute myocarditis)
- prior_cad_history: Known coronary artery disease or prior MI
- focal_st_changes: TRULY focal/territorial ST changes suggesting ischemic origin on ECG.
    *** ECG DIFFERENTIATION GUIDE — READ CAREFULLY ***
    Set TRUE only if ST changes are in a SINGLE CORONARY TERRITORY:
      - Inferior only (II, III, aVF) → possibly RCA territory
      - Anterior only (V1-V4) → possibly LAD territory
      - Lateral only (I, aVL, V5-V6) → possibly LCx territory
    Set FALSE if ANY of these patterns:
      - DIFFUSE ST elevation across multiple territories (e.g., anterior + inferior)
      - CONTIGUOUS precordial (V2-V5 or V1-V6) = typical myocarditis pattern
      - "Early repolarization" or "benign variant" = not pathologic
      - "Diffuse", "widespread", "global" ST changes = myocarditis, not ischemic
      - ST changes described without specific lead distribution = cannot determine → FALSE
      - Concave-up ST elevation = pericarditis/myocarditis pattern, not ischemic
    In myocarditis context, most ST changes are inflammatory (diffuse), NOT ischemic (focal).
- positive_catheterization: Catheterization showed coronary obstruction
- diabetes_hypertension: Diabetes or hypertension documented (RECORD ONLY — risk factor)
- smoking_history: Smoking history (RECORD ONLY — risk factor)

[COVID-19 Related]
- active_covid19: Concurrent lab-confirmed COVID-19 at symptom onset
- recent_covid_infection: COVID-19 within 4 weeks before cardiac onset
- mis_c_criteria_met: MIS-C criteria (pediatric)
- mis_a_criteria_met: MIS-A criteria (adult)
- elevated_d_dimer: D-dimer elevation

[Autoimmune / Inflammatory]
- known_autoimmune_dx: Known autoimmune disease (SLE, sarcoidosis, RA)
- positive_ana_dsdna: Positive ANA, anti-dsDNA, or other autoimmune markers
- systemic_inflammation: Multi-organ inflammatory signs beyond cardiac
- granulomas_on_biopsy: Granulomas on biopsy

[Narrative Nuance]
- reporter_uncertainty: Reporter/clinician expresses uncertainty about cause
- alternative_suspected: Narrative mentions possible non-vaccine cause
- lack_of_testing: Narrative states viral/other testing was NOT done

=== OUTPUT FORMAT ===
Respond ONLY with valid JSON. Each marker as a key with the 4-field object:

{
  "fever_reported": {
    "present": true,
    "is_acute_concordant": true,
    "plausibility": "moderate",
    "biological_rationale": "Fever concurrent with cardiac symptom onset suggests an active infectious or inflammatory process. Viral myocarditis typically presents with fever as part of the prodromal phase, making this finding biologically plausible as an indicator of an alternative acute etiology."
  },
  "new_chemotherapy": {
    "present": true,
    "is_acute_concordant": false,
    "plausibility": "low",
    "biological_rationale": "Patient received radiation therapy in 2003, approximately 18 years prior to the cardiac event. Radiation-induced cardiotoxicity follows a chronic fibrotic pathway (Type I cardiotoxicity) with latency periods of years to decades. This chronic mechanism is pathologically incompatible with the current acute inflammatory presentation. Excluded as noise."
  },
  ...
}

=== CRITICAL RULES ===
1. Respond ONLY with valid JSON — no explanation outside the JSON.
2. Include ALL 38 markers, even if present=false.
3. For myalgia_arthralgia: ONLY present=true if PRODROMAL, not post-vaccine reactogenicity.
4. For narrative nuance markers: is_acute_concordant and plausibility are not applicable,
   set is_acute_concordant=true and plausibility="moderate" if present.
5. For age_over_50: If present, is_acute_concordant=true but plausibility="low"
   (risk factor, not direct cause).
6. biological_rationale is MANDATORY for all markers where present=true.
   For present=false markers, set biological_rationale to "Not identified in narrative."
7. For EXCLUDED (filtered) markers: The rationale MUST explain the pathological mismatch —
   why this finding cannot explain the current ACUTE myocardial inflammation.
   Example: "Prostate cancer XRT in 2003 follows a chronic radiation-induced fibrotic pathway.
   This mechanism requires years to decades to manifest and produces diastolic dysfunction,
   not acute inflammatory myocarditis. Excluded as temporally and mechanistically implausible."
"""


# ============================================================
# MAIN EXECUTION
# ============================================================

def run_stage3(
    llm: LLMClient,
    icsr_data: dict,
    brighton_data: dict,
    original_narrative: str,
) -> dict:
    """
    Execute WHO Step 1 — Hybrid DDx with Plausibility Gate.

    Layer 1-3: LLM extracts 3-dimensional markers (observe + classify)
    Layer 4:   NCIEngine computes scores with plausibility filtering (calculate)
    Layer 5:   Threshold-based WHO Step 1 conclusion (decide)
    """
    vaers_id = icsr_data.get("vaers_id")

    # --- Layer 1-3: LLM as Clinical Observer + Pathologist ---
    user_message = (
        f"Extract and evaluate clinical markers from this VAERS report.\n\n"
        f"=== STRUCTURED DATA (for reference) ===\n"
        f"Patient: {json.dumps(icsr_data.get('demographics', {}))}\n"
        f"Vaccine: {json.dumps(icsr_data.get('vaccine', {}))}\n"
        f"Event: {json.dumps(icsr_data.get('event', {}))}\n"
        f"Clinical: {json.dumps(icsr_data.get('clinical_data', {}))}\n"
        f"History: {json.dumps(icsr_data.get('medical_history', {}))}\n\n"
        f"=== ORIGINAL NARRATIVE ===\n"
        f"{original_narrative}\n"
    )

    raw_findings = llm.query_json(
        system_prompt=MARKER_EXTRACTION_PROMPT,
        user_message=user_message,
    )

    # --- Validate and normalize LLM output ---
    cleaned_findings = {}
    for marker in ALL_MARKERS:
        val = raw_findings.get(marker, {})

        if isinstance(val, bool):
            # Legacy boolean fallback
            cleaned_findings[marker] = {
                "present": val,
                "is_acute_concordant": True,
                "plausibility": "moderate" if val else "none",
                "biological_rationale": "Legacy boolean conversion",
            }
        elif isinstance(val, dict):
            cleaned_findings[marker] = {
                "present": bool(val.get("present", False)),
                "is_acute_concordant": bool(val.get("is_acute_concordant", False)),
                "plausibility": str(val.get("plausibility", "none")).lower(),
                "biological_rationale": str(val.get("biological_rationale", "")),
            }
        else:
            cleaned_findings[marker] = {
                "present": False,
                "is_acute_concordant": False,
                "plausibility": "none",
                "biological_rationale": "Not found in LLM output",
            }

    # --- Layer 4: Deterministic NCI Calculation with Plausibility Gate ---
    nci_result = NCIEngine.calculate(cleaned_findings)

    # --- Build information gaps ---
    information_gaps = _identify_gaps(cleaned_findings, nci_result)

    # --- Build output (backward compatible with Stage 5) ---
    alternative_etiologies = []
    for cat_name, cat_data in nci_result["category_scores"].items():
        if cat_name == "narrative_nuance":
            continue
        if cat_data["nci_score"] > 0 or cat_data["filter_count"] > 0:
            status = _determine_status(cat_data) if cat_data["nci_score"] > 0 else "FILTERED"
            alternative_etiologies.append({
                "etiology": _category_label(cat_name),
                "nci_score": cat_data["nci_score"],
                "evidence_included": [
                    {
                        "marker": m["marker"],
                        "weight": m["weight"],
                        "gate": m["gate"],
                        "rationale": m.get("rationale", ""),
                    }
                    for m in cat_data["markers_passed"]
                ],
                "evidence_excluded": [
                    {
                        "marker": m["marker"],
                        "weight_blocked": m["weight_blocked"],
                        "gate": m["gate"],
                        "rationale": m.get("rationale", ""),
                    }
                    for m in cat_data["markers_filtered"]
                ],
                "status": status,
            })

    alternative_etiologies.sort(key=lambda x: x["nci_score"], reverse=True)

    # Dominant alternative (excluding narrative_nuance)
    non_nuance = {k: v for k, v in nci_result["category_scores"].items()
                  if k != "narrative_nuance"}
    if non_nuance:
        dominant_cat = max(non_nuance, key=lambda k: non_nuance[k]["nci_score"])
        dominant_nci = non_nuance[dominant_cat]["nci_score"]
        dominant_label = _category_label(dominant_cat) if dominant_nci > 0 else "NONE"
    else:
        dominant_label = "NONE"
        dominant_nci = 0.0

    return {
        "vaers_id": vaers_id,
        "engine": "HYBRID (LLM-Observer + Plausibility-Gate + NCI-WeightMatrix)",
        "llm_markers_extracted": cleaned_findings,
        "nci_detailed": nci_result["category_scores"],
        "alternative_etiologies": alternative_etiologies,
        "max_nci_score": nci_result["max_nci_score"],
        "max_nci_adjusted": nci_result["max_nci_score"],  # v3.1: adjusted = clinical (no nuance)
        "narrative_nuance_modifier": nci_result.get("narrative_nuance_modifier", 0),
        "epistemic_uncertainty": nci_result.get("epistemic_uncertainty", 0),  # v3.1
        "dominant_alternative": dominant_label,
        "who_step1_conclusion": nci_result["who_step1_conclusion"],
        "narrative_nuance": nci_result["category_scores"].get("narrative_nuance", {}),
        "noise_filtered_count": nci_result.get("noise_filtered_count", 0),
        "information_gaps": information_gaps,
    }


def _determine_status(cat_data: dict) -> str:
    """Map NCI score to evidence status."""
    score = cat_data["nci_score"]
    has_definitive = any(m["weight"] >= 0.8 for m in cat_data["markers_passed"])
    if has_definitive:
        return "CONFIRMED"
    if score >= 0.4:
        return "SUSPECTED"
    if score > 0:
        return "NOT_EVALUATED"
    return "EXCLUDED"


def _category_label(cat_name: str) -> str:
    """Human-readable category names."""
    labels = {
        "viral_etiology": "Viral myocarditis (infectious)",
        "giant_cell_myocarditis": "Giant cell myocarditis",
        "eosinophilic_myocarditis": "Eosinophilic myocarditis",
        "toxin_ici_myocarditis": "Toxin/ICI-induced myocarditis",
        "ischemic_heart_disease": "Ischemic heart disease (CAD/MI)",
        "covid19_related": "COVID-19 related myocarditis",
        "autoimmune_inflammatory": "Autoimmune/inflammatory myocarditis",
        "narrative_nuance": "Narrative clinical doubt",
    }
    return labels.get(cat_name, cat_name)


def _identify_gaps(findings: dict, nci_result: dict) -> list:
    """Identify investigation gaps based on what was NOT tested/evaluated."""
    gaps = []

    fever = findings.get("fever_reported", {})
    viral = findings.get("positive_viral_pcr", {})

    if not viral.get("present") and fever.get("present"):
        gaps.append("Viral testing (PCR/serology) not performed despite fever")
    elif not viral.get("present") and not fever.get("present"):
        gaps.append("Viral testing status unknown — cannot exclude viral etiology")

    # Biopsy gap for severe cases
    rhf = findings.get("rapid_heart_failure", {})
    cs = findings.get("cardiogenic_shock", {})
    gcb = findings.get("giant_cells_on_biopsy", {})
    eob = findings.get("eosinophils_on_biopsy", {})
    if rhf.get("present") or cs.get("present"):
        if not gcb.get("present") and not eob.get("present"):
            gaps.append("Endomyocardial biopsy not performed despite severe presentation")

    # Catheterization gap for older patients
    age50 = findings.get("age_over_50", {})
    cath = findings.get("positive_catheterization", {})
    cad = findings.get("prior_cad_history", {})
    if age50.get("present") and not cath.get("present") and not cad.get("present"):
        gaps.append("Coronary evaluation not documented for patient >50yo")

    # Autoimmune workup
    si = findings.get("systemic_inflammation", {})
    ana = findings.get("positive_ana_dsdna", {})
    if si.get("present") and not ana.get("present"):
        gaps.append("Autoimmune markers (ANA, dsDNA) not tested despite systemic inflammation")

    # COVID testing
    rci = findings.get("recent_covid_infection", {})
    ac = findings.get("active_covid19", {})
    if rci.get("present") and not ac.get("present"):
        gaps.append("Active COVID-19 status at cardiac onset not confirmed")

    # Narrative-driven gaps
    lot = findings.get("lack_of_testing", {})
    ru = findings.get("reporter_uncertainty", {})
    if lot.get("present"):
        gaps.append("Reporter explicitly noted testing was not performed")
    if ru.get("present"):
        gaps.append("Treating clinician expressed diagnostic uncertainty")

    # Noise reduction feedback
    total_filtered = nci_result.get("noise_filtered_count", 0)
    if total_filtered > 0:
        gaps.append(f"Plausibility gate filtered {total_filtered} marker(s) — chronic/non-concordant findings excluded from NCI")

    # Inflammatory markers
    cat_scores = nci_result.get("category_scores", {})
    if cat_scores.get("viral_etiology", {}).get("nci_score", 0) > 0:
        gaps.append("Inflammatory markers (CRP, ESR) needed to differentiate viral vs vaccine")

    return gaps
