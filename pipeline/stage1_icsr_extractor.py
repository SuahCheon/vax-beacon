"""
Stage 1: ICSR Extractor
========================
Converts unstructured VAERS narrative into structured JSON.
- Anthropic: Full LLM extraction from formatted case text
- MedGemma: Hybrid approach — code extracts structured fields, LLM extracts from narrative
"""

import re
from llm_client import LLMClient
from prompts.system_prompts import STAGE1_ICSR_EXTRACTOR, STAGE1_ICSR_EXTRACTOR_MEDGEMMA


def run_stage1(llm: LLMClient, case_text: str) -> dict:
    """
    Extract structured ICSR data from a raw VAERS report.

    Args:
        llm: LLM client instance
        case_text: Formatted VAERS case text (from data_loader.get_case_input)

    Returns:
        Structured ICSR dict with demographics, vaccine, event, clinical data, etc.
    """
    if llm.backend == "medgemma":
        return _run_stage1_medgemma(llm, case_text)

    result = llm.query_json(
        system_prompt=STAGE1_ICSR_EXTRACTOR,
        user_message=f"Parse the following VAERS report into structured ICSR format:\n\n{case_text}",
    )
    return result


# ------------------------------------------------------------------
#  MedGemma Hybrid: Code extraction + focused LLM narrative analysis
# ------------------------------------------------------------------

def _extract_field(text: str, label: str) -> str:
    """Extract a labeled field value from case text."""
    pattern = re.compile(re.escape(label) + r":\s*(.+?)(?:\n|$)")
    m = pattern.search(text)
    if m:
        val = m.group(1).strip()
        if val.lower() in ("nan", "unknown", "none", ""):
            return None
        return val
    return None


def _extract_section(text: str, header: str) -> str:
    """Extract content under a [HEADER] section."""
    pattern = re.compile(r"\[" + re.escape(header) + r"\]\s*\n(.*?)(?=\n\[|\Z)", re.DOTALL)
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def _parse_date(date_str: str) -> str:
    """Convert MM/DD/YYYY to YYYY-MM-DD."""
    if not date_str:
        return None
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return date_str


def _safe_float(val: str) -> float:
    """Parse a float from a string, return None if not parseable."""
    if not val:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_bool(val: str) -> bool:
    """Parse Y/N to bool."""
    if not val:
        return None
    v = val.strip().upper()
    if v in ("Y", "YES", "TRUE", "1"):
        return True
    if v in ("N", "NO", "FALSE", "0"):
        return False
    return None


def _extract_onset_days_from_narrative(narrative: str) -> float:
    """Fallback: extract days_to_onset from narrative text when CSV fields are empty.

    Targets literature reports that state onset interval in text, e.g.:
      - "Days from administration to presentation is 3 days"
      - "presented 9 days after her first vaccine dose"
      - "the next day"
      - "same day as vaccination"
    Returns float (days) or None if no pattern matched.
    """
    text = narrative.lower()

    # Pattern 1: "Days from administration to presentation: 3 days" (literature format)
    m = re.search(r"days?\s+from\s+(?:administration|vaccination)\s+to\s+presentation[:\s]+(?:is\s+)?(\d+)", text)
    if m:
        return float(m.group(1))

    # Pattern 2: onset verb + "X days after/post/following" (requires clinical context)
    m = re.search(r"(?:present(?:ed|ing)|develop(?:ed|ing)|experienc(?:ed|ing)|onset|symptoms?\s+(?:started|began|appeared))\s+(\d+)\s*days?\s+(?:after|post|following)", text)
    if m:
        return float(m.group(1))

    # Pattern 3: "X days after/post vaccine dose" (explicit dose reference)
    m = re.search(r"(\d+)\s*days?\s+(?:after|post|following)\s+(?:the\s+)?(?:vaccine|vaccination|second|first|2nd|1st)\s+dose", text)
    if m:
        return float(m.group(1))

    # Pattern 4: "the next day" / "the following day" -> 1 day
    if re.search(r"(?:the\s+)?next\s+day|the\s+following\s+day", text):
        return 1.0

    # Pattern 5: "same day" / "day of vaccination" -> 0 days
    if re.search(r"same\s+day|day\s+of\s+(?:the\s+)?vaccin", text):
        return 0.0

    return None


def _run_stage1_medgemma(llm: LLMClient, case_text: str) -> dict:
    """
    MedGemma hybrid extraction:
    1. Code parses structured VAERS fields (demographics, vaccine, timeline, outcomes)
    2. LLM only analyzes the narrative text for clinical data and summary
    """
    # --- Code extraction of structured fields ---
    vaers_id_m = re.search(r"VAERS REPORT ID:\s*(\d+)", case_text)
    vaers_id = int(vaers_id_m.group(1)) if vaers_id_m else None

    age = _safe_float(_extract_field(case_text, "Age"))
    sex = _extract_field(case_text, "Sex")
    state = _extract_field(case_text, "State")

    vax_name = _extract_field(case_text, "Vaccine")
    manufacturer = _extract_field(case_text, "Manufacturer")
    dose_str = _extract_field(case_text, "Dose")
    dose_number = None
    if dose_str:
        try:
            dose_number = int(float(dose_str))
        except (ValueError, TypeError):
            pass
    lot = _extract_field(case_text, "Lot")
    vax_date_raw = _extract_field(case_text, "Vaccination Date")
    vax_date = _parse_date(vax_date_raw)
    onset_date_raw = _extract_field(case_text, "Onset Date")
    onset_date = _parse_date(onset_date_raw)
    numdays = _safe_float(_extract_field(case_text, "Days to Onset"))

    # --- Narrative fallback: extract days_to_onset when CSV fields are empty ---
    if numdays is None and onset_date is None:
        narrative = _extract_section(case_text, "NARRATIVE") or ""
        numdays = _extract_onset_days_from_narrative(narrative)

    # Outcomes
    died = _parse_bool(_extract_field(case_text, "Died"))
    life_threat = _parse_bool(_extract_field(case_text, "Life-threatening"))
    er_visit = _parse_bool(_extract_field(case_text, "ER Visit"))
    hospitalized = _parse_bool(_extract_field(case_text, "Hospitalized"))
    hospital_days_str = _extract_field(case_text, "Hospital Days")
    hospital_days = None
    if hospital_days_str:
        try:
            hospital_days = int(float(hospital_days_str))
        except (ValueError, TypeError):
            pass
    recovered = _extract_field(case_text, "Recovered")

    # Sections
    narrative = _extract_section(case_text, "NARRATIVE") or ""
    lab_data = _extract_section(case_text, "LABORATORY DATA")
    history = _extract_section(case_text, "MEDICAL HISTORY")
    cur_ill = _extract_section(case_text, "CURRENT ILLNESS AT TIME OF VACCINATION")
    meds = _extract_section(case_text, "MEDICATIONS")
    allergies = _extract_section(case_text, "ALLERGIES")
    coded_symptoms = _extract_section(case_text, "CODED SYMPTOMS (MedDRA)")

    # --- LLM: focused narrative analysis only ---
    llm_input = f"Narrative: {narrative}"
    if lab_data:
        llm_input += f"\nLabs: {lab_data}"
    if coded_symptoms:
        llm_input += f"\nSymptoms: {coded_symptoms}"

    try:
        llm_result = llm.query_json(
            system_prompt=STAGE1_ICSR_EXTRACTOR_MEDGEMMA,
            user_message=llm_input,
        )
    except Exception:
        llm_result = {}
    if not isinstance(llm_result, dict):
        llm_result = {}

    # Extract LLM-analyzed clinical data (with keyword fallback)
    clin = llm_result.get("clinical_data", {})
    if not isinstance(clin, dict):
        clin = {}
    troponin = clin.get("troponin", {})
    if not isinstance(troponin, dict):
        troponin = {}
    bnp = clin.get("bnp_probnp", {})
    if not isinstance(bnp, dict):
        bnp = {}
    crp = clin.get("crp_esr", {})
    if not isinstance(crp, dict):
        crp = {}

    # --- Keyword-based fallback for clinical data ---
    all_text = (narrative + " " + (lab_data or "") + " " + (coded_symptoms or "")).lower()

    # Troponin fallback — try numeric extraction first, then keyword
    if not troponin.get("elevated"):
        # Priority 1: Extract actual numeric value
        trop_num = (
            re.search(r"(?:peak\s+)?tr[ao]ponin\s*[ti]?\s*[:=]?\s*(\d+[\.,]?\d*)\s*(ng/[mld]l|ug/l|pg/ml)?", all_text)
            or re.search(r"(?:ctni|ctnt|hs-?tni|hs-?tnt)\s*[:=]?\s*(\d+[\.,]?\d*)\s*(ng/[mld]l|ug/l|pg/ml)?", all_text)
        )
        if trop_num:
            val_str = trop_num.group(1).replace(",", ".")
            unit = trop_num.group(2) or ""
            troponin = {"value": f"{val_str} {unit}".strip(), "elevated": True}
        # Priority 2: Qualitative keywords
        elif re.search(r"tr[ao]ponin\s*(increased|elevated|high|positive|abnormal)", all_text):
            troponin = {"value": "elevated", "elevated": True}
        elif re.search(r"(high|elevated|increased)\s+tr[ao]ponin", all_text):
            troponin = {"value": "elevated", "elevated": True}
        elif re.search(r"\+\s*tr[ao]ponin", all_text):
            troponin = {"value": "elevated", "elevated": True}
        elif re.search(r"\b(ctni|ctnt|hs-?tni|hs-?tnt|hs-?troponin)\b", all_text):
            troponin = {"value": "elevated", "elevated": True}
        elif re.search(r"\btrop\s+\d", all_text):
            troponin = {"value": "elevated", "elevated": True}
        elif re.search(r"\bcardiac\s+troponin\b", all_text):
            troponin = {"value": "elevated", "elevated": True}
        elif re.search(r"troponin\s*[ti]\s*[:=]?\s*\d", all_text):
            troponin = {"value": "elevated", "elevated": True}
        elif re.search(r"tro+p\s*on\s", all_text):
            troponin = {"value": "mentioned", "elevated": None}
        elif re.search(r"tr[ao]ponin", all_text):
            troponin = troponin if troponin else {"value": "mentioned", "elevated": None}

    # ECG fallback — capture full finding sentence when possible
    if not clin.get("ecg_findings"):
        # Priority 1: ECG + verb + findings sentence
        ecg_detail = re.search(
            r"(?:ecg|ekg|electrocardiogram)\s+(?:show(?:ed|s|ing)?|demonstrat\w+|reveal\w+|findings?[:\s])\s*([^.;]{5,120})",
            all_text,
        )
        if ecg_detail:
            clin["ecg_findings"] = ecg_detail.group(0).strip()[:150]
        # Priority 2: ST-specific findings anywhere
        elif re.search(r"\bst[\s-]*(elevation|segment|depression|change)", all_text):
            st_match = re.search(r"((?:diffuse|lateral|anterior|inferior)?\s*st[\s-]*(?:elevation|segment|depression|change)[^.;]{0,80})", all_text)
            clin["ecg_findings"] = st_match.group(1).strip()[:150] if st_match else "ST changes"
        # Priority 3: Just mentioned
        elif re.search(r"\b(ecg|ekg|electrocardiogram)\b", all_text):
            clin["ecg_findings"] = "performed"
        elif re.search(r"\b12[\s-]*lead\b", all_text):
            clin["ecg_findings"] = "performed"

    # Echo fallback — extract LVEF + abnormalities
    if not clin.get("echo_findings"):
        echo_parts = []
        # Priority 1: LVEF numeric extraction
        ef_match = re.search(r"(?:lvef|ejection\s+fraction|\bef\b)\s*(?:of\s*|was\s*|[:=]\s*)?(\d{1,2})\s*%", all_text)
        if ef_match:
            ef_val = int(ef_match.group(1))
            echo_parts.append(f"LVEF {ef_val}%" + (", reduced" if ef_val < 55 else ", normal"))
        # Priority 2: Specific abnormalities
        if re.search(r"wall\s+motion\s+abnormalit", all_text):
            echo_parts.append("wall motion abnormality")
        if re.search(r"pericardial\s+effusion", all_text):
            echo_parts.append("pericardial effusion")
        if re.search(r"global\s+hypokinesis", all_text):
            echo_parts.append("global hypokinesis")
        if re.search(r"diastolic\s+dysfunction", all_text):
            echo_parts.append("diastolic dysfunction")
        if re.search(r"\b(global\s+longitudinal\s+strain|gls)\b", all_text):
            echo_parts.append("GLS abnormality")
        if echo_parts:
            clin["echo_findings"] = ", ".join(echo_parts)
        # Priority 3: Just mentioned
        elif re.search(r"\b(echo|echocardiogram|ecco)\b", all_text):
            clin["echo_findings"] = "performed"
        elif re.search(r"\b(tte|tee)\b", all_text):
            clin["echo_findings"] = "performed"

    # Cardiac MRI fallback (includes LGE pattern, CMR, myocardial edema)
    # Preserve LGE distribution pattern for Stage 4 mechanistic analysis
    if not clin.get("cardiac_mri"):
        mri_findings = []
        if re.search(r"\b(late\s+gadolinium\s+enhancement|lge)\b", all_text):
            mri_findings.append("LGE positive")
        if re.search(r"\b(focal|punctate|patchy)\b.*?(lge|enhancement|gadolinium)", all_text):
            mri_findings.append("focal LGE")
        elif re.search(r"\b(lge|enhancement|gadolinium).*?(focal|punctate|patchy)\b", all_text):
            mri_findings.append("focal LGE")
        if re.search(r"\b(diffuse|global|widespread)\b.*?(lge|enhancement|gadolinium)", all_text):
            mri_findings.append("diffuse LGE")
        elif re.search(r"\b(lge|enhancement|gadolinium).*?(diffuse|global|widespread)\b", all_text):
            mri_findings.append("diffuse LGE")
        if re.search(r"\bsubendocardial\b.*?(lge|enhancement|gadolinium)", all_text):
            mri_findings.append("subendocardial LGE")
        elif re.search(r"\b(lge|enhancement|gadolinium).*?subendocardial\b", all_text):
            mri_findings.append("subendocardial LGE")
        if re.search(r"\bmid[- ]?(wall|myocardial)\b.*?(lge|enhancement)", all_text):
            mri_findings.append("mid-wall LGE")
        if re.search(r"\bmyocardial\s+(edema|oedema)\b", all_text):
            mri_findings.append("myocardial edema")
        if re.search(r"\bt2\s*(mapping|elevation|signal|weighted)\b", all_text):
            mri_findings.append("T2 abnormality")
        if re.search(r"\b(lake\s+louise|ll\s+criteria)\b", all_text):
            mri_findings.append("Lake Louise criteria")
        if mri_findings:
            clin["cardiac_mri"] = ", ".join(mri_findings)
        elif re.search(r"\b(cardiac\s*mri|cmr)\b", all_text):
            clin["cardiac_mri"] = "performed"
        elif re.search(r"\bcardiac\s+magnetic\s+resonance\b", all_text):
            clin["cardiac_mri"] = "performed"
        elif re.search(r"\bmri\b", all_text):
            clin["cardiac_mri"] = "performed"

    # CRP/ESR fallback — try numeric extraction first
    if not crp.get("elevated"):
        crp_num = re.search(r"(?:crp|c-reactive\s+protein)\s*[:=]?\s*(\d+[\.,]?\d*)\s*(mg/[ld]l|mg/l)?", all_text)
        esr_num = re.search(r"(?:esr|sed(?:imentation)?\s+rate)\s*[:=]?\s*(\d+[\.,]?\d*)\s*(mm/hr?)?", all_text)
        if crp_num:
            val_str = crp_num.group(1).replace(",", ".")
            unit = crp_num.group(2) or ""
            crp = {"value": f"CRP {val_str} {unit}".strip(), "elevated": True}
        elif esr_num:
            val_str = esr_num.group(1).replace(",", ".")
            unit = esr_num.group(2) or ""
            crp = {"value": f"ESR {val_str} {unit}".strip(), "elevated": True}
        elif re.search(r"\b(crp|esr|c-reactive)\s*(elevated|high|increased)", all_text):
            crp = {"value": "elevated", "elevated": True}
        elif re.search(r"\bsed(imentation)?\s+rate\s*(elevated|high|increased)", all_text):
            crp = {"value": "elevated", "elevated": True}

    # BNP fallback — try numeric extraction first
    if not bnp.get("elevated"):
        bnp_num = re.search(r"(?:nt-?pro-?bnp|pro-?bnp|bnp)\s*[:=]?\s*(\d+[\.,]?\d*)\s*(pg/ml|ng/l)?", all_text)
        if bnp_num:
            val_str = bnp_num.group(1).replace(",", ".")
            unit = bnp_num.group(2) or ""
            bnp = {"value": f"{val_str} {unit}".strip(), "elevated": True}
        elif re.search(r"\b(bnp|pro-?bnp|nt-?probnp)\s*(elevated|high|increased)", all_text):
            bnp = {"value": "elevated", "elevated": True}

    # Determine primary diagnosis from coded symptoms and narrative
    primary_dx = "myocarditis"
    combined_text = (narrative + " " + (coded_symptoms or "")).lower()
    if "pericarditis" in combined_text and "myocarditis" not in combined_text:
        primary_dx = "pericarditis"

    # Extract symptoms from coded symptoms field
    symptoms = []
    if coded_symptoms:
        symptoms = [s.strip() for s in coded_symptoms.split(",") if s.strip()]

    # Narrative summary from LLM or fallback
    event = llm_result.get("event", {})
    if not isinstance(event, dict):
        event = {}
    summary = event.get("narrative_summary", "")
    if not summary:
        age_str = f"{int(age)}" if age else "?"
        sex_str = sex or "?"
        summary = f"{age_str}{sex_str} {primary_dx}. "
        if numdays is not None:
            summary += f"Onset {int(numdays)}d post-vaccination."

    # Compute richness score
    richness = 1
    if narrative and len(narrative) > 50:
        richness += 2
    if lab_data:
        richness += 2
    if troponin.get("elevated") is not None:
        richness += 1
    if history:
        richness += 1
    if onset_date:
        richness += 1
    richness = min(richness, 10)

    # Missing critical fields
    missing = []
    if not onset_date and numdays is None:
        missing.append("onset_date")
    if not lab_data:
        missing.append("lab_data")

    # --- Build final ICSR ---
    return {
        "vaers_id": vaers_id,
        "demographics": {
            "age": age,
            "sex": sex,
            "state": state,
        },
        "vaccine": {
            "name": vax_name,
            "manufacturer": manufacturer,
            "dose_number": dose_number,
            "vaccination_date": vax_date,
            "lot_number": lot,
        },
        "event": {
            "onset_date": onset_date,
            "days_to_onset": numdays,
            "onset_approximate": False if onset_date or numdays is not None else None,
            "primary_diagnosis": primary_dx,
            "symptoms": symptoms,
            "narrative_summary": summary,
        },
        "clinical_data": {
            "troponin": troponin if troponin else {"value": None, "elevated": None},
            "bnp_probnp": bnp if bnp else {"value": None, "elevated": None},
            "crp_esr": crp if crp else {"value": None, "elevated": None},
            "ecg_findings": clin.get("ecg_findings"),
            "echo_findings": clin.get("echo_findings"),
            "cardiac_mri": clin.get("cardiac_mri"),
            "catheterization": clin.get("catheterization"),
            "other_labs": clin.get("other_labs"),
        },
        "medical_history": {
            "prior_conditions": [h.strip() for h in history.split(",")] if history else [],
            "current_illness": cur_ill,
            "medications": [m.strip() for m in meds.split(",")] if meds else [],
            "allergies": [a.strip() for a in allergies.split(",")] if allergies and allergies.lower() not in ("no", "none", "nka", "nkda") else [],
        },
        "outcomes": {
            "hospitalized": hospitalized,
            "hospital_days": hospital_days,
            "er_visit": er_visit,
            "life_threatening": life_threat,
            "died": died if died is not None else False,
            "recovered": recovered,
        },
        "data_quality": {
            "narrative_length": len(narrative),
            "missing_critical_fields": missing,
            "richness_score": richness,
        },
    }
