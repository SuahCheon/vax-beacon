"""
Test 12 temporal UNKNOWN cases with hybrid Stage 1.
Verifies whether code-based extraction fixes the days_to_onset issue.

Run: python test_temporal_12.py
"""

import json
import time
from data_loader import load_vaers_data, get_case_input
from llm_client import LLMClient
from pipeline.stage1_icsr_extractor import run_stage1

# The 12 cases that were Claude A1 -> MedGemma Unclassifiable (temporal UNKNOWN)
TARGET_IDS = [
    1105807, 1147729, 1286607, 1299305, 1326494, 1350637,
    1354522, 1413266, 1482907, 1482909, 1592056, 1636617,
]

# --- Load data ---
df = load_vaers_data()
print()

# --- Load MedGemma ---
print("Loading MedGemma...")
llm = LLMClient(backend="medgemma")

# --- Run Stage 1 for each case ---
print("=" * 80)
print(f"{'VAERS_ID':<12} {'CSV_NUMDAYS':>12} {'EXTRACTED_DAYS':>15} {'ONSET_DATE':>15} {'STATUS':>10}")
print("-" * 80)

results = []
for vid in TARGET_IDS:
    subset = df[df["VAERS_ID"] == vid]
    if subset.empty:
        print(f"{vid:<12} {'NOT FOUND':>12}")
        continue

    row = subset.iloc[0]
    csv_numdays = row.get("NUMDAYS", "")
    csv_numdays_str = str(csv_numdays) if str(csv_numdays) not in ("nan", "") else "EMPTY"

    case_text = get_case_input(row)

    t0 = time.time()
    try:
        icsr = run_stage1(llm, case_text)
        elapsed = time.time() - t0

        days = icsr.get("event", {}).get("days_to_onset")
        onset = icsr.get("event", {}).get("onset_date")

        status = "OK" if days is not None else "FAIL"
        days_str = str(days) if days is not None else "None"
        onset_str = str(onset) if onset else "None"

        print(f"{vid:<12} {csv_numdays_str:>12} {days_str:>15} {onset_str:>15} {status:>10}  ({elapsed:.0f}s)")

        results.append({
            "vaers_id": vid,
            "csv_numdays": csv_numdays_str,
            "extracted_days": days,
            "extracted_onset": onset,
            "status": status,
            "time_s": round(elapsed, 1),
        })

    except Exception as e:
        elapsed = time.time() - t0
        print(f"{vid:<12} {csv_numdays_str:>12} {'ERROR':>15} {'':>15} {'ERROR':>10}  ({elapsed:.0f}s) {str(e)[:60]}")
        results.append({
            "vaers_id": vid,
            "csv_numdays": csv_numdays_str,
            "extracted_days": None,
            "extracted_onset": None,
            "status": "ERROR",
            "time_s": round(elapsed, 1),
        })

# --- Summary ---
print("=" * 80)
ok = sum(1 for r in results if r["status"] == "OK")
fail = sum(1 for r in results if r["status"] == "FAIL")
err = sum(1 for r in results if r["status"] == "ERROR")
total_time = sum(r["time_s"] for r in results)

print(f"\nSUMMARY: {ok} OK / {fail} FAIL / {err} ERROR  (total: {total_time:.0f}s)")

# Cases where CSV had data but extraction still failed
csv_had_data = [r for r in results if r["csv_numdays"] not in ("EMPTY", "NOT FOUND")]
csv_fixed = [r for r in csv_had_data if r["status"] == "OK"]
print(f"Cases with CSV dates: {len(csv_had_data)} total, {len(csv_fixed)} now extracted")

csv_no_data = [r for r in results if r["csv_numdays"] == "EMPTY"]
lit_fixed = [r for r in csv_no_data if r["status"] == "OK"]
print(f"Cases without CSV dates (literature): {len(csv_no_data)} total, {len(lit_fixed)} extracted from narrative")
