"""
Vax-Beacon: Comparison Script — Baseline (v1) vs Updated Stage 3 (v2)
========================================================================
4 dimensions:
  1. WHO 분포 변화 (특히 DEFINITE → POSSIBLE 전환)
  2. Ischemic NCI 변화 (age<40 cases)
  3. biological_rationale 필드 채워졌는지
  4. Pericarditis clean→C 해소 여부
"""

import json
from collections import Counter

OLD_PATH = "results/results_full_100_20260215_135820.json"
NEW_PATH = "results/results_full_100_20260215_170319.json"

with open(OLD_PATH, "r", encoding="utf-8") as f:
    old_list = json.load(f)
with open(NEW_PATH, "r", encoding="utf-8") as f:
    new_list = json.load(f)

old_cases = {str(c["vaers_id"]): c for c in old_list}
new_cases = {str(c["vaers_id"]): c for c in new_list}

common_ids = sorted(set(old_cases.keys()) & set(new_cases.keys()))
print(f"Cases in common: {len(common_ids)}")


def s3(case):
    return case.get("stages", {}).get("stage3_ddx", {})

def s5(case):
    return case.get("stages", {}).get("stage5_causality", {})

def s1(case):
    return case.get("stages", {}).get("stage1_icsr", {})

def get_who(case):
    return s5(case).get("who_category", case.get("who_category", "?"))

def get_age(case):
    icsr = s1(case)
    demos = icsr.get("demographics", {})
    return demos.get("age_years", demos.get("age", None))

def get_isch_nci(case):
    nci_d = s3(case).get("nci_detailed", {})
    isch = nci_d.get("ischemic_heart_disease", {})
    return isch.get("nci_score", None)

def get_marker(case, marker_name):
    markers = s3(case).get("llm_markers_extracted", {})
    return markers.get(marker_name, None)


# ============================================================
# 1. WHO 분포 변화 — transition matrix
# ============================================================
print("\n" + "="*70)
print("  1. WHO Category Distribution Change")
print("="*70)

old_who_counts = Counter()
new_who_counts = Counter()
transitions = Counter()
transition_details = []

for vid in common_ids:
    o = old_cases[vid]
    n = new_cases[vid]
    ow = get_who(o)
    nw = get_who(n)
    old_who_counts[ow] += 1
    new_who_counts[nw] += 1
    if ow != nw:
        transitions[(ow, nw)] += 1
        transition_details.append({"vaers_id": vid, "old": ow, "new": nw})

print("\n  Category       |  OLD  |  NEW  |  Δ")
print("  " + "-"*44)
for cat in ["A1", "A2", "A3", "A4", "B1", "B2", "C", "Unclassifiable"]:
    o = old_who_counts.get(cat, 0)
    n = new_who_counts.get(cat, 0)
    delta = n - o
    sign = "+" if delta > 0 else ""
    bar = ""
    if delta != 0:
        bar = f"  {'↑' if delta > 0 else '↓'}"
    print(f"  {cat:<15s}   {o:>4d}   {n:>4d}   {sign}{delta}{bar}")

print(f"\n  Total transitions: {sum(transitions.values())} cases changed WHO category")
if transitions:
    print("\n  Transition Detail:")
    for (src, dst), cnt in sorted(transitions.items(), key=lambda x: -x[1]):
        print(f"    {src} → {dst}: {cnt} cases")

# Individual case transitions
if transition_details:
    print(f"\n  Per-case transitions:")
    for td in transition_details:
        print(f"    VAERS {td['vaers_id']}: {td['old']} → {td['new']}")

# Step1 conclusion changes
print("\n  --- Step1 Conclusion Changes (Stage 3) ---")
step1_transitions = Counter()
step1_details = []
for vid in common_ids:
    o = old_cases[vid]
    n = new_cases[vid]
    if o.get("early_exit") or n.get("early_exit"):
        continue
    os1 = s3(o).get("who_step1_conclusion", "N/A")
    ns1 = s3(n).get("who_step1_conclusion", "N/A")
    if os1 != ns1:
        step1_transitions[(os1, ns1)] += 1
        step1_details.append({
            "vaers_id": vid,
            "old_step1": os1, "new_step1": ns1,
            "old_nci": s3(o).get("max_nci_score"), "new_nci": s3(n).get("max_nci_score"),
            "old_who": get_who(o), "new_who": get_who(n),
        })

if step1_transitions:
    for (src, dst), cnt in sorted(step1_transitions.items(), key=lambda x: -x[1]):
        print(f"    {src} → {dst}: {cnt} cases")
    print()
    for sd in step1_details:
        print(f"    VAERS {sd['vaers_id']}: Step1 {sd['old_step1']}→{sd['new_step1']} "
              f"| NCI {sd['old_nci']}→{sd['new_nci']} | WHO {sd['old_who']}→{sd['new_who']}")
else:
    print("    No Step1 conclusion changes detected")


# ============================================================
# 2. Ischemic NCI 변화 (age < 40 cases)
# ============================================================
print("\n" + "="*70)
print("  2. Ischemic NCI Changes (age < 40 cases)")
print("="*70)

ischemic_changes = []
for vid in common_ids:
    o = old_cases[vid]
    n = new_cases[vid]
    if o.get("early_exit") or n.get("early_exit"):
        continue

    age = get_age(o)
    if age is None:
        age = get_age(n)

    try:
        age_num = float(age) if age is not None else 999
    except (ValueError, TypeError):
        age_num = 999

    o_isch = get_isch_nci(o)
    n_isch = get_isch_nci(n)
    o_focal = get_marker(o, "focal_st_changes")
    n_focal = get_marker(n, "focal_st_changes")

    if age_num < 40:
        ischemic_changes.append({
            "vaers_id": vid,
            "age": age,
            "group": o.get("group", "?"),
            "old_isch_nci": o_isch,
            "new_isch_nci": n_isch,
            "old_focal": o_focal.get("present") if isinstance(o_focal, dict) else o_focal,
            "new_focal": n_focal.get("present") if isinstance(n_focal, dict) else n_focal,
            "old_who": get_who(o),
            "new_who": get_who(n),
        })

changed_isch = [c for c in ischemic_changes if c["old_isch_nci"] != c["new_isch_nci"]]
print(f"\n  Age<40 non-early-exit cases: {len(ischemic_changes)}")
print(f"  Ischemic NCI changed: {len(changed_isch)}")

if changed_isch:
    print(f"\n  {'VAERS':>10s} | Age | Group      | Old_NCI | New_NCI | Old_focal | New_focal | Old_WHO | New_WHO")
    print("  " + "-"*100)
    for c in sorted(changed_isch, key=lambda x: float(x["old_isch_nci"] or 0), reverse=True):
        print(f"  {c['vaers_id']:>10s} | {str(c['age']):>3s} | {str(c['group']):>10s} | "
              f"{str(c['old_isch_nci']):>7s} | {str(c['new_isch_nci']):>7s} | "
              f"{str(c['old_focal']):>9s} | {str(c['new_focal']):>9s} | "
              f"{c['old_who']:>7s} | {c['new_who']:>7s}")

# All age<40 with ischemic data
print(f"\n  All age<40 ischemic NCI summary:")
for c in ischemic_changes:
    if c["old_isch_nci"] and float(c["old_isch_nci"]) > 0:
        delta = float(c["new_isch_nci"] or 0) - float(c["old_isch_nci"])
        print(f"    VAERS {c['vaers_id']} (age={c['age']}, {c['group']}): "
              f"NCI {c['old_isch_nci']}→{c['new_isch_nci']} | "
              f"focal {c['old_focal']}→{c['new_focal']} | "
              f"WHO {c['old_who']}→{c['new_who']}")

# focal_st_changes flips across ALL ages
print(f"\n  --- focal_st_changes flips (all ages) ---")
focal_flips = []
for vid in common_ids:
    o = old_cases[vid]
    n = new_cases[vid]
    if o.get("early_exit"):
        continue
    o_f = get_marker(o, "focal_st_changes")
    n_f = get_marker(n, "focal_st_changes")
    o_present = o_f.get("present") if isinstance(o_f, dict) else o_f
    n_present = n_f.get("present") if isinstance(n_f, dict) else n_f
    if o_present != n_present:
        age = get_age(o)
        focal_flips.append({"vaers_id": vid, "age": age, "old": o_present, "new": n_present})

print(f"  Total flips: {len(focal_flips)}")
for ff in focal_flips:
    print(f"    VAERS {ff['vaers_id']} (age={ff['age']}): focal_st_changes {ff['old']} → {ff['new']}")


# ============================================================
# 3. biological_rationale 필드 채워졌는지
# ============================================================
print("\n" + "="*70)
print("  3. biological_rationale Field Quality")
print("="*70)

def count_bio_rationale(cases_dict):
    total_markers = 0
    filled_br = 0
    empty_br = 0
    for vid, case in cases_dict.items():
        if case.get("early_exit"):
            continue
        markers = s3(case).get("llm_markers_extracted", {})
        if not isinstance(markers, dict):
            continue
        for mk_name, mk_val in markers.items():
            if not isinstance(mk_val, dict):
                continue
            total_markers += 1
            br = mk_val.get("biological_rationale", "")
            if br and str(br).strip() and str(br).strip().lower() != "not identified in narrative.":
                filled_br += 1
            else:
                empty_br += 1
    return total_markers, filled_br, empty_br

o_total, o_filled, o_empty = count_bio_rationale(old_cases)
n_total, n_filled, n_empty = count_bio_rationale(new_cases)

print(f"\n  Marker-level biological_rationale:")
print(f"    OLD: {o_total} markers, {o_filled} meaningful ({o_filled/o_total*100:.1f}%), "
      f"{o_empty} empty/boilerplate ({o_empty/o_total*100:.1f}%)")
print(f"    NEW: {n_total} markers, {n_filled} meaningful ({n_filled/n_total*100:.1f}%), "
      f"{n_empty} empty/boilerplate ({n_empty/n_total*100:.1f}%)")

# Check category-level rationale in nci_detailed
def count_category_rationale(cases_dict):
    total_cats = 0
    with_rationale = 0
    for vid, case in cases_dict.items():
        if case.get("early_exit"):
            continue
        nci_d = s3(case).get("nci_detailed", {})
        if not isinstance(nci_d, dict):
            continue
        for cat_name, cat_data in nci_d.items():
            if not isinstance(cat_data, dict):
                continue
            if cat_data.get("nci_score", 0) > 0:
                total_cats += 1
                # Check if markers_passed have rationale
                passed = cat_data.get("markers_passed", [])
                if passed and any(m.get("rationale") for m in passed if isinstance(m, dict)):
                    with_rationale += 1
    return total_cats, with_rationale

o_cats, o_with_r = count_category_rationale(old_cases)
n_cats, n_with_r = count_category_rationale(new_cases)
print(f"\n  Active categories (NCI>0) with marker rationales:")
print(f"    OLD: {o_cats} active categories, {o_with_r} with rationale")
print(f"    NEW: {n_cats} active categories, {n_with_r} with rationale")


# ============================================================
# 4. Pericarditis clean → C 해소 여부
# ============================================================
print("\n" + "="*70)
print("  4. Pericarditis Clean Cases — C Resolution")
print("="*70)

peri_clean_cases = []
for vid in common_ids:
    o = old_cases[vid]
    n = new_cases[vid]

    ae_type = o.get("condition_type", "")
    group = o.get("group", "")

    if "pericarditis" in str(ae_type).lower() and "clean" in str(group).lower():
        peri_clean_cases.append({
            "vaers_id": vid,
            "old_who": get_who(o),
            "new_who": get_who(n),
            "old_nci": s3(o).get("max_nci_score", "?"),
            "new_nci": s3(n).get("max_nci_score", "?"),
            "old_step1": s3(o).get("who_step1_conclusion", "?"),
            "new_step1": s3(n).get("who_step1_conclusion", "?"),
            "old_isch": get_isch_nci(o),
            "new_isch": get_isch_nci(n),
            "old_adj": s3(o).get("max_nci_adjusted", "?"),
            "new_adj": s3(n).get("max_nci_adjusted", "?"),
        })

print(f"\n  Pericarditis clean cases: {len(peri_clean_cases)}")
print(f"\n  {'VAERS':>10s} | Old_WHO     | New_WHO     | Old_NCI | New_NCI | Old_adj | New_adj | Old_Step1              | New_Step1")
print("  " + "-"*125)

old_c_count = 0
new_c_count = 0
fixed_count = 0
for pc in peri_clean_cases:
    if pc["old_who"] == "C":
        old_c_count += 1
    if pc["new_who"] == "C":
        new_c_count += 1

    status = ""
    if pc["old_who"] == "C" and pc["new_who"] != "C":
        status = " ✓ FIXED"
        fixed_count += 1
    elif pc["old_who"] == "C" and pc["new_who"] == "C":
        status = " ⚠ STILL_C"
    elif pc["old_who"] != "C":
        status = " ★ WAS_OK"

    print(f"  {pc['vaers_id']:>10s} | {pc['old_who']:>11s} | {pc['new_who']:>11s} | "
          f"{str(pc['old_nci']):>7s} | {str(pc['new_nci']):>7s} | "
          f"{str(pc['old_adj']):>7s} | {str(pc['new_adj']):>7s} | "
          f"{str(pc['old_step1']):>22s} | {str(pc['new_step1']):>22s}{status}")

print(f"\n  Summary: OLD had {old_c_count}/4 peri_clean=C → NEW has {new_c_count}/4 peri_clean=C")
if fixed_count:
    print(f"  ✓ {fixed_count} cases resolved from C to better category")


# ============================================================
# 5. BONUS: Overall NCI distribution shift
# ============================================================
print("\n" + "="*70)
print("  5. BONUS: Overall max_nci Shift")
print("="*70)

old_nci_vals = []
new_nci_vals = []
nci_changes = []

for vid in common_ids:
    o = old_cases[vid]
    n = new_cases[vid]
    if o.get("early_exit"):
        continue
    o_nci = s3(o).get("max_nci_score")
    n_nci = s3(n).get("max_nci_score")
    if o_nci is not None:
        old_nci_vals.append(float(o_nci))
    if n_nci is not None:
        new_nci_vals.append(float(n_nci))
    if o_nci != n_nci:
        nci_changes.append({
            "vaers_id": vid,
            "old_nci": o_nci,
            "new_nci": n_nci,
            "old_who": get_who(o),
            "new_who": get_who(n),
        })

print(f"\n  Non-early-exit cases: {len(old_nci_vals)}")
if old_nci_vals:
    print(f"  OLD max_nci mean: {sum(old_nci_vals)/len(old_nci_vals):.3f}")
if new_nci_vals:
    print(f"  NEW max_nci mean: {sum(new_nci_vals)/len(new_nci_vals):.3f}")
print(f"  max_nci changed: {len(nci_changes)} cases")

decreased = [c for c in nci_changes if float(c["new_nci"] or 0) < float(c["old_nci"] or 0)]
increased = [c for c in nci_changes if float(c["new_nci"] or 0) > float(c["old_nci"] or 0)]
print(f"  NCI decreased: {len(decreased)} | NCI increased: {len(increased)}")

if decreased:
    print(f"\n  NCI drops (largest first):")
    for c in sorted(decreased, key=lambda x: float(x["old_nci"] or 0) - float(x["new_nci"] or 0), reverse=True):
        delta = float(c["new_nci"] or 0) - float(c["old_nci"] or 0)
        print(f"    VAERS {c['vaers_id']}: NCI {c['old_nci']} → {c['new_nci']} (Δ={delta:+.2f}) | WHO: {c['old_who']} → {c['new_who']}")


# ============================================================
# 6. BONUS: Risk factor weight=0 verification
# ============================================================
print("\n" + "="*70)
print("  6. BONUS: Risk Factor Weight=0 Verification")
print("="*70)

risk_markers = ["age_over_50", "diabetes_hypertension", "smoking_history"]

def check_risk_weights(cases_dict, label):
    present_count = 0
    nonzero_weight = 0
    filtered_count = 0
    for vid, case in cases_dict.items():
        if case.get("early_exit"):
            continue
        nci_d = s3(case).get("nci_detailed", {})
        isch = nci_d.get("ischemic_heart_disease", {})
        # Check markers_filtered (risk factors that were blocked)
        filtered = isch.get("markers_filtered", [])
        for f in filtered:
            if isinstance(f, dict) and f.get("marker") in risk_markers:
                filtered_count += 1
        # Check markers_passed (risk factors that somehow passed)
        passed = isch.get("markers_passed", [])
        for p in passed:
            if isinstance(p, dict) and p.get("marker") in risk_markers:
                nonzero_weight += 1
        # Check extracted markers
        markers = s3(case).get("llm_markers_extracted", {})
        for rm in risk_markers:
            mk = markers.get(rm, {})
            if isinstance(mk, dict) and mk.get("present"):
                present_count += 1
    return present_count, nonzero_weight, filtered_count

o_pres, o_nonzero, o_filt = check_risk_weights(old_cases, "OLD")
n_pres, n_nonzero, n_filt = check_risk_weights(new_cases, "NEW")

print(f"\n  OLD: risk factors present={o_pres}, passed_to_NCI={o_nonzero}, filtered={o_filt}")
print(f"  NEW: risk factors present={n_pres}, passed_to_NCI={n_nonzero}, filtered={n_filt}")
if n_nonzero == 0:
    print("  ✓ No risk factor markers contributing to NCI in new results (weight=0 working)")


# ============================================================
# 7. BONUS: Nuance cap at 0.69 verification
# ============================================================
print("\n" + "="*70)
print("  7. BONUS: Nuance Cap at 0.69 Verification")
print("="*70)

old_nuance_boost = 0
new_nuance_boost = 0
capped_cases = []

for vid in common_ids:
    o = old_cases[vid]
    n = new_cases[vid]
    if o.get("early_exit"):
        continue

    o_s3d = s3(o)
    n_s3d = s3(n)

    o_max = o_s3d.get("max_nci_score", 0)
    n_max = n_s3d.get("max_nci_score", 0)
    o_adj = o_s3d.get("max_nci_adjusted", 0)
    n_adj = n_s3d.get("max_nci_adjusted", 0)
    o_nuance = o_s3d.get("narrative_nuance_modifier", 0)
    n_nuance = n_s3d.get("narrative_nuance_modifier", 0)

    # Old: nuance boosted past 0.7
    if o_adj and float(o_adj) >= 0.7 and float(o_max or 0) < 0.7 and float(o_nuance or 0) > 0:
        old_nuance_boost += 1

    # New: check if capped at 0.69
    if n_adj is not None and float(str(n_adj)) == 0.69:
        capped_cases.append({
            "vaers_id": vid,
            "max_nci": n_max,
            "adjusted": n_adj,
            "nuance_mod": n_nuance,
            "step1": n_s3d.get("who_step1_conclusion"),
        })

    # New: no DEFINITE from nuance alone
    if n_s3d.get("who_step1_conclusion") == "DEFINITE_OTHER_CAUSE":
        if n_max is not None and float(n_max) < 0.7:
            print(f"  ⚠ WARNING: VAERS {vid} DEFINITE with max_nci={n_max} < 0.7 (nuance cap failure?)")

print(f"\n  OLD: nuance-boosted to ≥0.7 (DEFINITE from nuance): {old_nuance_boost} cases")
print(f"  NEW: adjusted_max capped at exactly 0.69: {len(capped_cases)} cases")
for nc in capped_cases:
    print(f"    VAERS {nc['vaers_id']}: max_nci={nc['max_nci']}, adjusted={nc['adjusted']}, "
          f"nuance_mod={nc['nuance_mod']}, step1={nc['step1']}")

# Count DEFINITE in new results (must be from clinical NCI ≥0.7)
new_definite = []
for vid in common_ids:
    n = new_cases[vid]
    if n.get("early_exit"):
        continue
    n_s3d = s3(n)
    if n_s3d.get("who_step1_conclusion") == "DEFINITE_OTHER_CAUSE":
        new_definite.append({
            "vaers_id": vid,
            "max_nci": n_s3d.get("max_nci_score"),
        })

print(f"\n  NEW DEFINITE cases (clinical NCI≥0.7 only): {len(new_definite)}")
for nd in new_definite:
    print(f"    VAERS {nd['vaers_id']}: max_nci={nd['max_nci']}")


print("\n" + "="*70)
print("  COMPARISON COMPLETE")
print("="*70)
