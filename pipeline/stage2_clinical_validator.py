"""
Stage 2: Clinical Validator (Rule-based) — Gatekeeper
=======================================================
WHO Step 0: Is there a valid diagnosis?
Brighton Collaboration diagnostic certainty level assignment.
Deterministic: no LLM, no hallucination.

Brighton Level 4 → Early Exit to Stage 6.

v4.3: Pending/ordered clinical data override — tests that were ordered
but not completed are NOT treated as positive findings.
"""

# --- Pending/Ordered status detection (v4.3) ---
PENDING_KEYWORDS = [
    "ordered", "pending", "not completed", "not yet",
    "scheduled", "awaiting", "planned", "requested",
    "to be done", "not available", "not performed",
    "not obtained", "awaited",
]


def _is_pending_status(value: str) -> bool:
    """Detect if a clinical data value indicates pending/ordered status.

    Returns True if the value describes a test that was ordered but
    not completed — should NOT be treated as a positive finding.
    """
    if not value:
        return False
    lower = value.lower().strip()
    return any(kw in lower for kw in PENDING_KEYWORDS)


def run_stage2(icsr_data: dict) -> dict:
    """
    Assign Brighton Level based on structured ICSR data.
    Pure rule-based: deterministic, auditable, zero hallucination.
    """
    vaers_id = icsr_data.get("vaers_id")
    clinical = icsr_data.get("clinical_data", {})
    event = icsr_data.get("event", {})

    # --- Extract criteria from structured ICSR ---
    troponin = clinical.get("troponin", {})
    troponin_elevated = troponin.get("elevated") is True

    ecg = clinical.get("ecg_findings")
    ecg_str = str(ecg).strip() if ecg else ""
    ecg_lower = ecg_str.lower()
    # ECG abnormal: positive findings override "normal sinus rhythm"
    _ecg_positive_findings = (
        "abnormal" in ecg_lower
        or "st elevation" in ecg_lower or "st-elevation" in ecg_lower
        or "st depression" in ecg_lower or "st-depression" in ecg_lower
        or "st change" in ecg_lower or "st segment" in ecg_lower
        or "bundle branch block" in ecg_lower
        or "t wave" in ecg_lower
        or "pr depression" in ecg_lower
    )
    ecg_abnormal = (
        ecg is not None
        and ecg_str != ""
        and not _is_pending_status(ecg_str)
        and (
            _ecg_positive_findings
            or (
                "normal" not in ecg_lower
                and "negative" not in ecg_lower
                and "unremarkable" not in ecg_lower
            )
        )
    )

    echo = clinical.get("echo_findings")
    echo_str = str(echo).strip() if echo else ""
    echo_lower = echo_str.lower()
    echo_abnormal = (
        echo is not None
        and echo_str != ""
        and "normal" not in echo_lower
        and "negative" not in echo_lower
        and "unremarkable" not in echo_lower
        and "no " not in echo_lower[:20]
        and not _is_pending_status(echo_str)
    )

    mri = clinical.get("cardiac_mri")
    mri_str = str(mri).strip() if mri else ""
    # MRI positive: LGE/enhancement/edema keywords override "normal LVEF"
    mri_lower = mri_str.lower()
    _mri_positive_findings = (
        "abnormal" in mri_lower
        or "enhancement" in mri_lower
        or "lge" in mri_lower
        or "edema" in mri_lower or "oedema" in mri_lower
        or "myocarditis" in mri_lower
    )
    mri_positive = (
        mri is not None
        and mri_str != ""
        and not _is_pending_status(mri_str)
        and (
            _mri_positive_findings
            or (
                "normal" not in mri_lower
                and "negative" not in mri_lower
            )
        )
    )

    # Histopathology (endomyocardial biopsy) — with negation detection
    histopathology = False
    symptoms_list = event.get("symptoms", [])
    narrative = event.get("narrative_summary", "")
    full_text = (" ".join(symptoms_list) + " " + narrative).lower()
    _biopsy_mentioned = any(term in full_text for term in ["biopsy", "endomyocardial", "histopath"])
    _biopsy_negated = any(neg in full_text for neg in [
        "not performed", "no biopsy", "without biopsy", "biopsy was not",
        "no endomyocardial", "without pathological evidence",
        "biopsy not", "not done",
    ])
    if _biopsy_mentioned and not _biopsy_negated:
        histopathology = True

    # Compatible symptoms
    compatible_symptoms = any(
        term in full_text
        for term in ["chest pain", "dyspnea", "palpitation", "heart failure",
                     "shortness of breath", "cardiac", "myocarditis", "pericarditis"]
    )

    # Pericarditis-specific
    primary_dx = event.get("primary_diagnosis", "").lower()
    is_pericarditis = "pericarditis" in primary_dx

    pericardial_effusion = False
    for field in [echo, mri]:
        if field and "effusion" in str(field).lower() and "no effusion" not in str(field).lower():
            pericardial_effusion = True

    crp_esr = clinical.get("crp_esr", {})
    inflammatory_elevated = crp_esr.get("elevated") is True

    # --- Pending override audit (v4.3) ---
    pending_overrides = {}
    if mri and _is_pending_status(str(mri)):
        pending_overrides["cardiac_mri"] = str(mri)
    if ecg and _is_pending_status(str(ecg)):
        pending_overrides["ecg_findings"] = str(ecg)
    if echo and _is_pending_status(str(echo)):
        pending_overrides["echo_findings"] = str(echo)

    # --- Criteria summary ---
    criteria_met = {
        "histopathology": histopathology,
        "cardiac_mri_positive": mri_positive,
        "troponin_elevated": troponin_elevated,
        "ecg_abnormal": ecg_abnormal,
        "echo_abnormal": echo_abnormal,
        "compatible_symptoms": compatible_symptoms,
        "pericardial_effusion": pericardial_effusion,
        "inflammatory_markers_elevated": inflammatory_elevated,
    }

    # --- Assign Brighton Level ---
    if is_pericarditis:
        level, justification = _pericarditis_level(criteria_met)
    else:
        level, justification = _myocarditis_level(criteria_met)

    early_exit = (level == 4)

    return {
        "vaers_id": vaers_id,
        "condition_type": "pericarditis" if is_pericarditis else "myocarditis",
        "brighton_level": level,
        "brighton_justification": justification,
        "criteria_met": criteria_met,
        "pending_overrides": pending_overrides if pending_overrides else None,
        "confidence": "DETERMINISTIC",
        "early_exit": early_exit,
        "early_exit_reason": "Brighton Level 4 — insufficient diagnostic evidence" if early_exit else None,
    }


def _myocarditis_level(c: dict) -> tuple:
    """
    Level 1: Histopathology OR (MRI+ AND Troponin+ AND Symptoms)
    Level 2: Troponin+ AND (ECG OR Echo OR MRI) AND Symptoms
    Level 3: (Troponin+ OR abnormal imaging) AND Symptoms
    Level 4: Reported but insufficient
    """
    if c["histopathology"]:
        return 1, "Histopathological confirmation (endomyocardial biopsy)"
    if c["cardiac_mri_positive"] and c["troponin_elevated"] and c["compatible_symptoms"]:
        return 1, "Cardiac MRI positive + elevated troponin + compatible symptoms"

    if c["troponin_elevated"] and c["compatible_symptoms"]:
        imaging = [k for k, v in [
            ("abnormal ECG", c["ecg_abnormal"]),
            ("abnormal Echo", c["echo_abnormal"]),
            ("positive MRI", c["cardiac_mri_positive"]),
        ] if v]
        if imaging:
            return 2, f"Elevated troponin + {' + '.join(imaging)} + compatible symptoms"

    if c["compatible_symptoms"]:
        if c["troponin_elevated"]:
            return 3, "Elevated troponin + compatible symptoms"
        findings = [k for k, v in [
            ("abnormal ECG", c["ecg_abnormal"]),
            ("abnormal Echo", c["echo_abnormal"]),
            ("positive MRI", c["cardiac_mri_positive"]),
        ] if v]
        if findings:
            return 3, f"{' + '.join(findings)} + compatible symptoms"

    return 4, "Reported as myocarditis but insufficient documented evidence for Level 1-3"


def _pericarditis_level(c: dict) -> tuple:
    """
    Level 1: ≥2 of (chest pain, ECG changes, pericardial effusion)
    Level 2: ≥1 criterion + elevated inflammatory markers
    Level 3: ≥1 criterion only
    Level 4: Reported but insufficient
    """
    count = sum([c["compatible_symptoms"], c["ecg_abnormal"], c["pericardial_effusion"]])

    if count >= 2:
        return 1, f"{count} pericarditis criteria met (>=2 required for Level 1)"
    if count >= 1 and c["inflammatory_markers_elevated"]:
        return 2, ">=1 pericarditis criterion + elevated inflammatory markers"
    if count >= 1:
        return 3, ">=1 pericarditis criterion present"
    return 4, "Reported as pericarditis but insufficient documented evidence for Level 1-3"
