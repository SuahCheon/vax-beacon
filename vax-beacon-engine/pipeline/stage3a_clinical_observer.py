"""
Vax-Beacon v4 | Stage 3A: Clinical Observer (LLM)
=====================================================
Open-ended clinical observation grouped by category.
NOT a 38-marker checklist — the LLM reports findings in clinical domains
with verbatim context quotes from the narrative.

Input:  Patient narrative (original text)
Output: Category-grouped clinical observations + verbatim context quotes

MedGemma Hybrid:
  - Code pre-extracts keywords from narrative via regex
  - LLM writes brief clinical observation text for each keyword
  - Code builds final JSON structure
  - Fallback: code generates default observations if LLM fails
"""

import re
from llm_client import LLMClient
from prompts.system_prompts import STAGE3A_CLINICAL_OBSERVER_MEDGEMMA


STAGE3A_SYSTEM_PROMPT = """You are a Senior Cardiac Pathologist and Pharmacovigilance Expert.

Your task is to carefully read a VAERS (Vaccine Adverse Event Reporting System) report
and extract ALL clinically relevant findings, organized by clinical domain.

For EACH finding you identify, you MUST provide:
  1. "finding": A concise descriptive name of the finding
  2. "context": The EXACT verbatim quote from the narrative that supports this finding
  3. "confidence": Your confidence that this finding is genuinely present ("high", "moderate", "low")

Report findings in these clinical domains:

[infectious_signs]
Look for: Fever/pyrexia, upper respiratory symptoms (cough, rhinorrhea, sore throat),
gastrointestinal symptoms (diarrhea, vomiting), myalgia/arthralgia as PRODROMAL symptoms
(NOT post-vaccine reactogenicity), viral test results (PCR, serology, culture),
lymphocyte count abnormalities.

[cardiac_dysfunction]
Look for: Heart failure (rapid vs chronic, EF values, recovery trajectory),
AV block or conduction abnormalities, ventricular arrhythmias (VT/VF — NOT sinus
tachycardia or SVT), cardiogenic shock, need for mechanical support (ECMO, IABP),
vasopressor/inotrope use.

[drug_toxin_exposure]
Look for: Immune checkpoint inhibitor (ICI) therapy, concurrent myositis,
conduction delays, recent cardiotoxic chemotherapy (within 6 months),
CK elevation, new medications.

[ischemic_findings]
Look for: Prior coronary artery disease, prior MI, focal/territorial ST changes on ECG
(single coronary territory ONLY — not diffuse), catheterization results,
CAD risk factors (age >50, diabetes, hypertension, smoking).

[autoimmune_findings]
Look for: Known autoimmune disease (SLE, sarcoidosis, RA, etc.), positive ANA/anti-dsDNA,
multi-organ inflammation BEYOND the heart (not just CRP elevation from myocarditis),
granulomas on biopsy.

[covid19_related]
Look for: Active COVID-19 at symptom onset (confirmed by test), recent COVID-19 infection
(within 4 weeks), MIS-C or MIS-A criteria, elevated D-dimer.

[eosinophilic_findings]
Look for: Peripheral eosinophilia (elevated eosinophil count), new medication causing
hypersensitivity, allergic rash or urticaria (systemic, not injection site only),
eosinophils on biopsy.

[narrative_uncertainty]
Look for: Reporter/clinician expressing doubt about the cause, mentions of possible
non-vaccine causes being suspected, explicit statements that testing was NOT performed
(viral testing, biopsy, catheterization not done).

Also extract:
- "demographics": Patient age and sex if stated
- "key_negatives": Findings that are EXPLICITLY negated in the narrative
  (e.g., "no fever", "coronary arteries normal", "viral testing negative")

=== CRITICAL RULES ===
1. Report ONLY what is present in the narrative. Do NOT infer or hallucinate.
2. Every finding MUST have a "context" quote from the narrative. Keep context
   quotes SHORT (max 1-2 sentences, under 150 characters). Paraphrase if needed
   but preserve clinical accuracy. Do NOT include special characters like & in quotes.
3. If a domain has no relevant findings, return an empty array [].
4. For myalgia/arthralgia: Report ONLY if PRODROMAL (preceding cardiac symptoms).
   Post-vaccine arm pain or injection site myalgia is NOT this finding.
5. For ECG/ST changes: Report the specific leads or description verbatim.
   Do NOT interpret territorial distribution — just report what is stated.
6. For viral tests: Report whether positive, negative, or not performed.
   If viral tests (PCR, serology) are mentioned, ALWAYS report the result.
7. For heart failure: Report EF values, recovery status, and treatment response if stated.
   If EF values are stated, ALWAYS report under cardiac_dysfunction.
8. key_negatives: MAX 5 items, NO duplicates. Use noun-phrases only.

=== OUTPUT FORMAT ===
Respond ONLY with valid JSON:
{
  "clinical_observations": {
    "infectious_signs": [
      {"finding": "descriptive finding", "context": "verbatim quote", "confidence": "high/moderate/low"}
    ],
    "cardiac_dysfunction": [...],
    "drug_toxin_exposure": [...],
    "ischemic_findings": [...],
    "autoimmune_findings": [...],
    "covid19_related": [...],
    "eosinophilic_findings": [...],
    "narrative_uncertainty": [...]
  },
  "demographics": {"age": <number or null>, "sex": "<M/F/U or null>"},
  "key_negatives": ["explicitly negated findings"]
}

=== EXAMPLE ===
NARRATIVE: "31M, CRP 112, troponin elevated, WBC 20K. Flu A/B negative, COVID PCR negative. Parvovirus IgM positive. MRI: LVEF 34%, RVEF 37%. No biopsy."
OUTPUT: {"clinical_observations":{"infectious_signs":[{"finding":"Parvovirus IgM positive","context":"Parvovirus IgM positive","confidence":"high"},{"finding":"Leukocytosis","context":"WBC 20K","confidence":"high"}],"cardiac_dysfunction":[{"finding":"LVEF 34%","context":"LVEF 34%, RVEF 37%","confidence":"high"}],"drug_toxin_exposure":[],"ischemic_findings":[],"autoimmune_findings":[],"covid19_related":[],"eosinophilic_findings":[],"narrative_uncertainty":[{"finding":"Biopsy not done","context":"No biopsy","confidence":"high"}]},"demographics":{"age":31,"sex":"M"},"key_negatives":["Flu A/B negative","COVID PCR negative","CMV undetected"]}
=== END EXAMPLE ===
"""


# ============================================================
# Keyword extraction patterns for MedGemma hybrid approach
# ============================================================
_KEYWORD_PATTERNS = {
    "infectious_signs": [
        (r"\bfever\b|pyrexia|febrile|temp(?:erature)?\s*(?:of\s*)?\d{2,3}", "fever_reported"),
        (r"\b(?:cough|rhinorrhea|sore\s*throat|pharyngitis|uri|upper\s*resp)", "uri_symptoms"),
        (r"\b(?:diarrhea|vomiting|nausea|gi\s*symptoms)", "gi_symptoms"),
        (r"\bmyalgia|arthralgia", "myalgia_arthralgia"),
        (r"(?:viral|pcr|serology|culture)\s*(?:positive|negative|test)", "viral_test"),
        (r"\b(?:parvovirus|coxsackie|enterovirus|adenovirus|ebv|cmv|influenza|flu)\b", "specific_virus"),
        (r"\blymphocyt(?:osis|e)", "lymphocytosis"),
        (r"\bwbc|leukocyt|white\s*(?:blood\s*)?cell", "leukocytosis"),
    ],
    "cardiac_dysfunction": [
        (r"\b(?:ef|ejection\s*fraction|lvef|rvef)\s*\d", "ef_value"),
        (r"heart\s*failure|hf\b|chf\b", "heart_failure"),
        (r"\bav\s*block|conduction\s*(?:delay|abnormal)", "av_block"),
        (r"\b(?:vt|vf|v-?tach|v-?fib|ventricular\s*(?:tachycardia|fibrillation))", "ventricular_arrhythmia"),
        (r"cardiogenic\s*shock", "cardiogenic_shock"),
        (r"\becmo|iabp|mechanical\s*support", "mechanical_support"),
        (r"\bvasopressor|inotrope|dobutamine|milrinone", "vasopressor_use"),
    ],
    "drug_toxin_exposure": [
        (r"\b(?:ici|checkpoint\s*inhibitor|nivolumab|pembrolizumab|ipilimumab)", "ici_therapy"),
        (r"\bmyositis|elevated?\s*ck\b|creatine\s*kinase", "myositis_ck"),
        (r"\bchemotherapy|chemo\b", "chemotherapy"),
    ],
    "ischemic_findings": [
        (r"\b(?:cad|coronary\s*artery\s*disease|prior\s*mi|myocardial\s*infarction)", "prior_cad"),
        (r"\bst\s*(?:elevation|depression|changes?|segment)", "st_changes"),
        (r"\bcatheterization|angiography|pci|stent", "catheterization"),
        (r"\bdiabetes|hypertension|smoking", "cad_risk_factor"),
    ],
    "autoimmune_findings": [
        (r"\b(?:sle|lupus|sarcoid|rheumatoid|vasculitis)", "autoimmune_dx"),
        (r"\bana\b|anti-?dsdna|autoantibod", "autoantibodies"),
        (r"\bgranuloma", "granulomas"),
    ],
    "covid19_related": [
        (r"\bcovid.{0,5}(?:positive|confirmed|active|infection|test)", "active_covid"),
        (r"\bmis-?[ca]\b|multisystem\s*inflammatory", "mis_criteria"),
        (r"\bd-?dimer\b", "d_dimer"),
    ],
    "eosinophilic_findings": [
        (r"\beosinophil", "eosinophilia"),
        (r"\b(?:rash|urticaria|hypersensitivity)\b", "hypersensitivity"),
    ],
    "narrative_uncertainty": [
        (r"(?:unsure|uncertain|doubt|question|unclear|possible)\s*(?:cause|etiology|diagnosis)", "reporter_uncertainty"),
        (r"(?:not\s*(?:done|performed|obtained|tested))|(?:no\s*(?:biopsy|testing))", "lack_of_testing"),
    ],
}

# Negation patterns for key_negatives extraction
_NEGATION_PATTERNS = [
    (r"no\s+fever", "No fever"),
    (r"(?:coronary|arteries?)\s*(?:normal|unremarkable)", "Coronary arteries normal"),
    (r"(?:viral|flu|covid)\s*(?:test(?:ing)?|pcr|serology)\s*(?:negative|neg\b)", "Viral testing negative"),
    (r"no\s+(?:prior|previous)\s+(?:cardiac|heart)", "No prior cardiac history"),
    (r"(?:ana|autoimmune)\s*negative", "Autoimmune markers negative"),
    (r"no\s+(?:rash|urticaria|eosinophil)", "No eosinophilic/allergic findings"),
    (r"no\s+(?:biopsy|emb)", "No biopsy performed"),
]


def _extract_keywords_from_text(text: str) -> dict:
    """
    Extract clinical keywords from narrative using regex patterns.
    Returns: {domain: [(keyword_id, matched_text, context_snippet)]}
    """
    text_lower = text.lower()
    results = {}
    for domain, patterns in _KEYWORD_PATTERNS.items():
        domain_matches = []
        for pattern, keyword_id in patterns:
            m = re.search(pattern, text_lower)
            if m:
                # Get context: 50 chars before and after
                start = max(0, m.start() - 50)
                end = min(len(text), m.end() + 50)
                context = text[start:end].strip()
                domain_matches.append((keyword_id, m.group(), context))
        results[domain] = domain_matches
    return results


def _extract_negatives(text: str) -> list:
    """Extract explicit negations from narrative."""
    text_lower = text.lower()
    negatives = []
    for pattern, label in _NEGATION_PATTERNS:
        if re.search(pattern, text_lower):
            negatives.append(label)
    return negatives[:5]


def _extract_demographics_from_text(text: str) -> dict:
    """Extract age and sex from narrative text."""
    age = None
    sex = None
    # Age patterns
    age_m = re.search(r"(?:age|aged?)\s*[:\s]*(\d{1,3})", text, re.IGNORECASE)
    if not age_m:
        age_m = re.search(r"(\d{1,3})\s*(?:year|yr|yo|y/?o)\b", text, re.IGNORECASE)
    if not age_m:
        age_m = re.search(r"\b(\d{1,2})\s*[MmFf]\b", text)
    if age_m:
        age = int(age_m.group(1))
    # Sex patterns
    if re.search(r"\bmale\b|\b\d+\s*M\b", text, re.IGNORECASE):
        sex = "M"
    elif re.search(r"\bfemale\b|\b\d+\s*F\b", text, re.IGNORECASE):
        sex = "F"
    return {"age": age, "sex": sex}


def _keyword_to_finding(keyword_id: str, matched_text: str) -> str:
    """Convert a keyword ID to a human-readable finding name."""
    _MAP = {
        "fever_reported": "Fever/pyrexia reported",
        "uri_symptoms": "Upper respiratory symptoms",
        "gi_symptoms": "Gastrointestinal symptoms",
        "myalgia_arthralgia": "Myalgia/arthralgia",
        "viral_test": "Viral test mentioned",
        "specific_virus": f"Specific virus mentioned ({matched_text})",
        "lymphocytosis": "Lymphocytosis",
        "leukocytosis": "Leukocytosis (WBC abnormality)",
        "ef_value": f"Ejection fraction value ({matched_text})",
        "heart_failure": "Heart failure",
        "av_block": "AV block / conduction abnormality",
        "ventricular_arrhythmia": "Ventricular arrhythmia",
        "cardiogenic_shock": "Cardiogenic shock",
        "mechanical_support": "Mechanical circulatory support",
        "vasopressor_use": "Vasopressor/inotrope use",
        "ici_therapy": "Immune checkpoint inhibitor therapy",
        "myositis_ck": "Myositis or elevated CK",
        "chemotherapy": "Recent chemotherapy",
        "prior_cad": "Prior coronary artery disease",
        "st_changes": "ST changes on ECG",
        "catheterization": "Catheterization/angiography",
        "cad_risk_factor": "CAD risk factor present",
        "autoimmune_dx": "Known autoimmune disease",
        "autoantibodies": "Autoantibodies detected",
        "granulomas": "Granulomas on biopsy",
        "active_covid": "Active COVID-19 infection",
        "mis_criteria": "MIS-C/MIS-A criteria",
        "d_dimer": "D-dimer mentioned",
        "eosinophilia": "Eosinophilia",
        "hypersensitivity": "Hypersensitivity/rash",
        "reporter_uncertainty": "Reporter/clinician uncertainty",
        "lack_of_testing": "Testing not performed",
    }
    return _MAP.get(keyword_id, keyword_id)


def run_stage3a(llm: LLMClient, original_narrative: str) -> dict:
    """
    Stage 3A: Open-ended clinical observation from narrative.

    Args:
        llm: LLM client instance
        original_narrative: Raw VAERS case text

    Returns:
        Dict with clinical_observations (by domain), demographics, key_negatives
    """
    if llm.backend == "medgemma":
        return _run_stage3a_medgemma(llm, original_narrative)

    user_message = (
        "Extract all clinically relevant findings from this VAERS report.\n\n"
        "=== VAERS REPORT ===\n"
        f"{original_narrative}\n"
    )

    # Retry once on JSON parse failure (common with special chars in verbatim quotes)
    try:
        result = llm.query_json(
            system_prompt=STAGE3A_SYSTEM_PROMPT,
            user_message=user_message,
        )
    except (ValueError, Exception):
        result = llm.query_json(
            system_prompt=STAGE3A_SYSTEM_PROMPT,
            user_message=user_message + "\n\nIMPORTANT: Ensure valid JSON output. "
            "Escape special characters in context quotes. Keep context quotes concise.",
        )

    return _normalize_stage3a(result)


def _run_stage3a_medgemma(llm: LLMClient, original_narrative: str) -> dict:
    """
    MedGemma hybrid Stage 3A:
    1. Code pre-extracts keywords via regex
    2. LLM writes brief clinical observations for each keyword
    3. Code builds final JSON structure
    4. Fallback: code generates default observations if LLM fails
    """
    # --- Step 1: Code-based keyword extraction ---
    keywords = _extract_keywords_from_text(original_narrative)
    demographics = _extract_demographics_from_text(original_narrative)
    key_negatives = _extract_negatives(original_narrative)

    # Collect found keywords for LLM
    found_keywords = []
    for domain, matches in keywords.items():
        for kw_id, matched_text, context in matches:
            found_keywords.append(f"{kw_id} (from: \"{context[:80]}\")")

    # --- Step 2: LLM writes observation text (optional enhancement) ---
    llm_observations = {}
    if found_keywords:
        kw_list = ", ".join(kw.split(" (")[0] for kw in found_keywords[:15])
        try:
            llm_text = llm.query_text(
                system_prompt=STAGE3A_CLINICAL_OBSERVER_MEDGEMMA,
                user_message=f"Keywords found: {kw_list}",
            )
            # Parse LLM observations: "keyword: description"
            for line in llm_text.strip().split("\n"):
                line = line.strip()
                if ":" in line:
                    parts = line.split(":", 1)
                    kw = parts[0].strip().lower()
                    desc = parts[1].strip()
                    if desc:
                        llm_observations[kw] = desc
        except Exception:
            pass  # LLM failed — use code fallback entirely

    # --- Step 3: Build final observations structure ---
    observations = {}
    expected_domains = [
        "infectious_signs", "cardiac_dysfunction", "drug_toxin_exposure",
        "ischemic_findings", "autoimmune_findings", "covid19_related",
        "eosinophilic_findings", "narrative_uncertainty",
    ]
    for domain in expected_domains:
        domain_entries = []
        for kw_id, matched_text, context in keywords.get(domain, []):
            finding_name = _keyword_to_finding(kw_id, matched_text)
            # Use LLM observation if available, otherwise use context
            llm_desc = llm_observations.get(kw_id, "")
            domain_entries.append({
                "finding": finding_name,
                "context": context[:150],
                "confidence": "high" if llm_desc else "moderate",
            })
        observations[domain] = domain_entries

    return {
        "clinical_observations": observations,
        "demographics": demographics,
        "key_negatives": key_negatives,
    }


def _normalize_stage3a(result: dict) -> dict:
    """Normalize output structure for Anthropic LLM results."""
    observations = result.get("clinical_observations", {})
    expected_domains = [
        "infectious_signs", "cardiac_dysfunction", "drug_toxin_exposure",
        "ischemic_findings", "autoimmune_findings", "covid19_related",
        "eosinophilic_findings", "narrative_uncertainty",
    ]
    for domain in expected_domains:
        if domain not in observations:
            observations[domain] = []
        normalized = []
        for entry in observations[domain]:
            if isinstance(entry, dict):
                normalized.append({
                    "finding": str(entry.get("finding", "")),
                    "context": str(entry.get("context", "")),
                    "confidence": str(entry.get("confidence", "low")).lower(),
                })
        observations[domain] = normalized

    return {
        "clinical_observations": observations,
        "demographics": result.get("demographics", {"age": None, "sex": None}),
        "key_negatives": result.get("key_negatives", []),
    }
