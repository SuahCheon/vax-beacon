"""
Compare v4.1a vs v4.1b results.

v4.1b changes:
  - Stage 4: investigation guidance fields (additive)
  - Stage 5: investigation_context in LLM input (classify() UNCHANGED)
  - Stage 6: temporal-aware guidance, onset_unknown routing, MIS-C differentiation
  - Knowledge DB: MIS-C differentiation guide + sars_cov2_positive indicator
  - DB patch1 (from v4.1a): high_degree_av_block, conduction_delay keywords

Expected:
  - classify() unchanged → WHO changes only from DB patch1 or LLM non-determinism
  - Stage 6 quality: temporal-aware gap scaling, bridging symptom queries, no "vaccine vs viral"
"""

import json
import glob
import os
import re
import sys


def load_latest_results(pattern):
    """Load the latest results file matching a glob pattern."""
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"ERROR: No files matching {pattern}")
        sys.exit(1)
    path = files[-1]
    print(f"  Loading: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f), path


def get_who(case):
    """Extract WHO category from a case result."""
    s5 = case.get("stages", {}).get("stage5_causality", {})
    s6 = case.get("stages", {}).get("stage6_guidance", {})
    return s5.get("who_category") or s6.get("who_category", "ERROR")


def get_temporal_zone(case):
    """Extract temporal zone from Stage 4."""
    s4 = case.get("stages", {}).get("stage4_temporal", {})
    return s4.get("temporal_assessment", {}).get("temporal_zone", "N/A")


def get_days_to_onset(case):
    """Extract days_to_onset from Stage 4."""
    s4 = case.get("stages", {}).get("stage4_temporal", {})
    return s4.get("temporal_assessment", {}).get("days_to_onset")


def get_max_nci(case):
    """Extract max NCI score."""
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("max_nci_score", 0)


def get_decision_chain(case):
    """Extract decision chain from Stage 5."""
    s5 = case.get("stages", {}).get("stage5_causality", {})
    return s5.get("decision_chain", {})


def get_investigation_intensity(case):
    """Extract investigation intensity from Stage 4."""
    s4 = case.get("stages", {}).get("stage4_temporal", {})
    return s4.get("temporal_assessment", {}).get("investigation_intensity", "N/A")


def get_stage6(case):
    """Extract Stage 6 output."""
    return case.get("stages", {}).get("stage6_guidance", {})


def get_dominant_alternative(case):
    """Extract dominant alternative from Stage 3."""
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("dominant_alternative", "NONE")


def get_alternative_etiologies(case):
    """Extract alternative etiologies from Stage 3."""
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("alternative_etiologies", [])


def categorize_who_change(vid, c_a, c_b):
    """Categorize the reason for WHO classification change."""
    nci_a = get_max_nci(c_a)
    nci_b = get_max_nci(c_b)
    tz_a = get_temporal_zone(c_a)
    tz_b = get_temporal_zone(c_b)
    days_a = get_days_to_onset(c_a)
    days_b = get_days_to_onset(c_b)

    # Check DB patch1 effect: NCI change due to av_block/conduction_delay
    if nci_a != nci_b:
        # Look for high_degree_av_block or conduction_delay in Stage 3
        s3_b = c_b.get("stages", {}).get("stage3_ddx", {})
        alts_a = get_alternative_etiologies(c_a)
        alts_b = get_alternative_etiologies(c_b)

        # Simple heuristic: if NCI changed, it could be DB patch1 or LLM drift
        alt_names_a = {a.get("etiology", ""): a.get("nci_score", 0) for a in alts_a}
        alt_names_b = {a.get("etiology", ""): a.get("nci_score", 0) for a in alts_b}

        return f"NCI changed: {nci_a} -> {nci_b} (DB patch1 or LLM drift)"

    if tz_a != tz_b:
        return f"Temporal zone changed: {tz_a} -> {tz_b}"

    if days_a != days_b:
        return f"days_to_onset changed: {days_a} -> {days_b}"

    return "LLM non-determinism (same NCI, same temporal)"


def main():
    print("\n" + "=" * 70)
    print("  Vax-Beacon: v4.1a vs v4.1b Comparison")
    print("=" * 70)

    # Load results
    print("\nLoading results...")
    v41a, v41a_path = load_latest_results(
        "results/results_v41a_full_100_*.json"
    )
    v41b, v41b_path = load_latest_results(
        "results/results_v41b_full_100_*.json"
    )

    # Build lookup by VAERS_ID
    v41a_map = {c["vaers_id"]: c for c in v41a}
    v41b_map = {c["vaers_id"]: c for c in v41b}

    common_ids = sorted(set(v41a_map.keys()) & set(v41b_map.keys()))
    print(f"\n  Common cases: {len(common_ids)}")

    # ================================================================
    # 1. WHO Classification Distribution
    # ================================================================
    print("\n" + "-" * 60)
    print("  1. WHO Classification Distribution")
    print("-" * 60)
    cats_a = {}
    cats_b = {}
    for vid in common_ids:
        wa = get_who(v41a_map[vid])
        wb = get_who(v41b_map[vid])
        cats_a[wa] = cats_a.get(wa, 0) + 1
        cats_b[wb] = cats_b.get(wb, 0) + 1

    all_cats = sorted(set(list(cats_a.keys()) + list(cats_b.keys())))
    print(f"\n  {'Category':<16s} {'v4.1a':>6s} {'v4.1b':>6s} {'Delta':>6s}")
    print(f"  {'-' * 40}")
    for cat in all_cats:
        ca = cats_a.get(cat, 0)
        cb = cats_b.get(cat, 0)
        delta = cb - ca
        delta_str = f"+{delta}" if delta > 0 else str(delta) if delta < 0 else "0"
        print(f"  {cat:<16s} {ca:>6d} {cb:>6d} {delta_str:>6s}")

    # ================================================================
    # 2. Cases Where WHO Changed
    # ================================================================
    print("\n" + "-" * 60)
    print("  2. Cases Where WHO Classification Changed")
    print("-" * 60)
    changed = []
    for vid in common_ids:
        wa = get_who(v41a_map[vid])
        wb = get_who(v41b_map[vid])
        if wa != wb:
            reason = categorize_who_change(vid, v41a_map[vid], v41b_map[vid])
            changed.append({
                "vaers_id": vid,
                "v41a": wa,
                "v41b": wb,
                "nci_a": get_max_nci(v41a_map[vid]),
                "nci_b": get_max_nci(v41b_map[vid]),
                "tz_a": get_temporal_zone(v41a_map[vid]),
                "tz_b": get_temporal_zone(v41b_map[vid]),
                "reason": reason,
            })

    if changed:
        print(f"\n  {len(changed)} cases changed:\n")
        db_patch1 = 0
        llm_drift = 0
        for c in changed:
            print(f"  VAERS {c['vaers_id']}: {c['v41a']} -> {c['v41b']}")
            print(f"    NCI: {c['nci_a']} -> {c['nci_b']}, "
                  f"Temporal: {c['tz_a']} -> {c['tz_b']}")
            print(f"    Reason: {c['reason']}")
            print()
            if "DB patch1" in c["reason"]:
                db_patch1 += 1
            if "LLM" in c["reason"]:
                llm_drift += 1

        print(f"  Summary: DB patch1 effect={db_patch1}, "
              f"LLM non-determinism={llm_drift}, "
              f"total={len(changed)}")
    else:
        print("\n  No cases changed WHO classification.\n")

    # ================================================================
    # 3. NCI Score Changes
    # ================================================================
    print("\n" + "-" * 60)
    print("  3. NCI Score Changes")
    print("-" * 60)
    nci_changes = []
    for vid in common_ids:
        nci_a = get_max_nci(v41a_map[vid])
        nci_b = get_max_nci(v41b_map[vid])
        if nci_a != nci_b:
            nci_changes.append({
                "vaers_id": vid,
                "nci_a": nci_a,
                "nci_b": nci_b,
                "delta": round(nci_b - nci_a, 3),
            })

    if nci_changes:
        print(f"\n  {len(nci_changes)} cases with NCI changes:\n")
        for nc in nci_changes:
            sign = "+" if nc["delta"] > 0 else ""
            print(f"    VAERS {nc['vaers_id']}: {nc['nci_a']} -> {nc['nci_b']} "
                  f"({sign}{nc['delta']})")
    else:
        print("\n  No NCI score changes.")

    # ================================================================
    # 4. Stage 6 Quality Metrics (NEW in v4.1b)
    # ================================================================
    print("\n" + "-" * 60)
    print("  4. Stage 6 Quality Metrics (v4.1b)")
    print("-" * 60)

    # 4a. Bridging symptom query rate for BACKGROUND_RATE/UNLIKELY
    print("\n  4a. Bridging Symptom Query Rate")
    bg_unlikely_count = 0
    bridging_found = 0
    bridging_cases = []
    for vid in common_ids:
        tz = get_temporal_zone(v41b_map[vid])
        if tz in ("BACKGROUND_RATE", "UNLIKELY"):
            bg_unlikely_count += 1
            s6 = get_stage6(v41b_map[vid])
            s6_str = json.dumps(s6).lower()
            has_bridging = "bridging" in s6_str
            if has_bridging:
                bridging_found += 1
            else:
                bridging_cases.append(vid)

    if bg_unlikely_count > 0:
        rate = bridging_found / bg_unlikely_count * 100
        print(f"    BACKGROUND_RATE/UNLIKELY cases: {bg_unlikely_count}")
        print(f"    With bridging symptom query: {bridging_found} ({rate:.1f}%)")
        print(f"    Target: 100%")
        if bridging_cases:
            print(f"    MISSING bridging query: {bridging_cases}")
    else:
        print("    No BACKGROUND_RATE/UNLIKELY cases found.")

    # 4b. MRI framing: "vaccine vs viral" check
    print("\n  4b. MRI Framing Check")
    vaccine_viral_count = 0
    vaccine_viral_cases = []
    for vid in common_ids:
        s6 = get_stage6(v41b_map[vid])
        s6_str = json.dumps(s6).lower()
        if "vaccine vs viral" in s6_str or "vaccine versus viral" in s6_str:
            vaccine_viral_count += 1
            vaccine_viral_cases.append(vid)

    print(f"    'vaccine vs viral' framing instances: {vaccine_viral_count}")
    print(f"    Target: 0")
    if vaccine_viral_cases:
        print(f"    Found in: {vaccine_viral_cases}")

    # 4c. Investigation scope scaling: avg gap count by intensity
    print("\n  4c. Investigation Scope Scaling")
    intensity_gaps = {}
    for vid in common_ids:
        intensity = get_investigation_intensity(v41b_map[vid])
        if intensity == "N/A":
            continue
        s6 = get_stage6(v41b_map[vid])
        gaps = s6.get("investigative_gaps", [])
        if intensity not in intensity_gaps:
            intensity_gaps[intensity] = []
        intensity_gaps[intensity].append(len(gaps))

    for intensity in ["STANDARD", "ENHANCED", "COMPREHENSIVE"]:
        if intensity in intensity_gaps:
            vals = intensity_gaps[intensity]
            avg = sum(vals) / len(vals) if vals else 0
            print(f"    {intensity}: avg={avg:.1f} gaps, "
                  f"n={len(vals)}, range=[{min(vals)}-{max(vals)}]")

    if all(k in intensity_gaps for k in ["STANDARD", "ENHANCED", "COMPREHENSIVE"]):
        avgs = {k: sum(v) / len(v) for k, v in intensity_gaps.items()}
        if avgs["STANDARD"] < avgs["ENHANCED"] < avgs["COMPREHENSIVE"]:
            print("    Scaling: STANDARD < ENHANCED < COMPREHENSIVE OK")
        else:
            print(f"    WARNING: Scaling not monotonic - "
                  f"S={avgs['STANDARD']:.1f}, E={avgs['ENHANCED']:.1f}, "
                  f"C={avgs['COMPREHENSIVE']:.1f}")

    # 4d. MIS-C cases: nucleocapsid antibody in recommendations
    print("\n  4d. MIS-C / COVID-19 Related: Nucleocapsid Antibody")
    misc_suspects = 0
    nucleocapsid_found = 0
    misc_details = []
    for vid in common_ids:
        dominant = get_dominant_alternative(v41b_map[vid])
        alts = get_alternative_etiologies(v41b_map[vid])
        is_covid = ("covid" in dominant.lower() or "mis" in dominant.lower()
                    if dominant != "NONE" else False)
        if not is_covid:
            for a in alts:
                etio = a.get("etiology", "").lower()
                if "covid" in etio or "mis" in etio:
                    is_covid = True
                    break

        if is_covid:
            misc_suspects += 1
            s6 = get_stage6(v41b_map[vid])
            s6_str = json.dumps(s6).lower()
            has_nucleo = "nucleocapsid" in s6_str
            if has_nucleo:
                nucleocapsid_found += 1
            misc_details.append({
                "vaers_id": vid,
                "dominant": dominant,
                "nucleocapsid_recommended": has_nucleo,
            })

    if misc_suspects > 0:
        rate = nucleocapsid_found / misc_suspects * 100
        print(f"    MIS-C/COVID suspects: {misc_suspects}")
        print(f"    With nucleocapsid recommendation: {nucleocapsid_found} ({rate:.1f}%)")
        print(f"    Target: 100%")
        for d in misc_details:
            status = "OK" if d["nucleocapsid_recommended"] else "MISSING"
            print(f"      VAERS {d['vaers_id']}: dominant={d['dominant']} {status}")
    else:
        print("    No MIS-C/COVID suspected cases found.")

    # 4e. Onset unknown cases: onset_verification field
    print("\n  4e. Onset Unknown: onset_verification Field")
    onset_unknown_count = 0
    onset_verify_found = 0
    onset_details = []
    for vid in common_ids:
        dc = get_decision_chain(v41b_map[vid])
        if dc.get("onset_unknown", False):
            onset_unknown_count += 1
            s6 = get_stage6(v41b_map[vid])
            has_verify = "onset_verification" in s6
            has_possible = "possible_categories_once_onset_known" in s6
            if has_verify:
                onset_verify_found += 1
            onset_details.append({
                "vaers_id": vid,
                "has_onset_verification": has_verify,
                "has_possible_categories": has_possible,
            })

    if onset_unknown_count > 0:
        rate = onset_verify_found / onset_unknown_count * 100
        print(f"    Onset unknown cases: {onset_unknown_count}")
        print(f"    With onset_verification: {onset_verify_found} ({rate:.1f}%)")
        print(f"    Target: 100%")
        for d in onset_details:
            v_status = "OK" if d["has_onset_verification"] else "MISSING"
            p_status = "OK" if d["has_possible_categories"] else "MISSING"
            print(f"      VAERS {d['vaers_id']}: verification={v_status}, "
                  f"possible_categories={p_status}")
    else:
        print("    No onset unknown cases found.")

    # ================================================================
    # 5. Error Summary
    # ================================================================
    print("\n" + "-" * 60)
    print("  5. Error Summary")
    print("-" * 60)
    errors_a = sum(len(c.get("errors", [])) for c in v41a)
    errors_b = sum(len(c.get("errors", [])) for c in v41b)
    print(f"\n  v4.1a errors: {errors_a}")
    print(f"  v4.1b errors: {errors_b}")

    if errors_b > 0:
        print("\n  v4.1b error details:")
        for c in v41b:
            errs = c.get("errors", [])
            if errs:
                print(f"    VAERS {c['vaers_id']}: {errs}")

    print("\n" + "=" * 70)
    print("  Comparison complete.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
