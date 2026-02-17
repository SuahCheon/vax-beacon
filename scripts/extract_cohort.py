"""
extract_cohort.py
=================
VAERS 원본 CSV(1GB)에서 PoC 대상 100건(심근염 90 + 심낭염 10)을 추출하여
vax-beacon/data/vaers_100_cohort.csv 로 저장합니다.

Usage:
    cd C:\vska_original\data\vaers\vax-beacon
    python scripts/extract_cohort.py
"""

import csv
import json
import os
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent          # vax-beacon/
DATA_DIR     = PROJECT_ROOT / "data"
VAERS_ROOT   = PROJECT_ROOT.parent / "vaers_jan_nov_2021.csv"  # 원본 데이터 폴더

SOURCE_CSV   = VAERS_ROOT / "vaers_jan_nov_2021.csv"           # 1GB 원본
MYO_CSV      = VAERS_ROOT / "Myocarditis_90_Final.csv"
PERI_JSON    = VAERS_ROOT / "pericarditis_isolated_all.json"
OUTPUT_CSV   = DATA_DIR   / "vaers_100_cohort.csv"

# ── 1. Collect Target IDs ─────────────────────────────────────────────────
print("=" * 60)
print("Vax-Beacon Cohort Extractor")
print("=" * 60)

# Myocarditis 90 IDs + group mapping
myo_meta = {}  # {vaers_id: {group, age, sex, onset_days, key_evidence, severity, summary}}
with open(MYO_CSV, encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        vid = row["VAERS_ID"].strip()
        myo_meta[vid] = {
            "condition_type": "myocarditis",
            "group": row["Group"].strip(),
            "curated_age": row["Age"].strip(),
            "curated_sex": row["Sex"].strip(),
            "curated_onset_days": row["Onset_Days"].strip(),
            "curated_key_evidence": row["Key_Evidence"].strip(),
            "curated_severity": row["Severity_Indicator"].strip(),
            "curated_summary": row["Clinical_Summary"].strip(),
        }

# Pericarditis 10 IDs (user-specified)
PERI_CLEAN_IDS      = ["977955", "925542", "966794", "1333796", "1147729", "1128543", "1361389"]
PERI_CONFOUNDED_IDS = ["1314908", "1023768", "1437261"]
PERI_ALL_IDS        = PERI_CLEAN_IDS + PERI_CONFOUNDED_IDS

peri_meta = {}
with open(PERI_JSON, encoding="utf-8") as f:
    peri_data = json.load(f)

for category, group_label in [("clean", "clean"), ("confounded", "confounded")]:
    for item in peri_data[category]:
        if item["id"] in PERI_ALL_IDS:
            peri_meta[item["id"]] = {
                "condition_type": "pericarditis",
                "group": group_label,
                "curated_age": item.get("age", ""),
                "curated_sex": item.get("sex", ""),
                "curated_onset_days": "",  # calculate from dates if available
                "curated_key_evidence": ", ".join(item.get("brighton_evidence", [])),
                "curated_severity": ", ".join(item.get("confounders", [])) if item.get("confounders") else "clean",
                "curated_summary": item.get("symptom", "")[:200],
            }
            # Calculate onset days
            vd, od = item.get("vax_date", ""), item.get("onset_date", "")
            if vd and od:
                try:
                    from datetime import datetime
                    d1 = datetime.strptime(vd, "%m/%d/%Y")
                    d2 = datetime.strptime(od, "%m/%d/%Y")
                    peri_meta[item["id"]]["curated_onset_days"] = str((d2 - d1).days)
                except ValueError:
                    pass

# Combine
all_meta = {**myo_meta, **peri_meta}
target_ids = set(all_meta.keys())

print(f"\n[1/3] Target IDs loaded:")
print(f"  Myocarditis:  {len(myo_meta)} (G1={sum(1 for v in myo_meta.values() if v['group']=='G1')}, "
      f"G2={sum(1 for v in myo_meta.values() if v['group']=='G2')}, "
      f"G3={sum(1 for v in myo_meta.values() if v['group']=='G3')})")
print(f"  Pericarditis: {len(peri_meta)} (clean={len(PERI_CLEAN_IDS)}, confounded={len(PERI_CONFOUNDED_IDS)})")
print(f"  Total:        {len(target_ids)}")

# ── 2. Scan Source CSV & Extract ──────────────────────────────────────────
print(f"\n[2/3] Scanning source CSV: {SOURCE_CSV}")
print(f"  File size: {SOURCE_CSV.stat().st_size / (1024**2):.0f} MB")

found_rows = {}
with open(SOURCE_CSV, encoding="utf-8", errors="replace") as f:
    reader = csv.DictReader(f)
    original_columns = reader.fieldnames
    
    for i, row in enumerate(reader, 1):
        vid = row.get("VAERS_ID", "").strip()
        if vid in target_ids:
            found_rows[vid] = row
            
        if i % 200_000 == 0:
            print(f"  ... scanned {i:,} rows, found {len(found_rows)}/{len(target_ids)}")
        
        # Early exit if all found
        if len(found_rows) == len(target_ids):
            print(f"  All {len(target_ids)} cases found at row {i:,}. Stopping early.")
            break

print(f"\n  Scan complete. Found: {len(found_rows)}/{len(target_ids)}")

# Check for missing IDs
missing = target_ids - set(found_rows.keys())
if missing:
    print(f"  ⚠ MISSING IDs ({len(missing)}): {sorted(missing)}")

# ── 3. Write Output CSV ──────────────────────────────────────────────────
# Append curated metadata columns to the original columns
meta_columns = [
    "condition_type", "group", 
    "curated_age", "curated_sex", "curated_onset_days",
    "curated_key_evidence", "curated_severity", "curated_summary"
]
output_columns = original_columns + meta_columns

os.makedirs(DATA_DIR, exist_ok=True)

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=output_columns)
    writer.writeheader()
    
    for vid in sorted(found_rows.keys(), key=lambda x: int(x)):
        row = found_rows[vid]
        meta = all_meta[vid]
        row.update(meta)
        writer.writerow(row)

print(f"\n[3/3] Output saved: {OUTPUT_CSV}")
print(f"  Rows:    {len(found_rows)}")
print(f"  Columns: {len(output_columns)} (original {len(original_columns)} + curated {len(meta_columns)})")
print(f"\n{'=' * 60}")
print("Done. Ready for agent development.")
print(f"{'=' * 60}")
