"""
Stage 1 MedGemma Few-Shot Draft — Test Version
================================================
Tests whether adding 2 literature-report examples improves clinical data extraction.
Run: python test_fewshot_stage1.py
"""

import json
import time
import re
from data_loader import load_vaers_data, get_case_input
from llm_client import LLMClient

# --- Draft prompt with 3 few-shot examples ---
STAGE1_FEWSHOT_DRAFT = """Extract clinical data from this medical narrative. Output ONLY JSON.

EXAMPLE 1 (simple):
INPUT: "Chest pain. Troponin 4.2 elevated. Echo EF 55%. ECG ST changes. MRI positive. CRP 52."
OUTPUT: {"clinical_data":{"troponin":{"value":"4.2","elevated":true},"bnp_probnp":{"value":null,"elevated":null},"crp_esr":{"value":"52","elevated":true},"ecg_findings":"ST changes","echo_findings":"EF 55%","cardiac_mri":"positive","catheterization":null,"other_labs":null},"event":{"narrative_summary":"Chest pain with elevated troponin. Echo EF 55%. ECG ST changes. MRI positive."}}

EXAMPLE 2 (literature report with diagnostic results):
INPUT:
Narrative: This literature case describes acute myocarditis in a 44-year-old male after mRNA vaccination. DIAGNOSTIC RESULTS: Troponin T: 847 ng/L (reference range: <=15 ng/L). Electrocardiogram showed ST-segment elevation in the lateral limb and precordial leads. Echocardiogram showed decreased LVEF of 40% with global hypokinesis. Cardiac MRI was compatible with acute myocarditis with mid-myocardial enhancement and associated myocardial oedema. NT-proBNP: 1059 pg/mL. CRP: 63.5 mg/L. COVID-19 PCR negative.
Labs: Troponin T: 847 ng/L; ECG: ST-segment elevation; Echo: LVEF 40%; Cardiac MRI: acute myocarditis with enhancement; CRP: 63.5 mg/L; NT-proBNP: 1059 pg/mL
OUTPUT: {"clinical_data":{"troponin":{"value":"847 ng/L","elevated":true},"bnp_probnp":{"value":"1059 pg/mL","elevated":true},"crp_esr":{"value":"63.5 mg/L","elevated":true},"ecg_findings":"ST-segment elevation in lateral limb and precordial leads","echo_findings":"LVEF 40%, global hypokinesis","cardiac_mri":"acute myocarditis, mid-myocardial enhancement, myocardial oedema","catheterization":null,"other_labs":"COVID-19 PCR negative"},"event":{"narrative_summary":"44M acute myocarditis post-mRNA vaccine. Troponin 847, ST elevation, LVEF 40%, MRI confirmed."}}

EXAMPLE 3 (fulminant case, no troponin, CK-MB is NOT troponin):
INPUT:
Narrative: A 34-year-old female presented with fulminant myocarditis 9 days after first vaccine dose. Echocardiogram showed severely reduced LVEF of 15%. CK-MB elevated at 42.4 ng/mL. ECG showed non-specific changes. Cardiac MRI showed diffuse elevation of native T1 values, pericardial effusion, and patchy mid-wall enhancement consistent with myopericarditis. VA-ECMO initiated for cardiogenic shock.
Labs: LVEF: 15%; CK-MB: 42.4 ng/mL; ECG: Non-specific changes; Cardiac MRI: T1 elevation, pericardial effusion, mid-wall enhancement; CRP: 5.6 mg/dL
OUTPUT: {"clinical_data":{"troponin":{"value":null,"elevated":null},"bnp_probnp":{"value":null,"elevated":null},"crp_esr":{"value":"5.6 mg/dL","elevated":true},"ecg_findings":"non-specific changes","echo_findings":"LVEF 15%, severely reduced","cardiac_mri":"T1 elevation, pericardial effusion, mid-wall enhancement, myopericarditis","catheterization":null,"other_labs":"CK-MB 42.4 ng/mL"},"event":{"narrative_summary":"34F fulminant myocarditis 9d post-vaccine. LVEF 15%, cardiogenic shock, VA-ECMO. MRI confirmed."}}

Now extract:
"""

# --- Test cases: the 7 Brighton L4 extraction gap cases ---
# Focus on 3 most impactful (literature reports where data EXISTS)
TEST_CASES = [1740551, 1661275, 1412506]


def _extract_section(text, header):
    pattern = re.compile(r"\[" + re.escape(header) + r"\]\s*\n(.*?)(?=\n\[|\Z)", re.DOTALL)
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def run_test():
    df = load_vaers_data()
    print()

    print("Loading MedGemma...")
    llm = LLMClient(backend="medgemma")

    print("\n" + "=" * 80)
    print("TESTING FEW-SHOT DRAFT vs ORIGINAL PROMPT")
    print("=" * 80)

    # Import original prompt for comparison
    from prompts.system_prompts import STAGE1_ICSR_EXTRACTOR_MEDGEMMA as ORIGINAL_PROMPT

    for vid in TEST_CASES:
        row = df[df["VAERS_ID"] == vid].iloc[0]
        case_text = get_case_input(row)

        # Build LLM input (same as _run_stage1_medgemma)
        narrative = _extract_section(case_text, "NARRATIVE") or ""
        lab_data = _extract_section(case_text, "LABORATORY DATA")
        coded_symptoms = _extract_section(case_text, "CODED SYMPTOMS (MedDRA)")

        llm_input = f"Narrative: {narrative}"
        if lab_data:
            llm_input += f"\nLabs: {lab_data}"
        if coded_symptoms:
            llm_input += f"\nSymptoms: {coded_symptoms}"

        print(f"\n{'='*80}")
        print(f"VAERS {vid}")
        print(f"{'='*80}")

        # --- Original prompt ---
        print("\n--- ORIGINAL PROMPT ---")
        t0 = time.time()
        try:
            orig_result = llm.query_json(
                system_prompt=ORIGINAL_PROMPT,
                user_message=llm_input,
            )
            elapsed = time.time() - t0
            orig_clin = orig_result.get("clinical_data", {})
            trop = orig_clin.get("troponin", {})
            ecg = orig_clin.get("ecg_findings")
            echo = orig_clin.get("echo_findings")
            mri = orig_clin.get("cardiac_mri")
            print(f"  troponin: {trop} ")
            print(f"  ecg:      {ecg}")
            print(f"  echo:     {echo}")
            print(f"  mri:      {mri}")
            print(f"  ({elapsed:.0f}s)")
        except Exception as e:
            print(f"  ERROR: {str(e)[:100]}")

        # --- Few-shot prompt ---
        print("\n--- FEW-SHOT PROMPT ---")
        t0 = time.time()
        try:
            fs_result = llm.query_json(
                system_prompt=STAGE1_FEWSHOT_DRAFT,
                user_message=llm_input,
            )
            elapsed = time.time() - t0
            fs_clin = fs_result.get("clinical_data", {})
            trop = fs_clin.get("troponin", {})
            ecg = fs_clin.get("ecg_findings")
            echo = fs_clin.get("echo_findings")
            mri = fs_clin.get("cardiac_mri")
            print(f"  troponin: {trop}")
            print(f"  ecg:      {ecg}")
            print(f"  echo:     {echo}")
            print(f"  mri:      {mri}")
            print(f"  ({elapsed:.0f}s)")
        except Exception as e:
            print(f"  ERROR: {str(e)[:100]}")

        # --- Expected values ---
        print("\n--- EXPECTED (for Brighton >= L3) ---")
        if vid == 1740551:
            print("  troponin: elevated=True (847 ng/L)")
            print("  ecg:      ST-segment elevation")
            print("  echo:     LVEF 40%, abnormal")
            print("  mri:      mid-myocardial enhancement, positive")
        elif vid == 1661275:
            print("  troponin: null (CK-MB present, NOT troponin)")
            print("  ecg:      non-specific changes")
            print("  echo:     LVEF 15%, severely reduced")
            print("  mri:      T1 elevation, enhancement, pericardial effusion")
        elif vid == 1412506:
            print("  troponin: elevated=True (0.82)")
            print("  ecg:      ST elevation")
            print("  echo:     any mention")
            print("  mri:      positive")


if __name__ == "__main__":
    run_test()
