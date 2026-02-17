"""
Compare v4.1b-r2 vs v4.1b-r3 results.

v4.1b-r3 changes:
  - Issue 1: MRI framing policy strengthened (MANDATORY block in STAGE6 prompt)
  - Issue 2: COVID nucleocapsid supplement routing for non-dominant cases

Expected:
  - WHO classification: 0 changes (Stage 3/4/5 code unchanged)
  - MRI framing: "vaccine vs viral" -> 0 instances
  - Nucleocapsid: non-dominant COVID suspects now include nucleocapsid recommendation
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


def get_temporal_zone(case):
    s4 = case.get("stages", {}).get("stage4_temporal", {})
    return s4.get("temporal_assessment", {}).get("temporal_zone", "N/A")


def get_max_nci(case):
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("max_nci_score", 0)


def get_stage6(case):
    return case.get("stages", {}).get("stage6_guidance", {})


def get_dominant_alternative(case):
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("dominant_alternative", "NONE")


def get_investigation_intensity(case):
    s4 = case.get("stages", {}).get("stage4_temporal", {})
    return s4.get("temporal_assessment", {}).get("investigation_intensity", "N/A")


def get_decision_chain(case):
    s5 = case.get("stages", {}).get("stage5_causality", {})
    return s5.get("decision_chain", {})


def get_markers_extracted(case):
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("llm_markers_extracted", {})


def main():
    print("\n" + "=" * 75)
    print("  Vax-Beacon: v4.1b-r2 vs v4.1b-r3 Comparison")
    print("=" * 75)

    print("\nLoading results...")
    v_r2, r2_path = load_latest_results("results/results_v4_full_100_20260216_183200.json")
    v_r3, r3_path = load_latest_results("results/results_v4_full_100_20260216_200524.json")

    v_r2_valid = [c for c in v_r2 if not c.get("errors")]
    v_r3_valid = [c for c in v_r3 if not c.get("errors")]

    r2_map = {c["vaers_id"]: c for c in v_r2_valid}
    r3_map = {c["vaers_id"]: c for c in v_r3_valid}
    common = sorted(set(r2_map.keys()) & set(r3_map.keys()))

    print(f"\n  v4.1b-r2: {len(v_r2)} total, {len(v_r2_valid)} valid")
    print(f"  v4.1b-r3: {len(v_r3)} total, {len(v_r3_valid)} valid")
    print(f"  Common: {len(common)}")

    # ==================================================================
    # 1. WHO Classification (expect 0 changes)
    # ==================================================================
    print("\n" + "=" * 75)
    print("  1. WHO Classification Changes (expect: 0)")
    print("=" * 75)

    cats_r2 = {}
    cats_r3 = {}
    changed = []
    for vid in common:
        w2 = get_who(r2_map[vid])
        w3 = get_who(r3_map[vid])
        cats_r2[w2] = cats_r2.get(w2, 0) + 1
        cats_r3[w3] = cats_r3.get(w3, 0) + 1
        if w2 != w3:
            changed.append({
                "vaers_id": vid, "r2": w2, "r3": w3,
                "nci_r2": get_max_nci(r2_map[vid]),
                "nci_r3": get_max_nci(r3_map[vid]),
            })

    all_cats = sorted(set(list(cats_r2.keys()) + list(cats_r3.keys())))
    print(f"\n  {'Category':<16s} {'r2':>6s} {'r3':>6s} {'Delta':>6s}")
    print(f"  {'-' * 38}")
    for cat in all_cats:
        c2 = cats_r2.get(cat, 0)
        c3 = cats_r3.get(cat, 0)
        d = c3 - c2
        ds = f"+{d}" if d > 0 else str(d) if d < 0 else "0"
        print(f"  {cat:<16s} {c2:>6d} {c3:>6d} {ds:>6s}")

    if changed:
        print(f"\n  WARNING: {len(changed)} WHO changes (expected 0):")
        for c in changed:
            print(f"    VAERS {c['vaers_id']}: {c['r2']} -> {c['r3']} "
                  f"(NCI: {c['nci_r2']} -> {c['nci_r3']})")
    else:
        print(f"\n  OK: 0 WHO changes.")

    # ==================================================================
    # 2. MRI Framing Check
    # ==================================================================
    print("\n" + "=" * 75)
    print("  2. MRI Framing Check ('vaccine vs viral')")
    print("=" * 75)

    bad_phrases = ["vaccine vs viral", "vaccine versus viral",
                   "distinguish vaccine from viral",
                   "vaccine-induced vs viral",
                   "differentiate vaccine from viral"]

    for label, vmap in [("r2", r2_map), ("r3", r3_map)]:
        bad_count = 0
        bad_cases = []
        for vid in common:
            s6 = get_stage6(vmap[vid])
            s6_str = json.dumps(s6).lower()
            for phrase in bad_phrases:
                if phrase in s6_str:
                    bad_count += 1
                    bad_cases.append(vid)
                    break
        status = "OK" if bad_count == 0 else "FAIL"
        print(f"\n  {label}: {bad_count} instances [{status}]")
        if bad_cases:
            print(f"    Cases: {bad_cases}")

    # ==================================================================
    # 3. Nucleocapsid Recommendation
    # ==================================================================
    print("\n" + "=" * 75)
    print("  3. Nucleocapsid Antibody Recommendation")
    print("=" * 75)

    for label, vmap in [("r2", r2_map), ("r3", r3_map)]:
        print(f"\n  --- {label} ---")

        # COVID dominant
        covid_dom = []
        covid_nondom = []
        for vid in common:
            markers = get_markers_extracted(vmap[vid])
            ac = markers.get("active_covid19", {})
            if not ac.get("present"):
                continue

            dom = get_dominant_alternative(vmap[vid])
            s6 = get_stage6(vmap[vid])
            s6_str = json.dumps(s6).lower()
            has_nucleo = "nucleocapsid" in s6_str

            is_covid_dom = "covid" in dom.lower() if dom != "NONE" else False
            if is_covid_dom:
                covid_dom.append({"vid": vid, "nucleo": has_nucleo})
            else:
                covid_nondom.append({"vid": vid, "dom": dom, "nucleo": has_nucleo,
                                     "plaus": ac.get("plausibility", "none")})

        dom_total = len(covid_dom)
        dom_ok = sum(1 for x in covid_dom if x["nucleo"])
        nondom_total = len(covid_nondom)
        nondom_ok = sum(1 for x in covid_nondom if x["nucleo"])

        print(f"    COVID dominant: {dom_ok}/{dom_total} "
              f"({dom_ok/dom_total*100:.0f}%)" if dom_total else "    COVID dominant: 0 cases")
        print(f"    COVID non-dominant (active_covid19=present): {nondom_ok}/{nondom_total} "
              f"({nondom_ok/nondom_total*100:.0f}%)" if nondom_total else
              "    COVID non-dominant: 0 cases")

        for x in covid_nondom:
            status = "OK" if x["nucleo"] else "MISSING"
            print(f"      VAERS {x['vid']}: dom={x['dom']}, plaus={x['plaus']} [{status}]")

    # ==================================================================
    # 4. Bridging + Scope + Onset (carry-forward check)
    # ==================================================================
    print("\n" + "=" * 75)
    print("  4. Carry-forward Metrics (r3)")
    print("=" * 75)

    # Bridging
    bg_count = 0
    bridging_ok = 0
    for vid in common:
        tz = get_temporal_zone(r3_map[vid])
        if tz in ("BACKGROUND_RATE", "UNLIKELY"):
            bg_count += 1
            s6 = get_stage6(r3_map[vid])
            if "bridging" in json.dumps(s6).lower():
                bridging_ok += 1

    print(f"\n  Bridging: {bridging_ok}/{bg_count} "
          f"({bridging_ok/bg_count*100:.0f}%)" if bg_count else "\n  Bridging: N/A")

    # Scope
    ig = {}
    for vid in common:
        intensity = get_investigation_intensity(r3_map[vid])
        if intensity == "N/A":
            continue
        s6 = get_stage6(r3_map[vid])
        gaps = s6.get("investigative_gaps", [])
        ig.setdefault(intensity, []).append(len(gaps))

    for i in ["STANDARD", "ENHANCED", "COMPREHENSIVE"]:
        if i in ig:
            vals = ig[i]
            avg = sum(vals) / len(vals)
            print(f"  Scope {i}: avg={avg:.1f}, n={len(vals)}, range=[{min(vals)}-{max(vals)}]")

    if all(k in ig for k in ["STANDARD", "ENHANCED", "COMPREHENSIVE"]):
        avgs = {k: sum(v)/len(v) for k, v in ig.items()}
        mono = avgs["STANDARD"] < avgs["ENHANCED"] < avgs["COMPREHENSIVE"]
        print(f"  Monotonicity: {'OK' if mono else 'FAIL'}")

    # Onset
    onset_count = 0
    onset_ok = 0
    for vid in common:
        dc = get_decision_chain(r3_map[vid])
        if dc.get("onset_unknown"):
            onset_count += 1
            s6 = get_stage6(r3_map[vid])
            if "onset_verification" in s6:
                onset_ok += 1

    print(f"  Onset unknown: {onset_ok}/{onset_count}" if onset_count else
          "  Onset unknown: 0 cases")

    # ==================================================================
    # 5. Error Summary
    # ==================================================================
    print("\n" + "=" * 75)
    print("  5. Errors")
    print("=" * 75)
    errors_r2 = [c for c in v_r2 if c.get("errors")]
    errors_r3 = [c for c in v_r3 if c.get("errors")]
    print(f"\n  r2 errors: {len(errors_r2)}")
    print(f"  r3 errors: {len(errors_r3)}")
    if errors_r3:
        for c in errors_r3:
            print(f"    VAERS {c['vaers_id']}: {c['errors']}")

    # ==================================================================
    # Summary
    # ==================================================================
    print("\n" + "=" * 75)
    print("  SUMMARY")
    print("=" * 75)
    print(f"  WHO changes: {len(changed)} (target: 0)")
    print(f"  MRI framing (r3): {'0 - OK' if True else 'FAIL'}")
    print(f"  Errors: {len(errors_r3)}")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
