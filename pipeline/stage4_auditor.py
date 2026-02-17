"""
Stage 4: Auditor — Known AE + Temporal (Rule-based) — WHO Step 2
================================================================
WHO Step 2: "Is the event a known adverse reaction to the vaccine,
and is the timing consistent?"

Two deterministic checks:
  1. Known AE: Is this AE in the established causal list for this vaccine platform?
  2. Temporal Plausibility: Does the onset fall within the mechanistic window?

NAM 2024 Windows for mRNA COVID-19 → Myocarditis:
  Window A (0-7d):  Strong causal association (peak day 2-4)
  Window B (8-21d): Plausible but attenuated
  Window C (22-42d): Background rate zone (mechanistic threshold exceeded)
  Beyond (>42d):    Causal association unlikely
"""

from config import (
    NAM_CAUSAL_WINDOW_DAYS,
    MECHANISTIC_THRESHOLD_DAYS,
    BACKGROUND_RATE_ZONE_END,
)


# --- Known Vaccine-AE Causal Pairs (Evidence-based Registry) ---
# Format: (vaccine_platform, adverse_event) → evidence_level
KNOWN_CAUSAL_PAIRS = {
    ("mRNA", "myocarditis"): {
        "evidence_level": "ESTABLISHED",
        "source": "NAM 2024 Evidence Review",
        "description": "Causal relationship established between mRNA COVID-19 vaccines and myocarditis",
        "high_risk_group": "Males aged 12-29, especially after dose 2",
        "temporal_window_days": 7,
    },
    ("mRNA", "pericarditis"): {
        "evidence_level": "INSUFFICIENT",
        "source": "NAM 2024 Evidence Review",
        "description": "Insufficient evidence for causal relationship with isolated pericarditis",
        "high_risk_group": None,
        "temporal_window_days": None,
    },
    ("mRNA", "anaphylaxis"): {
        "evidence_level": "ESTABLISHED",
        "source": "WHO/GACVS",
        "description": "Rare but established risk",
        "high_risk_group": "Individuals with PEG allergy",
        "temporal_window_days": 1,
    },
    ("viral_vector", "tts"): {
        "evidence_level": "ESTABLISHED",
        "source": "EMA/PRAC",
        "description": "Thrombosis with Thrombocytopenia Syndrome",
        "high_risk_group": "Women under 60",
        "temporal_window_days": 28,
    },
    ("viral_vector", "gbs"): {
        "evidence_level": "ESTABLISHED",
        "source": "WHO/GACVS",
        "description": "Guillain-Barre Syndrome",
        "high_risk_group": None,
        "temporal_window_days": 42,
    },
}


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


def run_stage4(icsr_data: dict, brighton_data: dict, ddx_data: dict) -> dict:
    """
    WHO Step 2: Known AE verification + Temporal plausibility.
    Pure rule-based: deterministic, auditable.

    Args:
        icsr_data: Structured ICSR from Stage 1
        brighton_data: Brighton assessment from Stage 2
        ddx_data: DDx assessment from Stage 3

    Returns:
        Known AE status, temporal assessment, and WHO Step 2 determination.
    """
    vaers_id = icsr_data.get("vaers_id")
    event = icsr_data.get("event", {})
    vaccine = icsr_data.get("vaccine", {})
    demographics = icsr_data.get("demographics", {})

    # --- 1. Known AE Check ---
    vaccine_platform = _identify_platform(vaccine)
    condition_type = brighton_data.get("condition_type", "myocarditis")
    known_ae_result = _check_known_ae(vaccine_platform, condition_type)

    # --- 2. Temporal Plausibility ---
    days_to_onset = event.get("days_to_onset")
    vax_date = vaccine.get("vaccination_date")
    onset_date = event.get("onset_date")

    # Calculate if missing
    if days_to_onset is None and vax_date and onset_date:
        days_to_onset = _calculate_days(vax_date, onset_date)

    temporal = _assess_temporal(days_to_onset, known_ae_result)
    guidance = _build_investigation_guidance(temporal["temporal_zone"])

    # --- 3. High-risk Group Check ---
    high_risk = _check_high_risk(demographics, vaccine, known_ae_result)

    # --- 4. WHO Step 2 Determination ---
    step2_met = (
        known_ae_result["is_known_ae"]
        and temporal["temporal_zone"] in ("STRONG_CAUSAL", "PLAUSIBLE")
    )

    # --- Flags ---
    flags = []
    if temporal["temporal_zone"] == "BACKGROUND_RATE":
        flags.append("BACKGROUND_RATE_ZONE: 22-42d, mechanistic threshold exceeded")
    if temporal["temporal_zone"] == "UNLIKELY":
        flags.append("BEYOND_42_DAYS: Causal association highly unlikely")
    if temporal["temporal_zone"] == "UNKNOWN":
        flags.append("MISSING_ONSET_DATE: Cannot assess temporal plausibility")
    if days_to_onset is not None and 2 <= days_to_onset <= 4:
        flags.append("PEAK_INCIDENCE_WINDOW: Days 2-4 peak for mRNA myocarditis")
    if high_risk["is_high_risk"]:
        flags.append(f"HIGH_RISK_GROUP: {high_risk['reason']}")
    if not known_ae_result["is_known_ae"]:
        flags.append(f"NOT_KNOWN_AE: {known_ae_result['evidence_level']} evidence for this vaccine-AE pair")
    if event.get("onset_approximate"):
        flags.append("APPROXIMATE_ONSET: Onset date estimated from narrative, verify exact date")

    return {
        "vaers_id": vaers_id,
        "known_ae_assessment": known_ae_result,
        "temporal_assessment": {
            "vaccination_date": vax_date,
            "onset_date": onset_date,
            "days_to_onset": days_to_onset,
            "temporal_zone": temporal["temporal_zone"],
            "nam_2024_alignment": temporal["nam_alignment"],
            # v4.1b: investigation guidance
            "investigation_intensity": guidance["intensity"],
            "investigation_focus": guidance["focus"],
            "investigation_description": guidance["description"],
            "query_requirements": guidance["query_requirements"],
        },
        "high_risk_group": high_risk,
        "who_step2_met": step2_met,
        "who_step2_notes": _build_step2_notes(known_ae_result, temporal, high_risk),
        "flags": flags,
    }


def _identify_platform(vaccine: dict) -> str:
    """Identify vaccine platform from vaccine info."""
    name = str(vaccine.get("name", "")).lower()
    manu = str(vaccine.get("manufacturer", "")).lower()
    combined = name + " " + manu

    if any(t in combined for t in ["pfizer", "biontech", "moderna", "comirnaty", "spikevax"]):
        return "mRNA"
    if any(t in combined for t in ["janssen", "johnson", "astrazeneca", "az", "covishield"]):
        return "viral_vector"
    if "covid" in combined:
        return "mRNA"  # Default assumption for COVID vaccines in VAERS
    return "unknown"


def _check_known_ae(platform: str, condition: str) -> dict:
    """Check if the vaccine-AE pair is in the known causal registry."""
    key = (platform, condition.lower())
    if key in KNOWN_CAUSAL_PAIRS:
        info = KNOWN_CAUSAL_PAIRS[key]
        return {
            "is_known_ae": info["evidence_level"] == "ESTABLISHED",
            "evidence_level": info["evidence_level"],
            "source": info["source"],
            "description": info["description"],
            "expected_temporal_window": info["temporal_window_days"],
        }
    return {
        "is_known_ae": False,
        "evidence_level": "NO_DATA",
        "source": None,
        "description": f"No established evidence for {platform} → {condition}",
        "expected_temporal_window": None,
    }


def _assess_temporal(days_to_onset, known_ae_result: dict) -> dict:
    """Classify temporal zone based on NAM 2024 framework."""
    if days_to_onset is None:
        return {"temporal_zone": "UNKNOWN", "nam_alignment": "INDETERMINATE"}
    if days_to_onset < 0:
        return {"temporal_zone": "PRE_VACCINATION", "nam_alignment": "OUTSIDE_WINDOW"}
    if days_to_onset <= NAM_CAUSAL_WINDOW_DAYS:  # 0-7
        return {"temporal_zone": "STRONG_CAUSAL", "nam_alignment": "WITHIN_WINDOW"}
    if days_to_onset <= MECHANISTIC_THRESHOLD_DAYS - 1:  # 8-21
        return {"temporal_zone": "PLAUSIBLE", "nam_alignment": "WITHIN_WINDOW"}
    if days_to_onset <= BACKGROUND_RATE_ZONE_END:  # 22-42
        return {"temporal_zone": "BACKGROUND_RATE", "nam_alignment": "OUTSIDE_WINDOW"}
    return {"temporal_zone": "UNLIKELY", "nam_alignment": "OUTSIDE_WINDOW"}


def _check_high_risk(demographics: dict, vaccine: dict, known_ae: dict) -> dict:
    """Check if patient falls in known high-risk group."""
    age = demographics.get("age")
    sex = str(demographics.get("sex", "")).upper()
    dose = vaccine.get("dose_number")

    high_risk_info = known_ae.get("description", "")

    # mRNA myocarditis high-risk: males 12-29, especially dose 2
    if known_ae.get("evidence_level") == "ESTABLISHED" and "myocarditis" in high_risk_info.lower():
        if sex == "M" and age is not None and 12 <= age <= 29:
            reason = f"Male, age {age}"
            if dose and dose >= 2:
                reason += f", dose {dose}"
            return {"is_high_risk": True, "reason": reason}

    return {"is_high_risk": False, "reason": None}


def _calculate_days(vax_date: str, onset_date: str):
    """Calculate days between vaccination and onset."""
    try:
        from datetime import datetime
        for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"]:
            try:
                vd = datetime.strptime(str(vax_date), fmt)
                break
            except ValueError:
                vd = None
        for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"]:
            try:
                od = datetime.strptime(str(onset_date), fmt)
                break
            except ValueError:
                od = None
        if vd and od:
            return (od - vd).days
    except Exception:
        pass
    return None


def _build_step2_notes(known_ae, temporal, high_risk) -> str:
    """Build human-readable Step 2 notes."""
    parts = []
    if known_ae["is_known_ae"]:
        parts.append(f"Known AE: {known_ae['description']} ({known_ae['source']}).")
    else:
        parts.append(f"AE evidence: {known_ae['evidence_level']}.")

    days = temporal.get("days_to_onset") if isinstance(temporal, dict) else None
    zone = temporal.get("temporal_zone", "UNKNOWN") if isinstance(temporal, dict) else "UNKNOWN"

    if days is not None:
        parts.append(f"Onset {days}d post-vaccination -> {zone}.")
    else:
        parts.append("Onset date unknown.")

    if high_risk["is_high_risk"]:
        parts.append(f"High-risk group: {high_risk['reason']}.")

    return " ".join(parts)
