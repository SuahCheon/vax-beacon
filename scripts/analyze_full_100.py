"""
Vax-Beacon v3 — Full 100-Case Analysis Report
=================================================
Analyses:
  1. Overall Summary (WHO × Group, Brighton, Early Exit, Errors)
  2. Plausibility Gate Audit (noise_filtered_count > 0)
  3. Edge Cases (ischemic young, DEFINITE_OTHER, GT mismatch, nuance flip)
  4. mechanism_check Quality (legacy boolean, suspicious plausibility)
  5. Result File Paths
"""
import sys
import json
import csv
from collections import Counter, defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --- Load data ---
JSON_PATH = "results/results_full_100_20260215_135820.json"
CSV_PATH = "results/summary_full_100_20260215_135820.csv"

with open(JSON_PATH, "r", encoding="utf-8") as f:
    results = json.load(f)

with open(CSV_PATH, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    csv_rows = list(reader)

# Index by vaers_id
results_by_id = {r["vaers_id"]: r for r in results}


def hr(title, char="=", width=78):
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


# ============================================================
# ANALYSIS 1: Overall Summary
# ============================================================
hr("ANALYSIS 1: OVERALL SUMMARY")

# 1a. WHO Category × Group Crosstab
print("\n[1a] WHO Category × Group Crosstab")
groups = sorted(set(r["group"] for r in csv_rows))
who_cats = ["A1", "B1", "B2", "C", "Unclassifiable"]

# Build crosstab
crosstab = defaultdict(lambda: defaultdict(int))
for row in csv_rows:
    crosstab[row["who_category"]][row["group"]] += 1

# Header
header = f"{'WHO':>16s}"
for g in groups:
    header += f" | {g:>11s}"
header += f" | {'TOTAL':>6s}"
print(header)
print("-" * len(header))

for cat in who_cats:
    line = f"{cat:>16s}"
    total = 0
    for g in groups:
        count = crosstab[cat][g]
        total += count
        line += f" | {count:>11d}"
    line += f" | {total:>6d}"
    print(line)

# Total row
line = f"{'TOTAL':>16s}"
for g in groups:
    count = sum(crosstab[cat][g] for cat in who_cats)
    line += f" | {count:>11d}"
line += f" | {len(csv_rows):>6d}"
print("-" * len(line))
print(line)

# 1b. Brighton Level Distribution
print("\n[1b] Brighton Level Distribution")
brighton_counts = Counter(int(r["brighton_level"]) for r in csv_rows)
for level in sorted(brighton_counts):
    count = brighton_counts[level]
    bar = "█" * count
    print(f"  Level {level}: {count:3d} ({count:5.1f}%) {bar}")

# 1c. Early Exit
early_exits = [r for r in csv_rows if r["early_exit"] == "True"]
print(f"\n[1c] Early Exit (Brighton L4): {len(early_exits)} cases")
for r in early_exits:
    print(f"  VAERS {r['vaers_id']:>8s} | Group={r['group']:>12s} | GT={r['gt_severity']}")

# 1d. Error Count
error_count = sum(1 for r in csv_rows if int(r["errors"]) > 0)
print(f"\n[1d] Pipeline Errors: {error_count}")

# 1e. Confidence Distribution
print("\n[1e] Confidence Distribution")
conf_counts = Counter(r["confidence"] for r in csv_rows)
for c in ["HIGH", "MEDIUM", "LOW", ""]:
    if c in conf_counts:
        label = c if c else "(empty)"
        print(f"  {label:>10s}: {conf_counts[c]}")

# 1f. WHO Step 1 Conclusion Distribution (non-early-exit only)
print("\n[1f] WHO Step 1 Conclusion Distribution (non-early-exit)")
step1_counts = Counter(r["who_step1_conclusion"] for r in csv_rows if r["early_exit"] == "False")
for k, v in step1_counts.most_common():
    print(f"  {k:>30s}: {v}")


# ============================================================
# ANALYSIS 2: Plausibility Gate Audit
# ============================================================
hr("ANALYSIS 2: PLAUSIBILITY GATE AUDIT")

filtered_cases = []
for r in results:
    if r.get("early_exit"):
        continue
    s3 = r.get("stages", {}).get("stage3_ddx", {})
    nfc = s3.get("noise_filtered_count", 0)
    if nfc > 0:
        filtered_cases.append(r)

print(f"\nCases with noise_filtered_count > 0: {len(filtered_cases)} / {len(results)}")
print(f"{'='*78}")

for case in filtered_cases:
    vid = case["vaers_id"]
    s3 = case["stages"]["stage3_ddx"]
    nfc = s3["noise_filtered_count"]
    conclusion = s3["who_step1_conclusion"]
    max_nci = s3["max_nci_score"]
    adjusted = s3.get("max_nci_adjusted", max_nci)
    group = case.get("group", "?")

    print(f"\n  VAERS {vid} | Group={group} | NCI={max_nci} -> adj={adjusted} | Step1={conclusion} | filtered={nfc}")

    # Show filtered markers
    nci_detail = s3.get("nci_detailed", {})
    for cat_name, cat_data in nci_detail.items():
        for fm in cat_data.get("markers_filtered", []):
            marker_name = fm["marker"]
            weight_blocked = fm["weight_blocked"]
            gate_info = fm["gate"]

            # Get rationale from llm_markers_extracted
            llm_markers = s3.get("llm_markers_extracted", {})
            marker_data = llm_markers.get(marker_name, {})
            rationale = marker_data.get("biological_rationale", "N/A")[:150]

            print(f"    [{cat_name}] {marker_name:30s} weight_blocked={weight_blocked:.2f}")
            print(f"      gate: {gate_info}")
            print(f"      rationale: {rationale}...")

# Clinical assessment summary
print(f"\n{'='*78}")
print(f"  PLAUSIBILITY GATE SUMMARY")
print(f"{'='*78}")

total_filtered_markers = 0
filter_by_category = Counter()
filter_by_reason = Counter()
for case in filtered_cases:
    s3 = case["stages"]["stage3_ddx"]
    for cat_name, cat_data in s3.get("nci_detailed", {}).items():
        for fm in cat_data.get("markers_filtered", []):
            total_filtered_markers += 1
            filter_by_category[cat_name] += 1
            gate = fm.get("gate", "")
            if "acute=False" in gate:
                filter_by_reason["not_acute_concordant"] += 1
            elif "plausibility=low" in gate or "plausibility=none" in gate:
                filter_by_reason["low_plausibility"] += 1
            else:
                filter_by_reason["other"] += 1

print(f"  Total markers filtered across all cases: {total_filtered_markers}")
print(f"\n  By Category:")
for cat, count in filter_by_category.most_common():
    print(f"    {cat:35s}: {count}")
print(f"\n  By Filter Reason:")
for reason, count in filter_by_reason.most_common():
    print(f"    {reason:35s}: {count}")


# ============================================================
# ANALYSIS 3: Edge Cases
# ============================================================
hr("ANALYSIS 3: EDGE CASES")

# 3a. Ischemic NCI > 0.3 with age < 40
print("\n[3a] Ischemic Heart Disease NCI > 0.3 with age < 40")
ischemic_young = []
for r in results:
    if r.get("early_exit"):
        continue
    s3 = r["stages"]["stage3_ddx"]
    nci_detail = s3.get("nci_detailed", {})
    ischemic = nci_detail.get("ischemic_heart_disease", {})
    ischemic_nci = ischemic.get("nci_score", 0)
    if ischemic_nci > 0.3:
        age = r["stages"].get("stage1_icsr", {}).get("demographics", {}).get("age")
        if age is not None and age < 40:
            ischemic_young.append({
                "vaers_id": r["vaers_id"],
                "age": age,
                "ischemic_nci": ischemic_nci,
                "group": r.get("group"),
                "who_category": r["stages"]["stage5_causality"]["who_category"],
                "markers_passed": ischemic.get("markers_passed", []),
            })

if ischemic_young:
    for case in ischemic_young:
        print(f"  VAERS {case['vaers_id']} | age={case['age']} | ischemic_NCI={case['ischemic_nci']} | WHO={case['who_category']} | Group={case['group']}")
        for m in case["markers_passed"]:
            print(f"    + {m['marker']:30s} weight={m['weight']:.2f} gate={m['gate']}")
else:
    print("  None found (good — no false ischemic signal in young patients)")

# 3b. max_nci_adjusted >= 0.7 (DEFINITE_OTHER_CAUSE) full list
print("\n[3b] DEFINITE_OTHER_CAUSE Cases (max_nci_adjusted >= 0.7)")
definite_cases = []
for r in csv_rows:
    if r["early_exit"] == "True":
        continue
    try:
        max_nci = float(r["max_nci"])
    except (ValueError, TypeError):
        continue
    if r["who_step1_conclusion"] == "DEFINITE_OTHER_CAUSE":
        definite_cases.append(r)

print(f"  Total: {len(definite_cases)}")
print(f"  {'VAERS_ID':>10s} | {'Group':>12s} | {'NCI':>5s} | {'Dominant':>40s} | {'WHO':>5s} | {'GT_severity'}")
print(f"  {'-'*110}")
for r in definite_cases:
    print(f"  {r['vaers_id']:>10s} | {r['group']:>12s} | {r['max_nci']:>5s} | {r['dominant_alternative']:>40s} | {r['who_category']:>5s} | {r['gt_severity']}")

# 3c. Ground Truth vs WHO Category Mismatches
print("\n[3c] Ground Truth vs WHO Category Mismatches")
print("  Logic: G1(clean/classic) expected → A1/B1; G2(confounded) → B2/C; G3(severe) → B2/C; confounded → C")

mismatches = []
for r in csv_rows:
    gt_group = r["gt_group"]
    who = r["who_category"]
    vid = r["vaers_id"]
    concern = None

    if gt_group == "G1" and who in ("C",):
        concern = f"G1 (classic) classified as C (coincidental)"
    elif gt_group == "G1" and who in ("Unclassifiable",):
        concern = f"G1 (classic) classified as Unclassifiable (data quality)"
    elif gt_group == "clean" and who in ("C",):
        concern = f"clean pericarditis classified as C (coincidental)"
    elif gt_group == "confounded" and who in ("A1", "B1"):
        concern = f"confounded case classified as {who} (expected C/B2)"

    if concern:
        mismatches.append({
            "vaers_id": vid,
            "gt_group": gt_group,
            "gt_severity": r["gt_severity"],
            "who_category": who,
            "max_nci": r["max_nci"],
            "dominant": r["dominant_alternative"],
            "concern": concern,
        })

if mismatches:
    for m in mismatches:
        print(f"  VAERS {m['vaers_id']:>8s} | GT={m['gt_group']:>12s} ({m['gt_severity'][:30]}) | WHO={m['who_category']} | NCI={m['max_nci']} | {m['concern']}")
else:
    print("  No critical mismatches found")

def _nci_category(nci):
    if nci >= 0.7:
        return "DEFINITE"
    elif nci >= 0.4:
        return "POSSIBLE"
    elif nci >= 0.2:
        return "WEAK"
    else:
        return "NO_ALT"

# 3d. Narrative nuance modifier that flipped the conclusion
print("\n[3d] Narrative Nuance Modifier Flips (nuance pushed NCI across threshold)")
nuance_flips = []
for r in results:
    if r.get("early_exit"):
        continue
    s3 = r["stages"]["stage3_ddx"]
    max_nci = s3.get("max_nci_score", 0)
    adjusted = s3.get("max_nci_adjusted", max_nci)
    nuance = s3.get("narrative_nuance_modifier", 0)

    if nuance > 0 and max_nci != adjusted:
        old_cat = _nci_category(max_nci)
        new_cat = _nci_category(adjusted)
        if old_cat != new_cat:
            nuance_flips.append({
                "vaers_id": r["vaers_id"],
                "max_nci": max_nci,
                "adjusted": adjusted,
                "nuance": nuance,
                "old_cat": old_cat,
                "new_cat": new_cat,
                "group": r.get("group"),
            })

if nuance_flips:
    for nf in nuance_flips:
        print(f"  VAERS {nf['vaers_id']} | Group={nf['group']} | NCI {nf['max_nci']} -> {nf['adjusted']} (nuance={nf['nuance']}) | {nf['old_cat']} -> {nf['new_cat']}")
else:
    print("  No nuance-induced threshold flips found")


# ============================================================
# ANALYSIS 4: mechanism_check Quality
# ============================================================
hr("ANALYSIS 4: MARKER EXTRACTION QUALITY")

# 4a. Legacy boolean or empty string markers
print("\n[4a] Legacy Boolean or Empty Biological Rationale")
legacy_cases = []
for r in results:
    if r.get("early_exit"):
        continue
    s3 = r["stages"]["stage3_ddx"]
    markers = s3.get("llm_markers_extracted", {})
    issues = []
    for marker_name, marker_data in markers.items():
        if isinstance(marker_data, bool):
            issues.append(f"{marker_name}: raw boolean (not 3-dimensional)")
        elif isinstance(marker_data, dict):
            rationale = marker_data.get("biological_rationale", "")
            if marker_data.get("present") and (
                rationale in ("", "Legacy boolean conversion", "Not found in LLM output")
                or len(rationale) < 10
            ):
                issues.append(f"{marker_name}: present=True but rationale='{rationale[:50]}'")
            plaus = marker_data.get("plausibility", "")
            if marker_data.get("present") and plaus not in ("high", "moderate", "low", "none"):
                issues.append(f"{marker_name}: invalid plausibility='{plaus}'")

    if issues:
        legacy_cases.append({"vaers_id": r["vaers_id"], "group": r.get("group"), "issues": issues})

if legacy_cases:
    print(f"  Found {len(legacy_cases)} cases with quality issues:")
    for lc in legacy_cases:
        print(f"\n  VAERS {lc['vaers_id']} | Group={lc['group']}")
        for issue in lc["issues"]:
            print(f"    - {issue}")
else:
    print("  All markers have proper 3-dimensional output with valid rationale (PASS)")

# 4b. Suspicious plausibility judgments (chronic conditions marked as moderate+)
print("\n[4b] Suspicious Plausibility Judgments")
print("  Checking: present=True, is_acute_concordant=True, plausibility=moderate/high")
print("  for markers that are typically CHRONIC findings")

CHRONIC_SUSPECT_MARKERS = {
    "age_over_50": "Risk factor, not cause",
    "diabetes_hypertension": "Chronic risk factor",
    "smoking_history": "Chronic exposure",
    "prior_cad_history": "Chronic disease",
}

suspicious = []
for r in results:
    if r.get("early_exit"):
        continue
    s3 = r["stages"]["stage3_ddx"]
    markers = s3.get("llm_markers_extracted", {})
    for marker_name, expected_note in CHRONIC_SUSPECT_MARKERS.items():
        md = markers.get(marker_name, {})
        if (md.get("present") and
            md.get("is_acute_concordant") and
            md.get("plausibility") in ("high", "moderate")):
            suspicious.append({
                "vaers_id": r["vaers_id"],
                "marker": marker_name,
                "plausibility": md["plausibility"],
                "rationale": md.get("biological_rationale", "")[:120],
                "expected": expected_note,
            })

if suspicious:
    print(f"  Found {len(suspicious)} suspicious judgments:")
    for s in suspicious:
        print(f"  VAERS {s['vaers_id']} | {s['marker']:25s} | plaus={s['plausibility']:8s} | expected: {s['expected']}")
        print(f"    rationale: {s['rationale']}...")
else:
    print("  No suspicious plausibility overrides found (PASS)")

# 4c. Overall marker statistics
print("\n[4c] Overall Marker Statistics (non-early-exit cases)")
total_present = Counter()
total_markers = 0
non_exit_cases = [r for r in results if not r.get("early_exit")]
for r in non_exit_cases:
    s3 = r["stages"]["stage3_ddx"]
    markers = s3.get("llm_markers_extracted", {})
    for marker_name, md in markers.items():
        total_markers += 1
        if isinstance(md, dict) and md.get("present"):
            total_present[marker_name] += 1

print(f"  Non-early-exit cases: {len(non_exit_cases)}")
print(f"  Total markers evaluated: {total_markers}")
print(f"\n  Top 15 most frequently present markers:")
for marker, count in total_present.most_common(15):
    pct = count / len(non_exit_cases) * 100
    print(f"    {marker:35s}: {count:3d} ({pct:5.1f}%)")

print(f"\n  Markers NEVER present:")
all_marker_names = set()
for r in non_exit_cases:
    s3 = r["stages"]["stage3_ddx"]
    all_marker_names.update(s3.get("llm_markers_extracted", {}).keys())
never_present = all_marker_names - set(total_present.keys())
for m in sorted(never_present):
    print(f"    {m}")


# ============================================================
# ANALYSIS 5: Result File Paths
# ============================================================
hr("ANALYSIS 5: RESULT FILE PATHS")
print(f"\n  JSON Results: {JSON_PATH}")
print(f"  Summary CSV:  {CSV_PATH}")
print(f"  Total cases:  {len(results)}")
print(f"  File sizes:")

import os
json_size = os.path.getsize(JSON_PATH)
csv_size = os.path.getsize(CSV_PATH)
print(f"    JSON: {json_size:,.0f} bytes ({json_size/1024/1024:.1f} MB)")
print(f"    CSV:  {csv_size:,.0f} bytes ({csv_size/1024:.1f} KB)")


# ============================================================
# FINAL SUMMARY
# ============================================================
hr("FINAL PIPELINE QUALITY SUMMARY", "=")
print(f"""
  Total Cases:           100
  Errors:                {error_count}
  Early Exit (L4):       {len(early_exits)}
  Full Pipeline:         {100 - len(early_exits)}

  WHO Distribution:
    A1 (Vaccine-related): {sum(1 for r in csv_rows if r['who_category']=='A1')}
    B1 (Potential signal): {sum(1 for r in csv_rows if r['who_category']=='B1')}
    B2 (Conflicting):     {sum(1 for r in csv_rows if r['who_category']=='B2')}
    C  (Coincidental):    {sum(1 for r in csv_rows if r['who_category']=='C')}
    Unclassifiable:       {sum(1 for r in csv_rows if r['who_category']=='Unclassifiable')}

  Plausibility Gate:     {len(filtered_cases)} cases filtered ({total_filtered_markers} markers)
  Legacy Booleans:       {len(legacy_cases)} cases with quality issues
  Suspicious Plausibility: {len(suspicious)} markers flagged
  GT Mismatches:         {len(mismatches)} cases
  Nuance Flips:          {len(nuance_flips)} threshold crossings
""")
