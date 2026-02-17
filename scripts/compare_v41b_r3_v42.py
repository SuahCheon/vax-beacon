"""
Compare v4.1b-r3 vs v4.2 results.

v4.2 changes:
  - Brighton Level 4 early exit now generates structured guidance (Stage 6)
  - Onset unknown Unclassifiable output standardized with shared fields
  - Both Unclassifiable paths now include: who_category, unclassifiable_reason,
    what_is_known, what_is_missing, recommended_actions, reassessment_potential

Expected:
  - WHO classification: 0 changes (Stage 3/4/5 code unchanged)
  - All Unclassifiable cases: Stage 6 output present with standardized fields
  - Non-Unclassifiable cases: Stage 6 output functionally unchanged
"""

import json
import glob
import sys


def load_latest_results(pattern):
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"ERROR: No files matching {pattern}")
        sys.exit(1)
    path = files[-1]
    print(f"  Loading: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f), path


def get_who(case):
    s5 = case.get("stages", {}).get("stage5_causality", {})
    s6 = case.get("stages", {}).get("stage6_guidance", {})
    return s5.get("who_category") or s6.get("who_category", "ERROR")


def get_stage6(case):
    return case.get("stages", {}).get("stage6_guidance", {})


def get_max_nci(case):
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("max_nci_score", 0)


def get_temporal_zone(case):
    s4 = case.get("stages", {}).get("stage4_temporal", {})
    return s4.get("temporal_assessment", {}).get("temporal_zone", "N/A")


def get_investigation_intensity(case):
    s4 = case.get("stages", {}).get("stage4_temporal", {})
    return s4.get("temporal_assessment", {}).get("investigation_intensity", "N/A")


def get_decision_chain(case):
    s5 = case.get("stages", {}).get("stage5_causality", {})
    return s5.get("decision_chain", {})


def get_dominant_alternative(case):
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("dominant_alternative", "NONE")


def get_markers_extracted(case):
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("llm_markers_extracted", {})


def main():
    print("\n" + "=" * 75)
    print("  Vax-Beacon: v4.1b-r3 vs v4.2 Comparison")
    print("=" * 75)

    print("\nLoading results...")
    v_r3, r3_path = load_latest_results("results/results_v4_full_100_20260216_200524.json")
    v_42, v42_path = load_latest_results("results/results_v4_full_100_20260216_2*.json")

    # Ensure we're not comparing same file
    if r3_path == v42_path:
        # Try finding v4.2 by getting the last file that isn't the r3 file
        all_files = sorted(glob.glob("results/results_v4_full_100_*.json"))
        v42_candidates = [f for f in all_files if f != r3_path]
        if not v42_candidates:
            print("ERROR: Cannot find v4.2 results file distinct from r3")
            sys.exit(1)
        v42_path = v42_candidates[-1]
        print(f"  Re-loading v4.2: {v42_path}")
        with open(v42_path, encoding="utf-8") as f:
            v_42 = json.load(f)

    r3_valid = [c for c in v_r3 if not c.get("errors")]
    v42_valid = [c for c in v_42 if not c.get("errors")]

    r3_map = {c["vaers_id"]: c for c in r3_valid}
    v42_map = {c["vaers_id"]: c for c in v42_valid}
    common = sorted(set(r3_map.keys()) & set(v42_map.keys()))

    print(f"\n  v4.1b-r3: {len(v_r3)} total, {len(r3_valid)} valid")
    print(f"  v4.2:     {len(v_42)} total, {len(v42_valid)} valid")
    print(f"  Common:   {len(common)}")

    # ==================================================================
    # 1. WHO Classification (expect 0 changes)
    # ==================================================================
    print("\n" + "=" * 75)
    print("  1. WHO Classification Changes (expect: 0)")
    print("=" * 75)

    cats_r3 = {}
    cats_42 = {}
    changed = []
    for vid in common:
        w3 = get_who(r3_map[vid])
        w42 = get_who(v42_map[vid])
        cats_r3[w3] = cats_r3.get(w3, 0) + 1
        cats_42[w42] = cats_42.get(w42, 0) + 1
        if w3 != w42:
            changed.append({
                "vaers_id": vid, "r3": w3, "v42": w42,
                "nci_r3": get_max_nci(r3_map[vid]),
                "nci_42": get_max_nci(v42_map[vid]),
            })

    all_cats = sorted(set(list(cats_r3.keys()) + list(cats_42.keys())))
    print(f"\n  {'Category':<16s} {'r3':>6s} {'v4.2':>6s} {'Delta':>6s}")
    print(f"  {'-' * 38}")
    for cat in all_cats:
        c3 = cats_r3.get(cat, 0)
        c42 = cats_42.get(cat, 0)
        d = c42 - c3
        ds = f"+{d}" if d > 0 else str(d) if d < 0 else "0"
        print(f"  {cat:<16s} {c3:>6d} {c42:>6d} {ds:>6s}")

    if changed:
        print(f"\n  WARNING: {len(changed)} WHO changes (expected 0):")
        for c in changed:
            print(f"    VAERS {c['vaers_id']}: {c['r3']} -> {c['v42']} "
                  f"(NCI: {c['nci_r3']} -> {c['nci_42']})")
    else:
        print(f"\n  OK: 0 WHO changes.")

    # ==================================================================
    # 2. Unclassifiable Output Standardization (KEY v4.2 METRIC)
    # ==================================================================
    print("\n" + "=" * 75)
    print("  2. Unclassifiable Output Standardization")
    print("=" * 75)

    # Required fields for all Unclassifiable cases
    required_fields = [
        "who_category", "unclassifiable_reason", "what_is_known",
        "what_is_missing", "recommended_actions", "reassessment_potential",
        "quality_flags", "officer_summary", "mode",
    ]

    for label, vmap in [("r3", r3_map), ("v4.2", v42_map)]:
        print(f"\n  --- {label} ---")

        # Identify Unclassifiable cases
        unclass = []
        for vid in common:
            who = get_who(vmap[vid])
            if who == "Unclassifiable":
                unclass.append(vid)

        brighton_exit = []
        onset_unknown = []
        other_unclass = []

        for vid in unclass:
            s6 = get_stage6(vmap[vid])
            mode = s6.get("mode", "")
            if mode == "brighton_exit":
                brighton_exit.append(vid)
            elif mode == "onset_unknown":
                onset_unknown.append(vid)
            elif vmap[vid].get("early_exit"):
                brighton_exit.append(vid)  # r3 early exits without mode field
            else:
                dc = get_decision_chain(vmap[vid])
                if dc.get("onset_unknown"):
                    onset_unknown.append(vid)
                else:
                    other_unclass.append(vid)

        print(f"    Total Unclassifiable: {len(unclass)}")
        print(f"      Brighton L4: {len(brighton_exit)}")
        print(f"      Onset unknown: {len(onset_unknown)}")
        if other_unclass:
            print(f"      Other: {len(other_unclass)} — {other_unclass}")

        # Check required fields
        has_s6 = 0
        field_coverage = {f: 0 for f in required_fields}
        for vid in unclass:
            s6 = get_stage6(vmap[vid])
            if s6:
                has_s6 += 1
            for f in required_fields:
                if s6.get(f):
                    field_coverage[f] += 1

        print(f"    Stage 6 output present: {has_s6}/{len(unclass)}")
        print(f"    Required field coverage:")
        for f in required_fields:
            pct = field_coverage[f] / len(unclass) * 100 if unclass else 0
            status = "OK" if field_coverage[f] == len(unclass) else "PARTIAL" if field_coverage[f] > 0 else "MISSING"
            print(f"      {f:<24s}: {field_coverage[f]:>3d}/{len(unclass)} "
                  f"({pct:>5.1f}%) [{status}]")

    # ==================================================================
    # 3. Brighton Exit Guidance Quality (v4.2 only)
    # ==================================================================
    print("\n" + "=" * 75)
    print("  3. Brighton Exit Guidance Quality (v4.2)")
    print("=" * 75)

    brighton_fields = [
        "missing_brighton_criteria", "diagnostic_deficiencies",
        "fastest_path_to_classification", "what_is_known",
        "what_is_missing", "recommended_actions",
    ]

    brighton_cases = []
    for vid in common:
        if v42_map[vid].get("early_exit"):
            brighton_cases.append(vid)

    print(f"\n  Brighton L4 cases: {len(brighton_cases)}")
    field_counts = {f: 0 for f in brighton_fields}
    for vid in brighton_cases:
        s6 = get_stage6(v42_map[vid])
        for f in brighton_fields:
            val = s6.get(f)
            if val and (not isinstance(val, (list, dict)) or len(val) > 0):
                field_counts[f] += 1

    for f in brighton_fields:
        pct = field_counts[f] / len(brighton_cases) * 100 if brighton_cases else 0
        print(f"    {f:<35s}: {field_counts[f]:>3d}/{len(brighton_cases)} ({pct:>5.1f}%)")

    # Average diagnostic_deficiencies count
    dd_counts = []
    for vid in brighton_cases:
        s6 = get_stage6(v42_map[vid])
        dd = s6.get("diagnostic_deficiencies", [])
        dd_counts.append(len(dd))
    if dd_counts:
        avg_dd = sum(dd_counts) / len(dd_counts)
        print(f"\n    Avg diagnostic_deficiencies per case: {avg_dd:.1f} "
              f"(range: {min(dd_counts)}-{max(dd_counts)})")

    # ==================================================================
    # 4. Onset Unknown Guidance Quality (v4.2 only)
    # ==================================================================
    print("\n" + "=" * 75)
    print("  4. Onset Unknown Guidance Quality (v4.2)")
    print("=" * 75)

    onset_fields = [
        "onset_verification", "possible_categories_once_onset_known",
        "investigative_gaps", "what_is_known", "what_is_missing",
        "reassessment_potential",
    ]

    onset_cases = []
    for vid in common:
        dc = get_decision_chain(v42_map[vid])
        if dc.get("onset_unknown"):
            onset_cases.append(vid)

    print(f"\n  Onset unknown cases: {len(onset_cases)}")
    for vid in onset_cases:
        s6 = get_stage6(v42_map[vid])
        present = []
        missing = []
        for f in onset_fields:
            val = s6.get(f)
            if val and (not isinstance(val, (list, dict)) or len(val) > 0):
                present.append(f)
            else:
                missing.append(f)
        status = "OK" if not missing else f"MISSING: {missing}"
        print(f"    VAERS {vid}: {len(present)}/{len(onset_fields)} fields [{status}]")

    # ==================================================================
    # 5. Non-Unclassifiable Regression Check
    # ==================================================================
    print("\n" + "=" * 75)
    print("  5. Non-Unclassifiable Stage 6 Regression Check")
    print("=" * 75)

    non_unclass = [vid for vid in common if get_who(v42_map[vid]) != "Unclassifiable"]
    print(f"\n  Non-Unclassifiable cases: {len(non_unclass)}")

    # Check that key Stage 6 fields are still present
    s6_fields = ["investigative_gaps", "recommended_actions", "officer_summary", "quality_flags"]
    for f in s6_fields:
        r3_count = sum(1 for vid in non_unclass
                       if get_stage6(r3_map[vid]).get(f))
        v42_count = sum(1 for vid in non_unclass
                        if get_stage6(v42_map[vid]).get(f))
        delta = v42_count - r3_count
        ds = f"+{delta}" if delta > 0 else str(delta) if delta < 0 else "0"
        print(f"    {f:<24s}: r3={r3_count:>3d}, v4.2={v42_count:>3d} (delta={ds})")

    # ==================================================================
    # 6. Carry-forward Metrics
    # ==================================================================
    print("\n" + "=" * 75)
    print("  6. Carry-forward Metrics (v4.2)")
    print("=" * 75)

    # MRI framing
    bad_phrases = ["vaccine vs viral", "vaccine versus viral",
                   "distinguish vaccine from viral",
                   "vaccine-induced vs viral",
                   "differentiate vaccine from viral"]

    for label, vmap in [("r3", r3_map), ("v4.2", v42_map)]:
        bad_count = 0
        for vid in common:
            s6 = get_stage6(vmap[vid])
            s6_str = json.dumps(s6).lower()
            for phrase in bad_phrases:
                if phrase in s6_str:
                    bad_count += 1
                    break
        print(f"\n  MRI framing ({label}): {bad_count} instances")

    # Bridging
    bg_count = 0
    bridging_ok = 0
    for vid in common:
        tz = get_temporal_zone(v42_map[vid])
        if tz in ("BACKGROUND_RATE", "UNLIKELY"):
            bg_count += 1
            s6 = get_stage6(v42_map[vid])
            if "bridging" in json.dumps(s6).lower():
                bridging_ok += 1

    print(f"\n  Bridging (v4.2): {bridging_ok}/{bg_count} "
          f"({bridging_ok/bg_count*100:.0f}%)" if bg_count else
          "\n  Bridging: N/A")

    # Scope monotonicity
    ig = {}
    for vid in common:
        intensity = get_investigation_intensity(v42_map[vid])
        if intensity == "N/A":
            continue
        s6 = get_stage6(v42_map[vid])
        gaps = s6.get("investigative_gaps", [])
        ig.setdefault(intensity, []).append(len(gaps))

    for i in ["STANDARD", "ENHANCED", "COMPREHENSIVE"]:
        if i in ig:
            vals = ig[i]
            avg = sum(vals) / len(vals)
            print(f"  Scope {i}: avg={avg:.1f}, n={len(vals)}")

    if all(k in ig for k in ["STANDARD", "ENHANCED", "COMPREHENSIVE"]):
        avgs = {k: sum(v)/len(v) for k, v in ig.items()}
        mono = avgs["STANDARD"] < avgs["ENHANCED"] < avgs["COMPREHENSIVE"]
        print(f"  Monotonicity: {'OK' if mono else 'FAIL'}")

    # Nucleocapsid
    covid_nondom_ok = 0
    covid_nondom_total = 0
    for vid in common:
        markers = get_markers_extracted(v42_map[vid])
        ac = markers.get("active_covid19", {})
        if not ac.get("present"):
            continue
        dom = get_dominant_alternative(v42_map[vid])
        is_covid_dom = "covid" in dom.lower() if dom != "NONE" else False
        if not is_covid_dom:
            covid_nondom_total += 1
            s6 = get_stage6(v42_map[vid])
            if "nucleocapsid" in json.dumps(s6).lower():
                covid_nondom_ok += 1

    print(f"\n  Nucleocapsid (non-dom COVID, v4.2): {covid_nondom_ok}/{covid_nondom_total}"
          if covid_nondom_total else "\n  Nucleocapsid: N/A")

    # ==================================================================
    # 7. Error Summary
    # ==================================================================
    print("\n" + "=" * 75)
    print("  7. Errors")
    print("=" * 75)
    errors_r3 = [c for c in v_r3 if c.get("errors")]
    errors_42 = [c for c in v_42 if c.get("errors")]
    print(f"\n  r3 errors: {len(errors_r3)}")
    print(f"  v4.2 errors: {len(errors_42)}")
    if errors_42:
        for c in errors_42:
            print(f"    VAERS {c['vaers_id']}: {c['errors']}")

    # ==================================================================
    # Summary
    # ==================================================================
    print("\n" + "=" * 75)
    print("  SUMMARY")
    print("=" * 75)
    print(f"  WHO changes: {len(changed)} (target: 0)")

    # Brighton guidance
    bg_s6 = sum(1 for vid in brighton_cases
                if get_stage6(v42_map[vid]).get("mode") == "brighton_exit")
    print(f"  Brighton L4 guidance: {bg_s6}/{len(brighton_cases)} "
          f"({bg_s6/len(brighton_cases)*100:.0f}%)" if brighton_cases else
          "  Brighton L4 guidance: N/A")

    # Onset guidance
    on_s6 = sum(1 for vid in onset_cases
                if get_stage6(v42_map[vid]).get("mode") == "onset_unknown")
    print(f"  Onset unknown guidance: {on_s6}/{len(onset_cases)} "
          f"({on_s6/len(onset_cases)*100:.0f}%)" if onset_cases else
          "  Onset unknown guidance: N/A")

    print(f"  Errors: {len(errors_42)}")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
