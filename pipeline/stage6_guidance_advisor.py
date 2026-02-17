"""
Vax-Beacon v4 | Stage 6: Guidance Advisor (LLM) — Reporting
================================================================
Final report generation, gap analysis, and HITL guidance.
Handles both normal flow and Early Exit (Brighton L4) cases.

v4 change: DDx-specific investigation guidance is loaded from
knowledge/investigation_protocols.json at runtime instead of
being hardcoded in the prompt.
"""

import json
from llm_client import LLMClient
from prompts.system_prompts import (
    STAGE6_GUIDANCE_ADVISOR,
    STAGE6_EARLY_EXIT,
    STAGE6_ONSET_UNKNOWN,
    STAGE6_BRIGHTON_EXIT,
)


# Reverse mapping: human-readable label → subtype key
_LABEL_TO_KEY = {
    "Viral myocarditis (infectious)": "viral_etiology",
    "Giant cell myocarditis": "giant_cell_myocarditis",
    "Eosinophilic myocarditis": "eosinophilic_myocarditis",
    "Toxin/ICI-induced myocarditis": "toxin_ici_myocarditis",
    "Ischemic heart disease (CAD/MI)": "ischemic_heart_disease",
    "COVID-19 related myocarditis": "covid19_related",
    "Autoimmune/inflammatory myocarditis": "autoimmune_inflammatory",
}


def _get_protocol_for_dominant(dominant_label: str, protocols_db: dict) -> dict:
    """
    Map a dominant_alternative label to its investigation protocol from the DB.

    Args:
        dominant_label: Human-readable label from Stage 3 dominant_alternative
                        (e.g., "Giant cell myocarditis")
        protocols_db: Loaded investigation_protocols.json content

    Returns:
        Protocol dict with label, why_suspected, investigations — or empty dict
    """
    # Try exact label match first
    subtype_key = _LABEL_TO_KEY.get(dominant_label)

    # Fallback: case-insensitive partial match
    if not subtype_key:
        label_lower = dominant_label.lower()
        for label, key in _LABEL_TO_KEY.items():
            if label.lower() in label_lower or label_lower in label.lower():
                subtype_key = key
                break

    if not subtype_key:
        return {}

    protocols = protocols_db.get("protocols", {})
    return protocols.get(subtype_key, {})


def _format_protocol_context(protocol: dict) -> str:
    """
    Format a protocol dict into a readable text block for prompt injection.

    Returns:
        Formatted string, or empty string if no protocol.
    """
    if not protocol:
        return ""

    label = protocol.get("label", "Unknown")
    why = protocol.get("why_suspected", "")
    investigations = protocol.get("investigations", [])

    lines = [
        f"=== INVESTIGATION PROTOCOL: {label} ===",
        f"Why suspected: {why}",
        "",
        "Required investigations:",
    ]

    for inv in investigations:
        test = inv.get("test", "")
        priority = inv.get("priority", "MEDIUM")
        rationale = inv.get("rationale", "")
        indication = inv.get("indication", "")
        expected = inv.get("expected_finding", "")
        diff_vaccine = inv.get("differential_from_vaccine", "")

        lines.append(f"- {priority}: {test}")
        lines.append(f"  Rationale: {rationale}")
        if indication:
            lines.append(f"  Indication: {indication}")
        if expected:
            lines.append(f"  Expected finding: {expected}")
        if diff_vaccine:
            lines.append(f"  Differential from vaccine: {diff_vaccine}")

    lines.append("=== END PROTOCOL ===")
    return "\n".join(lines)


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


def _has_covid_suspect(ddx_data: dict) -> bool:
    """Check if active_covid19 marker is present in Stage 3 output."""
    if not ddx_data:
        return False
    markers = ddx_data.get("llm_markers_extracted", {})
    active_covid = markers.get("active_covid19", {})
    return active_covid.get("present", False)


def _format_covid_nucleocapsid_supplement() -> str:
    """Return supplementary nucleocapsid guidance for non-COVID-dominant cases."""
    return (
        "\n=== SUPPLEMENTARY: COVID-19 DIFFERENTIATION ===\n"
        "COVID-19 infection was detected in this patient's history.\n"
        "Even though COVID-19 is not the dominant alternative etiology,\n"
        "nucleocapsid antibody testing is recommended to differentiate\n"
        "natural infection from vaccination-only immune response.\n"
        "mRNA vaccines produce only spike protein antibody, NOT nucleocapsid.\n"
        "Positive nucleocapsid = prior natural infection confirmed.\n"
        "Include nucleocapsid antibody test in investigative gaps.\n"
        "=== END SUPPLEMENTARY ===\n"
    )


def _identify_missing_brighton_criteria(criteria_met: dict, condition_type: str) -> list:
    """
    Identify missing Brighton criteria needed to upgrade from Level 4.

    Returns a list of dicts describing each missing criterion and what it would achieve.
    """
    missing = []

    if condition_type == "pericarditis":
        # Pericarditis Brighton: symptoms, ECG, effusion (count-based), inflammatory markers
        if not criteria_met.get("compatible_symptoms"):
            missing.append({
                "criterion": "compatible_symptoms",
                "label": "Compatible pericarditis symptoms",
                "description": "Chest pain (pleuritic, positional), pericardial friction rub",
                "tests_needed": ["Detailed symptom review", "Physical examination for friction rub"],
                "achievable_level": "Level 3 (with 1 criterion) or Level 1 (with 2+)",
            })
        if not criteria_met.get("ecg_abnormal"):
            missing.append({
                "criterion": "ecg_abnormal",
                "label": "ECG abnormalities",
                "description": "Diffuse ST elevation, PR depression, new T-wave changes",
                "tests_needed": ["12-lead ECG", "Serial ECGs if initial was normal"],
                "achievable_level": "Level 3 (with 1 criterion) or Level 1 (with 2+)",
            })
        if not criteria_met.get("pericardial_effusion"):
            missing.append({
                "criterion": "pericardial_effusion",
                "label": "Pericardial effusion",
                "description": "Pericardial fluid collection on imaging",
                "tests_needed": ["Transthoracic echocardiogram (TTE)"],
                "achievable_level": "Level 3 (with 1 criterion) or Level 1 (with 2+)",
            })
        if not criteria_met.get("inflammatory_markers_elevated"):
            missing.append({
                "criterion": "inflammatory_markers_elevated",
                "label": "Elevated inflammatory markers",
                "description": "CRP, ESR elevation supporting pericardial inflammation",
                "tests_needed": ["CRP", "ESR", "CBC with differential"],
                "achievable_level": "Supports Level 2 (with 1+ core criterion)",
            })
    else:
        # Myocarditis Brighton criteria
        if not criteria_met.get("compatible_symptoms"):
            missing.append({
                "criterion": "compatible_symptoms",
                "label": "Compatible myocarditis symptoms",
                "description": "Chest pain, dyspnea, palpitations, syncope, heart failure symptoms",
                "tests_needed": ["Detailed symptom history review"],
                "achievable_level": "Required for Level 2-3",
            })
        if not criteria_met.get("troponin_elevated"):
            missing.append({
                "criterion": "troponin_elevated",
                "label": "Elevated cardiac troponin",
                "description": "Troponin I or T above 99th percentile upper reference limit",
                "tests_needed": ["High-sensitivity troponin I or T", "Serial troponin if initial borderline"],
                "achievable_level": "Required for Level 1-2; supports Level 3",
            })
        if not criteria_met.get("ecg_abnormal"):
            missing.append({
                "criterion": "ecg_abnormal",
                "label": "ECG abnormalities",
                "description": "ST-T changes, conduction abnormalities, arrhythmias",
                "tests_needed": ["12-lead ECG", "Continuous telemetry if arrhythmia suspected"],
                "achievable_level": "Supports Level 2 (with troponin + symptoms)",
            })
        if not criteria_met.get("echo_abnormal"):
            missing.append({
                "criterion": "echo_abnormal",
                "label": "Echocardiographic abnormalities",
                "description": "Wall motion abnormalities, reduced EF, pericardial effusion",
                "tests_needed": ["Transthoracic echocardiogram (TTE)"],
                "achievable_level": "Supports Level 2 (with troponin + symptoms)",
            })
        if not criteria_met.get("cardiac_mri_positive"):
            missing.append({
                "criterion": "cardiac_mri_positive",
                "label": "Cardiac MRI positive (Lake Louise criteria)",
                "description": "T2 edema + LGE (Late Gadolinium Enhancement) per Lake Louise criteria",
                "tests_needed": [
                    "Cardiac MRI with T2 mapping and LGE",
                    "Assess for myocardial inflammation presence",
                    "Evaluate involvement extent (focal vs diffuse)",
                ],
                "achievable_level": "Level 1 (with troponin + symptoms) or Level 2 (with troponin + symptoms)",
            })
        if not criteria_met.get("histopathology"):
            missing.append({
                "criterion": "histopathology",
                "label": "Histopathological confirmation (EMB)",
                "description": "Endomyocardial biopsy showing inflammatory infiltrate with myocyte necrosis (Dallas criteria)",
                "tests_needed": ["Endomyocardial biopsy (EMB) — invasive, consider risk-benefit"],
                "achievable_level": "Level 1 (definitive, standalone)",
            })

    return missing


def _run_brighton_exit(llm, icsr_data: dict, brighton_data: dict) -> dict:
    """Brighton Level 4 early exit with structured missing-criteria guidance."""
    criteria = brighton_data.get("criteria_met", {})
    condition = brighton_data.get("condition_type", "myocarditis")
    missing = _identify_missing_brighton_criteria(criteria, condition)

    combined_input = {
        "icsr": icsr_data,
        "stage2_brighton": brighton_data,
        "missing_criteria_analysis": missing,
    }

    prompt = STAGE6_BRIGHTON_EXIT

    result = llm.query_json(
        system_prompt=prompt,
        user_message=(
            f"Generate Brighton Level 4 exit guidance for this {condition} case.\n\n"
            f"Missing criteria analysis (code-identified):\n"
            f"{json.dumps(missing, indent=2)}\n\n"
            f"Full case data:\n"
            f"{json.dumps(combined_input, indent=2)}"
        ),
    )

    # Ensure standardized Unclassifiable output fields
    result["who_category"] = "Unclassifiable"
    result["unclassifiable_reason"] = "brighton_insufficient"
    result["mode"] = "brighton_exit"
    result["early_exit"] = True
    result["missing_brighton_criteria"] = missing

    return result


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
    """
    Generate HITL guidance report.
    Handles both normal flow and Early Exit (Brighton L4) cases.

    Args:
        llm: LLM client instance
        icsr_data: Structured ICSR from Stage 1
        brighton_data: Brighton assessment from Stage 2
        ddx_data: DDx assessment from Stage 3
        temporal_data: Temporal + Known AE from Stage 4
        causality_data: Causality classification from Stage 5
        knowledge_db: Loaded knowledge DB (ddx + protocols)
        early_exit: True if Brighton L4 early exit

    Returns:
        HITL guidance report dict
    """
    if early_exit:
        return _run_brighton_exit(llm, icsr_data, brighton_data)

    # Fetch protocol for dominant alternative from knowledge DB
    dominant = ddx_data.get("dominant_alternative", "NONE") if ddx_data else "NONE"
    protocol = {}
    if knowledge_db and dominant != "NONE":
        protocols_db = knowledge_db.get("protocols", {})
        protocol = _get_protocol_for_dominant(dominant, protocols_db)

    # v4.1b: onset unknown routing
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

    # v4.1b-r3: COVID nucleocapsid supplement for non-COVID-dominant cases
    dominant_label = (ddx_data or {}).get("dominant_alternative", "NONE")
    dominant_key = _LABEL_TO_KEY.get(dominant_label, "")
    if _has_covid_suspect(ddx_data) and dominant_key != "covid19_related":
        protocol_context += _format_covid_nucleocapsid_supplement()

    # v4.1b: temporal investigation context
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

    # Ensure standardized Unclassifiable output fields
    result["who_category"] = "Unclassifiable"
    result["unclassifiable_reason"] = "onset_unknown"
    result["mode"] = "onset_unknown"
    result["early_exit"] = False  # Full pipeline was executed

    return result


def _run_early_exit(llm, icsr_data, brighton_data) -> dict:
    """Early Exit: Brighton Level 4, insufficient diagnostic evidence."""
    combined_input = {
        "icsr": icsr_data,
        "stage2_brighton": brighton_data,
    }

    result = llm.query_json(
        system_prompt=STAGE6_EARLY_EXIT,
        user_message=(
            "Generate Early Exit report for this Brighton Level 4 case:\n\n"
            f"{json.dumps(combined_input, indent=2)}"
        ),
    )
    return result
