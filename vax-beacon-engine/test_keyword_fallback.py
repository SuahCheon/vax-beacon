"""
Unit test: keyword fallback for Brighton L4 cases
Tests whether the existing regex patterns in stage1_icsr_extractor.py
would catch troponin/ecg/echo/mri from the 7 L4 gap cases.

No MedGemma needed — pure regex against actual VAERS text.

Run: python test_keyword_fallback.py
"""

import re
import csv

DATA_PATH = "data/vaers_100_cohort.csv"

# Same regex patterns as _run_stage1_medgemma keyword fallback
def test_keyword_fallback(narrative: str, lab_data: str, coded_symptoms: str):
    all_text = (narrative + " " + (lab_data or "") + " " + (coded_symptoms or "")).lower()
    
    results = {}
    
    # Troponin
    troponin_found = False
    if re.search(r"tr[ao]ponin\s*(increased|elevated|high|positive|abnormal|\d)", all_text):
        troponin_found = True
    elif re.search(r"high\s+tr[ao]ponin", all_text):
        troponin_found = True
    elif re.search(r"elevated\s+tr[ao]ponin", all_text):
        troponin_found = True
    elif re.search(r"troponin\s*[ti]\s*[:=]?\s*\d", all_text):
        troponin_found = True
    elif re.search(r"\btrop\s+\d", all_text):
        troponin_found = True
    elif re.search(r"\bcardiac\s+troponin\b", all_text):
        troponin_found = True
    elif re.search(r"\b(ctni|ctnt|hs-?tni|hs-?tnt|hs-?troponin)\b", all_text):
        troponin_found = True
    results["troponin_elevated"] = troponin_found
    results["troponin_mentioned"] = bool(re.search(r"tr[ao]ponin", all_text))
    
    # ECG
    ecg = None
    if re.search(r"\b(ecg|ekg|electrocardiogram)\b", all_text):
        ecg = "performed"
    if re.search(r"\bst[\s-]*(elevation|segment|depression|change)", all_text):
        ecg = "ST changes"
    results["ecg"] = ecg
    
    # Echo
    echo = None
    if re.search(r"\b(echo|echocardiogram|ecco)\b", all_text):
        echo = "performed"
    if re.search(r"\b(tte|tee)\b", all_text):
        echo = "performed"
    if re.search(r"\b(lvef|ef\s+\d)", all_text):
        echo = "performed"
    results["echo"] = echo
    
    # MRI
    mri = None
    if re.search(r"\b(cardiac\s*mri|cmr|mri)\b", all_text):
        mri = "performed"
    if re.search(r"\b(late\s+gadolinium\s+enhancement|lge)\b", all_text):
        mri = "LGE positive"
    if re.search(r"\bcardiac\s+magnetic\s+resonance\b", all_text):
        mri = "performed"
    if re.search(r"\bmyocardial\s+(edema|oedema)\b", all_text):
        mri = "myocardial edema"
    results["mri"] = mri
    
    # Brighton estimate
    has_symptoms = bool(re.search(r"(chest pain|dyspnea|palpitation|heart failure|shortness of breath|cardiac|myocarditis|pericarditis)", all_text))
    results["compatible_symptoms"] = has_symptoms
    
    # Estimate Brighton level
    if troponin_found and ecg and echo and mri and has_symptoms:
        results["est_brighton"] = "L1 (troponin + imaging + symptoms)"
    elif troponin_found and (ecg or echo or mri) and has_symptoms:
        results["est_brighton"] = "L2 (troponin + 1 imaging + symptoms)"
    elif (troponin_found or ecg or echo or mri) and has_symptoms:
        results["est_brighton"] = "L3 (1 finding + symptoms)"
    else:
        results["est_brighton"] = "L4 (insufficient)"
    
    return results


# Test the 7 L4 gap cases
target_ids = ['1412506', '1437909', '1490549', '1501224', '1511080', '1661275', '1740551']

# Claude's Brighton level for comparison
claude_brighton = {
    '1412506': 'L1', '1437909': 'L3', '1490549': 'L3',
    '1501224': 'L3', '1511080': 'L3', '1661275': 'L3', '1740551': 'L1',
}

print("=" * 90)
print("KEYWORD FALLBACK TEST — 7 Brighton L4 Cases")
print("=" * 90)

with open(DATA_PATH, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["VAERS_ID"] in target_ids:
            vid = row["VAERS_ID"]
            narr = row.get("SYMPTOM_TEXT", "")
            lab = row.get("LAB_DATA", "")
            coded = ", ".join([row.get(f"SYMPTOM{i}", "").strip() 
                              for i in range(1,6) if row.get(f"SYMPTOM{i}", "").strip()])
            
            r = test_keyword_fallback(narr, lab, coded)
            
            fixed = r["est_brighton"] != "L4 (insufficient)"
            cl = claude_brighton.get(vid, "?")
            
            print(f"\nVAERS {vid} | Claude={cl} | MedGemma=L4")
            print(f"  troponin: elevated={r['troponin_elevated']}, mentioned={r['troponin_mentioned']}")
            print(f"  ecg:      {r['ecg']}")
            print(f"  echo:     {r['echo']}")
            print(f"  mri:      {r['mri']}")
            print(f"  symptoms: {r['compatible_symptoms']}")
            print(f"  >> Keyword fallback Brighton: {r['est_brighton']}")
            print(f"  >> {'FIXED' if fixed else 'STILL L4'}")

print("\n" + "=" * 90)
