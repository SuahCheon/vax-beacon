"""Analyze G2 case (983362) Stage 3 DDx output in detail."""
import sys
import json

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

with open("results/results_sample_1_20260215_122024.json", "r", encoding="utf-8") as f:
    results = json.load(f)

# Find G2 case
g2 = next(r for r in results if r["vaers_id"] == 983362)
s3 = g2["stages"]["stage3_ddx"]

print("=" * 70)
print("  G2 Case 983362 — Stage 3 DDx Hybrid Analysis")
print("=" * 70)

# 1. LLM Markers (38 Boolean)
markers = s3["llm_markers_extracted"]
print(f"\n[1] LLM MARKERS EXTRACTED: {len(markers)} total")
present_markers = {k: v for k, v in markers.items() if v.get("present")}
absent_markers = {k: v for k, v in markers.items() if not v.get("present")}
print(f"    Present (True): {len(present_markers)}")
print(f"    Absent (False): {len(absent_markers)}")
print(f"\n    --- Present Markers ---")
for name, data in present_markers.items():
    acute = data.get("is_acute_concordant", "?")
    plaus = data.get("plausibility", "?")
    rationale = data.get("biological_rationale", "")[:120]
    print(f"    {name:30s} | acute={str(acute):5s} | plaus={plaus:10s} | {rationale}...")

# 2. NCI Detailed (per category)
print(f"\n[2] NCI DETAILED (Category Scores)")
nci_detail = s3["nci_detailed"]
for cat, data in nci_detail.items():
    score = data["nci_score"]
    passed = data["pass_count"]
    filtered = data["filter_count"]
    absent_ct = len(data["markers_absent"])
    indicator = " ***" if score > 0 else ""
    print(f"    {cat:30s} | NCI={score:.2f} | passed={passed} | filtered={filtered} | absent={absent_ct}{indicator}")
    if data.get("markers_passed"):
        for m in data["markers_passed"]:
            print(f"      + {m['marker']:28s} weight={m['weight']:.2f}  gate={m['gate']}")
    if data.get("markers_filtered"):
        for m in data["markers_filtered"]:
            print(f"      x {m['marker']:28s} blocked={m['weight_blocked']:.2f}  gate={m['gate']}")

# 3. Overall Assessment
print(f"\n[3] OVERALL ASSESSMENT")
print(f"    max_nci_score:            {s3['max_nci_score']}")
print(f"    max_nci_adjusted:         {s3['max_nci_adjusted']}")
print(f"    narrative_nuance_modifier: {s3['narrative_nuance_modifier']}")
print(f"    dominant_alternative:      {s3['dominant_alternative']}")
print(f"    who_step1_conclusion:      {s3['who_step1_conclusion']}")
print(f"    noise_filtered_count:      {s3['noise_filtered_count']}")
print(f"    engine:                    {s3['engine']}")

# 4. Information Gaps
print(f"\n[4] INFORMATION GAPS")
for gap in s3.get("information_gaps", []):
    print(f"    - {gap}")

# 5. Comparison with previous
print(f"\n[5] COMPARISON WITH PREVIOUS VERSION")
print(f"    Previous: NCI=0.5, dominant=Viral myocarditis, conclusion=POSSIBLE_OTHER_CAUSE (LLM free-text)")
print(f"    Current:  NCI={s3['max_nci_score']}, adjusted={s3['max_nci_adjusted']}, dominant={s3['dominant_alternative']}, conclusion={s3['who_step1_conclusion']}")
print(f"    Engine:   {s3['engine']}")

# 6. Stage 5 Final WHO
s5 = g2["stages"]["stage5_causality"]
print(f"\n[6] STAGE 5 FINAL CLASSIFICATION")
print(f"    WHO Category: {s5['who_category']}")
print(f"    Confidence:   {s5['confidence']}")
print(f"    Decision Chain: {json.dumps(s5.get('decision_chain', {}), indent=6)}")
print(f"    Reasoning: {s5.get('reasoning', 'N/A')}")
