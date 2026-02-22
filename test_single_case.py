"""
Quick single-case test: VAERS 1105807
Tests whether hybrid Stage 1 (code extraction) correctly captures days_to_onset.
Run: python test_single_case.py
"""

import json
from data_loader import load_vaers_data, get_case_input
from llm_client import LLMClient
from pipeline.stage1_icsr_extractor import run_stage1

# --- Load data ---
df = load_vaers_data()
row = df[df["VAERS_ID"] == 1105807].iloc[0]

# --- Show what's in the CSV ---
print("=" * 60)
print("RAW CSV VALUES:")
print(f"  NUMDAYS:    {row['NUMDAYS']}")
print(f"  ONSET_DATE: {row['ONSET_DATE']}")
print(f"  VAX_DATE:   {row['VAX_DATE']}")
print("=" * 60)

# --- Show formatted case_text (what Stage 1 receives) ---
case_text = get_case_input(row)
print("\nFORMATTED CASE TEXT (first 500 chars):")
print(case_text[:500])
print("..." if len(case_text) > 500 else "")
print("=" * 60)

# --- Run Stage 1 with MedGemma ---
print("\nLoading MedGemma...")
llm = LLMClient(backend="medgemma")

print("\nRunning Stage 1...")
icsr = run_stage1(llm, case_text)

# --- Check result ---
print("\n" + "=" * 60)
print("STAGE 1 OUTPUT (event section):")
print(json.dumps(icsr.get("event", {}), indent=2))
print("=" * 60)

days = icsr.get("event", {}).get("days_to_onset")
onset = icsr.get("event", {}).get("onset_date")
print(f"\n[OK] days_to_onset: {days}")
print(f"[OK] onset_date:    {onset}")

if days is not None:
    print("\nSUCCESS - Code-based extraction captured days_to_onset!")
else:
    print("\nFAILURE - days_to_onset is still None. Check _extract_field logic.")
