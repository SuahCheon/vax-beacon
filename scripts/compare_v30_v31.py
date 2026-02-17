"""
Vax-Beacon: v3.0 vs v3.1 Comparison Script
==============================================
Step 5 + Step 6 combined analysis
"""
import json, sys, glob, os
from collections import Counter

# Auto-detect newest results file
result_files = sorted(glob.glob("results/results_full_100_*.json"), key=os.path.getmtime)
OLD = "results/results_full_100_20260215_170319.json"  # v3.0

if len(sys.argv) > 1:
    NEW = sys.argv[1]
else:
    # Pick newest that is NOT the old file
    candidates = [f for f in result_files if f != OLD]
    if not candidates:
        print("ERROR: No new results file found. Pass path as argument.")
        sys.exit(1)
    NEW = candidates[-1]

print(f"OLD (v3.0): {OLD}")
print(f"NEW (v3.1): {NEW}")

with open(NEW, encoding="utf-8") as f:
    new_data = json.load(f)
with open(OLD, encoding="utf-8") as f:
    old_data = json.load(f)

old_map = {c["vaers_id"]: c for c in old_data}
new_map = {c["vaers_id"]: c for c in new_data}


# ============================================================
# Step 5: Classification Changes
# ============================================================
print("\n" + "=" * 80)
print("  STEP 5: v3.0 -> v3.1 Classification Changes")
print("=" * 80)

changes = []
for vid in sorted(old_map.keys()):
    if vid not in new_map:
        continue

    old_s5 = old_map[vid].get("stages", {}).get("stage5_causality", {})
    new_s5 = new_map[vid].get("stages", {}).get("stage5_causality", {})
    old_s6 = old_map[vid].get("stages", {}).get("stage6_guidance", {})
    new_s6 = new_map[vid].get("stages", {}).get("stage6_guidance", {})

    old_who = old_s5.get("who_category") or old_s6.get("who_category", "?")
    new_who = new_s5.get("who_category") or new_s6.get("who_category", "?")

    if old_who != new_who:
        override = new_s5.get("override_applied", False)
        reason = new_s5.get("override_reason", "")
        changes.append((vid, old_who, new_who, override, reason))
        guard_tag = f"  [GUARD: {reason}]" if override else ""
        print(f"  {vid}: {old_who} -> {new_who}{guard_tag}")

print(f"\n  Total changed: {len(changes)}")
print(f"  Expected: ~14 cases (LLM non-determinism allows +/-2)")

# Transition summary
trans = Counter()
for vid, old_who, new_who, _, _ in changes:
    trans[(old_who, new_who)] += 1
if trans:
    print("\n  Transition summary:")
    for (src, dst), cnt in sorted(trans.items(), key=lambda x: -x[1]):
        print(f"    {src} -> {dst}: {cnt} cases")


# Distribution
print("\n" + "=" * 80)
print("  WHO Category Distribution")
print("=" * 80)

old_dist = Counter()
new_dist = Counter()
for c in old_data:
    s5 = c.get("stages", {}).get("stage5_causality", {})
    s6 = c.get("stages", {}).get("stage6_guidance", {})
    old_dist[s5.get("who_category") or s6.get("who_category", "?")] += 1
for c in new_data:
    s5 = c.get("stages", {}).get("stage5_causality", {})
    s6 = c.get("stages", {}).get("stage6_guidance", {})
    new_dist[s5.get("who_category") or s6.get("who_category", "?")] += 1

print(f"\n  {'Category':>15s}   OLD   NEW    D")
print("  " + "-" * 40)
for cat in ["A1", "B1", "B2", "C", "Unclassifiable"]:
    o, n = old_dist.get(cat, 0), new_dist.get(cat, 0)
    d = n - o
    sign = "+" if d > 0 else ""
    print(f"  {cat:>15s}   {o:>3d}   {n:>3d}  ({sign}{d})")


# Guard override stats
print("\n" + "=" * 80)
print("  Decision Guard Stats")
print("=" * 80)

guard_count = sum(
    1 for c in new_data
    if c.get("stages", {}).get("stage5_causality", {}).get("override_applied")
)
print(f"\n  Cases with guard override: {guard_count}")
for c in new_data:
    s5 = c.get("stages", {}).get("stage5_causality", {})
    if s5.get("override_applied"):
        orig = s5.get("original_llm_category", s5.get("llm_raw_category", "?"))
        final = s5.get("who_category")
        reason = s5.get("override_reason", "")
        print(f"    {c['vaers_id']}: {orig} -> {final} | {reason}")


# ============================================================
# Step 5B: NCI Drift Analysis (LLM Non-determinism)
# ============================================================
print("\n" + "=" * 80)
print("  STEP 5B: NCI Drift Analysis (|delta| >= 0.15)")
print("=" * 80)

drift_cases = []
for vid in sorted(old_map.keys()):
    if vid not in new_map:
        continue
    o = old_map[vid]
    n = new_map[vid]
    if o.get("early_exit") or n.get("early_exit"):
        continue

    os3 = o.get("stages", {}).get("stage3_ddx", {})
    ns3 = n.get("stages", {}).get("stage3_ddx", {})
    o_nci = os3.get("max_nci_score")
    n_nci = ns3.get("max_nci_score")

    if o_nci is None or n_nci is None:
        continue

    delta = float(n_nci) - float(o_nci)
    if abs(delta) >= 0.15:
        # Find marker flips
        o_markers = os3.get("llm_markers_extracted", {})
        n_markers = ns3.get("llm_markers_extracted", {})
        flips = []
        for mk in set(list(o_markers.keys()) + list(n_markers.keys())):
            om = o_markers.get(mk, {})
            nm = n_markers.get(mk, {})
            op = om.get("present") if isinstance(om, dict) else None
            np_ = nm.get("present") if isinstance(nm, dict) else None
            if op != np_ and (op or np_):
                flips.append((mk, op, np_))

        os5 = o.get("stages", {}).get("stage5_causality", {})
        ns5 = n.get("stages", {}).get("stage5_causality", {})
        old_who = os5.get("who_category", "?")
        new_who = ns5.get("who_category", "?")

        drift_cases.append({
            "vid": vid, "delta": delta,
            "old_nci": o_nci, "new_nci": n_nci,
            "old_who": old_who, "new_who": new_who,
            "flips": flips,
        })

print(f"\n  Cases with NCI drift >= 0.15: {len(drift_cases)}")
if drift_cases:
    print(f"\n  {'VAERS':>10s} | old_NCI | new_NCI |  delta | old_WHO | new_WHO | marker_flips")
    print("  " + "-" * 90)
    for dc in sorted(drift_cases, key=lambda x: abs(x["delta"]), reverse=True):
        flip_str = ", ".join(f"{m}:{o}->{n}" for m, o, n in dc["flips"]) if dc["flips"] else "NONE"
        print(f"  {dc['vid']:>10d} | {float(dc['old_nci']):>7.2f} | {float(dc['new_nci']):>7.2f} | {dc['delta']:>+6.2f} | "
              f"{dc['old_who']:>7s} | {dc['new_who']:>7s} | {flip_str}")

    who_flipped = sum(1 for dc in drift_cases if dc["old_who"] != dc["new_who"])
    marker_flipped = sum(1 for dc in drift_cases if dc["flips"])
    print(f"\n  Of {len(drift_cases)} drift cases: {who_flipped} changed WHO category, {marker_flipped} had marker flips")


# ============================================================
# Step 6: Etiology-Specific Guidance Check
# ============================================================
print("\n" + "=" * 80)
print("  STEP 6A: GCM-dominant cases - EMB recommendation check")
print("=" * 80)

gcm_count = 0
gcm_emb = 0
for c in new_data:
    s3 = c.get("stages", {}).get("stage3_ddx", {})
    s6 = c.get("stages", {}).get("stage6_guidance", {})
    dom = s3.get("dominant_alternative", "")
    if dom and "giant" in str(dom).lower():
        gcm_count += 1
        gaps = s6.get("investigative_gaps", [])
        gap_text = json.dumps(gaps, ensure_ascii=False).lower()
        has_emb = "biopsy" in gap_text or "emb" in gap_text
        if has_emb:
            gcm_emb += 1
        status = "YES" if has_emb else "NO !!!"
        print(f"  VAERS {c['vaers_id']}: EMB mentioned = {status}")

if gcm_count > 0:
    print(f"\n  GCM cases: {gcm_count}, EMB mentioned: {gcm_emb} ({gcm_emb/gcm_count*100:.0f}%)")
else:
    print("  No GCM-dominant cases found")


print("\n" + "=" * 80)
print("  STEP 6B: Viral-dominant cases - viral panel / Lake Louise check")
print("=" * 80)

viral_count = 0
viral_panel = 0
viral_lake = 0
for c in new_data:
    s3 = c.get("stages", {}).get("stage3_ddx", {})
    s6 = c.get("stages", {}).get("stage6_guidance", {})
    dom = s3.get("dominant_alternative", "")
    if dom and "viral" in str(dom).lower():
        viral_count += 1
        gaps = s6.get("investigative_gaps", [])
        gap_text = json.dumps(gaps, ensure_ascii=False).lower()
        has_viral = "pcr" in gap_text or "viral panel" in gap_text or "serology" in gap_text
        has_lake = "lake louise" in gap_text or "lge" in gap_text
        if has_viral:
            viral_panel += 1
        if has_lake:
            viral_lake += 1
        print(f"  VAERS {c['vaers_id']}: viral_panel={'YES' if has_viral else 'NO'} lake_louise={'YES' if has_lake else 'NO'}")

if viral_count > 0:
    print(f"\n  Viral cases: {viral_count}, viral_panel: {viral_panel} ({viral_panel/viral_count*100:.0f}%), lake_louise: {viral_lake} ({viral_lake/viral_count*100:.0f}%)")
else:
    print("  No Viral-dominant cases found")


# ============================================================
# Step 6C: 1313197 Deep Dive
# ============================================================
print("\n" + "=" * 80)
print("  STEP 6C: Case 1313197 Full Stage 6 Output")
print("=" * 80)

for c in new_data:
    if c["vaers_id"] == 1313197:
        s3 = c["stages"]["stage3_ddx"]
        s5 = c["stages"]["stage5_causality"]
        s6 = c["stages"]["stage6_guidance"]

        print(f"\n  Stage 3:")
        print(f"    max_nci_score:        {s3.get('max_nci_score')}")
        print(f"    max_nci_adjusted:     {s3.get('max_nci_adjusted')}")
        print(f"    epistemic_uncertainty: {s3.get('epistemic_uncertainty')}")
        print(f"    who_step1_conclusion: {s3.get('who_step1_conclusion')}")
        print(f"    dominant_alternative: {s3.get('dominant_alternative')}")

        print(f"\n  Stage 5:")
        print(f"    who_category:        {s5.get('who_category')}")
        print(f"    override_applied:    {s5.get('override_applied')}")
        print(f"    override_reason:     {s5.get('override_reason')}")

        print(f"\n  Stage 6 investigative_gaps:")
        gaps = s6.get("investigative_gaps", [])
        for i, g in enumerate(gaps):
            if isinstance(g, dict):
                print(f"    [{i+1}] {g.get('gap', '')}")
                print(f"        priority: {g.get('priority', '')}")
                print(f"        action:   {g.get('action', '')[:120]}")
            else:
                print(f"    [{i+1}] {g}")
        break


# ============================================================
# Step 6D: epistemic_uncertainty distribution
# ============================================================
print("\n" + "=" * 80)
print("  BONUS: epistemic_uncertainty Distribution (v3.1)")
print("=" * 80)

eu_vals = []
for c in new_data:
    if c.get("early_exit"):
        continue
    s3 = c.get("stages", {}).get("stage3_ddx", {})
    eu = s3.get("epistemic_uncertainty")
    if eu is not None:
        eu_vals.append(float(eu))

if eu_vals:
    print(f"  Cases with epistemic_uncertainty: {len(eu_vals)}")
    print(f"  Mean: {sum(eu_vals)/len(eu_vals):.3f}")
    print(f"  Min:  {min(eu_vals):.2f}")
    print(f"  Max:  {max(eu_vals):.2f}")
    eu_dist = Counter()
    for v in eu_vals:
        if v == 0:
            eu_dist["0.0"] += 1
        elif v <= 0.3:
            eu_dist["0.01-0.30"] += 1
        elif v <= 0.5:
            eu_dist["0.31-0.50"] += 1
        elif v <= 0.7:
            eu_dist["0.51-0.70"] += 1
        else:
            eu_dist["0.71-1.0"] += 1
    for bucket in ["0.0", "0.01-0.30", "0.31-0.50", "0.51-0.70", "0.71-1.0"]:
        print(f"    {bucket}: {eu_dist.get(bucket, 0)} cases")
else:
    print("  No epistemic_uncertainty values found")


print("\n" + "=" * 80)
print("  COMPARISON COMPLETE")
print("=" * 80)
