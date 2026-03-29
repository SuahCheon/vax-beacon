"""
Vax-Beacon v4 | Stage 3D: NCI Calculator (Deterministic Code)
=================================================================
100% deterministic NCI score calculation with Plausibility Gate.
Moved from v3.1's stage3_ddx_specialist.py NCIEngine — logic unchanged.

Input:  Stage 3C output (cleaned_findings) + ddx_myocarditis.json
Output: Same structure as v3.1 Stage 3 output (backward compatible)

Also contains merge_stage3() to combine 3A-3D into the unified output.
"""


# ============================================================
# NCI WEIGHT MATRIX (loaded from code, verified against DB)
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
        "high_degree_av_block": 0.5,
        "ventricular_arrhythmia": 0.5,
        "cardiogenic_shock": 0.4,
        "giant_cells_on_biopsy": 1.0,
    },

    # --- Eosinophilic Myocarditis (EM) ---
    "eosinophilic_myocarditis": {
        "peripheral_eosinophilia": 0.5,
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
    "ischemic_heart_disease": {
        "age_over_50": 0.0,             # Risk factor only
        "prior_cad_history": 0.5,
        "focal_st_changes": 0.5,
        "positive_catheterization": 1.0,
        "diabetes_hypertension": 0.0,   # Risk factor only
        "smoking_history": 0.0,         # Risk factor only
    },

    # --- COVID-19 Related Myocarditis ---
    "covid19_related": {
        "active_covid19": 0.8,
        "mis_c_criteria_met": 0.6,
        "mis_a_criteria_met": 0.6,
        "elevated_d_dimer": 0.2,
    },

    # --- Pre-existing / Autoimmune ---
    "autoimmune_inflammatory": {
        "known_autoimmune_dx": 0.5,
        "positive_ana_dsdna": 0.5,
        "systemic_inflammation": 0.3,
        "granulomas_on_biopsy": 0.9,
    },

    # --- Narrative Nuance (Clinical Doubt) ---
    "narrative_nuance": {
        "reporter_uncertainty": 0.3,
        "alternative_suspected": 0.2,
        "lack_of_testing": 0.1,
    },
}

# Build marker registry
ALL_MARKERS = []
MARKER_CATEGORIES = {}
for _category, _markers in NCI_WEIGHT_MATRIX.items():
    for _marker in _markers:
        ALL_MARKERS.append(_marker)
        MARKER_CATEGORIES[_marker] = _category

# Narrative nuance markers bypass the plausibility gate
NUANCE_MARKERS = set(NCI_WEIGHT_MATRIX["narrative_nuance"].keys())


# ============================================================
# NCI ENGINE (Deterministic Calculator + Plausibility Gate)
# ============================================================

class NCIEngine:
    """
    Deterministic engine with Biological Plausibility Gate.
    Identical to v3.1 — logic unchanged.
    """

    @staticmethod
    def calculate(llm_findings: dict) -> dict:
        """
        Compute category-level NCI scores with plausibility filtering.

        Args:
            llm_findings: dict of {marker_name: {present, is_acute_concordant,
                          plausibility, biological_rationale}}

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
                    finding = {
                        "present": finding,
                        "is_acute_concordant": True,
                        "plausibility": "moderate" if finding else "none",
                        "biological_rationale": "Legacy boolean conversion",
                    }

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
                    # GATE FILTERED
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
        clinical_scores = {
            k: v for k, v in category_scores.items()
            if k != "narrative_nuance"
        }
        if clinical_scores:
            max_category = max(
                clinical_scores,
                key=lambda k: clinical_scores[k]["nci_score"],
            )
            max_nci = clinical_scores[max_category]["nci_score"]
        else:
            max_category = "none"
            max_nci = 0.0

        # Narrative nuance — DECOUPLED from NCI (v3.1 design)
        nuance_score = category_scores.get(
            "narrative_nuance", {},
        ).get("nci_score", 0)

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
            "max_nci_adjusted": max_nci,
            "narrative_nuance_modifier": nuance_score,
            "epistemic_uncertainty": nuance_score,
            "dominant_category": max_category,
            "who_step1_conclusion": conclusion,
            "noise_filtered_count": total_filtered,
        }


# ============================================================
# HELPER FUNCTIONS (from v3.1)
# ============================================================

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
    ac = findings.get("active_covid19", {})
    if ac.get("present") and ac.get("plausibility") in ("low", "none"):
        gaps.append("COVID-19 infection documented but temporal relationship to cardiac onset unclear")

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
        gaps.append(
            f"Plausibility gate filtered {total_filtered} marker(s) "
            "— chronic/non-concordant findings excluded from NCI"
        )

    # Inflammatory markers
    cat_scores = nci_result.get("category_scores", {})
    if cat_scores.get("viral_etiology", {}).get("nci_score", 0) > 0:
        gaps.append(
            "Inflammatory markers (CRP, ESR) needed to differentiate viral vs vaccine"
        )

    return gaps


# ============================================================
# STAGE 3D: NCI CALCULATION
# ============================================================

def run_stage3d(stage3c_output: dict, ddx_db: dict) -> dict:
    """
    Stage 3D: Deterministic NCI calculation from Stage 3C findings.

    Args:
        stage3c_output: Dict of {marker_name: {present, is_acute_concordant,
                        plausibility, biological_rationale}} from Stage 3C
        ddx_db: Loaded ddx_myocarditis.json content (for future DB weight loading)

    Returns:
        NCI calculation result (same structure as v3.1 NCIEngine output)
    """
    return NCIEngine.calculate(stage3c_output)


# ============================================================
# MERGE FUNCTION: Combine 3A-3D into v3.1 Stage 3 output
# ============================================================

def merge_stage3(
    stage3a: dict,
    stage3b: dict,
    stage3c: dict,
    stage3d: dict,
    vaers_id: int = None,
) -> dict:
    """
    Combine Stage 3A-3D results into v3.1-compatible Stage 3 output.

    The output structure MUST match the keys expected by Stage 4, 5, and 6.

    Args:
        stage3a: Clinical Observer output
        stage3b: DDx Matcher output
        stage3c: Plausibility Assessor output (cleaned_findings dict)
        stage3d: NCI Calculator output
        vaers_id: VAERS case ID for the output

    Returns:
        Dict matching v3.1 run_stage3() output structure exactly
    """
    nci_result = stage3d  # stage3d IS the NCIEngine.calculate() result

    # Build information gaps
    information_gaps = _identify_gaps(stage3c, nci_result)

    # Build alternative_etiologies list (same as v3.1)
    alternative_etiologies = []
    for cat_name, cat_data in nci_result["category_scores"].items():
        if cat_name == "narrative_nuance":
            continue
        if cat_data["nci_score"] > 0 or cat_data["filter_count"] > 0:
            status = (
                _determine_status(cat_data) if cat_data["nci_score"] > 0
                else "FILTERED"
            )
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
    non_nuance = {
        k: v for k, v in nci_result["category_scores"].items()
        if k != "narrative_nuance"
    }
    if non_nuance:
        dominant_cat = max(
            non_nuance,
            key=lambda k: non_nuance[k]["nci_score"],
        )
        dominant_nci = non_nuance[dominant_cat]["nci_score"]
        dominant_label = (
            _category_label(dominant_cat) if dominant_nci > 0 else "NONE"
        )
    else:
        dominant_label = "NONE"

    return {
        "vaers_id": vaers_id,
        "engine": "v4 TWO-PASS (3A-Observer + 3B-Matcher + 3C-Assessor + 3D-NCI)",
        "llm_markers_extracted": stage3c,
        "nci_detailed": nci_result["category_scores"],
        "alternative_etiologies": alternative_etiologies,
        "max_nci_score": nci_result["max_nci_score"],
        "max_nci_adjusted": nci_result["max_nci_score"],
        "narrative_nuance_modifier": nci_result.get("narrative_nuance_modifier", 0),
        "epistemic_uncertainty": nci_result.get("epistemic_uncertainty", 0),
        "dominant_alternative": dominant_label,
        "who_step1_conclusion": nci_result["who_step1_conclusion"],
        "narrative_nuance": nci_result["category_scores"].get("narrative_nuance", {}),
        "noise_filtered_count": nci_result.get("noise_filtered_count", 0),
        "information_gaps": information_gaps,
        # v4 additions: preserve sub-stage outputs for auditability
        "v4_stage3a": stage3a,
        "v4_stage3b": stage3b,
    }
