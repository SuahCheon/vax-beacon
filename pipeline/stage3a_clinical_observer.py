"""
Vax-Beacon v4 | Stage 3A: Clinical Observer (LLM)
=====================================================
Open-ended clinical observation grouped by category.
NOT a 38-marker checklist — the LLM reports findings in clinical domains
with verbatim context quotes from the narrative.

Input:  Patient narrative (original text)
Output: Category-grouped clinical observations + verbatim context quotes
"""

import json
from llm_client import LLMClient


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
7. For heart failure: Report EF values, recovery status, and treatment response if stated.

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
"""


def run_stage3a(llm: LLMClient, original_narrative: str) -> dict:
    """
    Stage 3A: Open-ended clinical observation from narrative.

    Args:
        llm: LLM client instance
        original_narrative: Raw VAERS case text

    Returns:
        Dict with clinical_observations (by domain), demographics, key_negatives
    """
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

    # Normalize output structure
    observations = result.get("clinical_observations", {})
    expected_domains = [
        "infectious_signs", "cardiac_dysfunction", "drug_toxin_exposure",
        "ischemic_findings", "autoimmune_findings", "covid19_related",
        "eosinophilic_findings", "narrative_uncertainty",
    ]
    for domain in expected_domains:
        if domain not in observations:
            observations[domain] = []
        # Ensure each entry has required fields
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
