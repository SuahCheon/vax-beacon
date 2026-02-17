"""
Compare v4.0 vs v4.1a results.
v4.1a changes:
  - Stage 1: onset extraction rules + onset_approximate field
  - Stage 5: UNKNOWN onset -> Unclassifiable (Rule 2.5)
  - Stage 4: APPROXIMATE_ONSET flag

Expected:
  - Cases with known onset -> identical classification
  - Cases with UNKNOWN onset -> may change from B2/other to Unclassifiable
  - Cases with NCI >= 0.7 + UNKNOWN onset -> still C (Rule 2 before Rule 2.5)
"""

import json
import glob
import os
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


def get_onset_approximate(case):
    """Extract onset_approximate from Stage 1."""
    s1 = case.get("stages", {}).get("stage1_icsr", {})
    return s1.get("event", {}).get("onset_approximate")


def get_max_nci(case):
    """Extract max NCI score."""
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("max_nci_score", 0)


def get_decision_chain(case):
    """Extract decision chain from Stage 5."""
    s5 = case.get("stages", {}).get("stage5_causality", {})
    return s5.get("decision_chain", {})


def main():
    print("\n" + "=" * 70)
    print("  Vax-Beacon: v4.0 vs v4.1a Comparison")
    print("=" * 70)

    # Load results
    print("\nLoading results...")
    v40, v40_path = load_latest_results("results/results_v4_full_100_*.json")
    v41a, v41a_path = load_latest_results("results/results_v41a_full_100_*.json")

    # Build lookup by VAERS_ID
    v40_map = {c["vaers_id"]: c for c in v40}
    v41a_map = {c["vaers_id"]: c for c in v41a}

    common_ids = sorted(set(v40_map.keys()) & set(v41a_map.keys()))
    print(f"\n  Common cases: {len(common_ids)}")

    # --- WHO Distribution ---
    print("\n" + "-" * 60)
    print("  WHO Classification Distribution")
    print("-" * 60)
    cats_v40 = {}
    cats_v41a = {}
    for vid in common_ids:
        w40 = get_who(v40_map[vid])
        w41a = get_who(v41a_map[vid])
        cats_v40[w40] = cats_v40.get(w40, 0) + 1
        cats_v41a[w41a] = cats_v41a.get(w41a, 0) + 1

    all_cats = sorted(set(list(cats_v40.keys()) + list(cats_v41a.keys())))
    print(f"\n  {'Category':<16s} {'v4.0':>6s} {'v4.1a':>6s} {'Delta':>6s}")
    print(f"  {'-'*40}")
    for cat in all_cats:
        c40 = cats_v40.get(cat, 0)
        c41a = cats_v41a.get(cat, 0)
        delta = c41a - c40
        delta_str = f"+{delta}" if delta > 0 else str(delta) if delta < 0 else "0"
        print(f"  {cat:<16s} {c40:>6d} {c41a:>6d} {delta_str:>6s}")

    # --- Changed Cases ---
    print("\n" + "-" * 60)
    print("  Cases Where WHO Classification Changed")
    print("-" * 60)
    changed = []
    for vid in common_ids:
        w40 = get_who(v40_map[vid])
        w41a = get_who(v41a_map[vid])
        if w40 != w41a:
            tz40 = get_temporal_zone(v40_map[vid])
            tz41a = get_temporal_zone(v41a_map[vid])
            days40 = get_days_to_onset(v40_map[vid])
            days41a = get_days_to_onset(v41a_map[vid])
            nci40 = get_max_nci(v40_map[vid])
            nci41a = get_max_nci(v41a_map[vid])
            dc41a = get_decision_chain(v41a_map[vid])
            onset_unknown = dc41a.get("onset_unknown", False)

            reason = "UNKNOWN"
            if onset_unknown:
                reason = "UNKNOWN onset -> Unclassifiable (Rule 2.5)"
            elif tz40 != tz41a:
                reason = f"Temporal zone changed: {tz40} -> {tz41a}"
            elif days40 != days41a:
                reason = f"days_to_onset changed: {days40} -> {days41a}"
            elif nci40 != nci41a:
                reason = f"NCI changed: {nci40} -> {nci41a}"

            changed.append({
                "vaers_id": vid,
                "v40": w40,
                "v41a": w41a,
                "tz_v40": tz40,
                "tz_v41a": tz41a,
                "days_v40": days40,
                "days_v41a": days41a,
                "nci_v40": nci40,
                "nci_v41a": nci41a,
                "onset_unknown": onset_unknown,
                "reason": reason,
            })

    if changed:
        print(f"\n  {len(changed)} cases changed:\n")
        for c in changed:
            print(f"  VAERS {c['vaers_id']}: {c['v40']} -> {c['v41a']}")
            print(f"    Temporal: {c['tz_v40']} -> {c['tz_v41a']}, "
                  f"Days: {c['days_v40']} -> {c['days_v41a']}, "
                  f"NCI: {c['nci_v40']} -> {c['nci_v41a']}")
            print(f"    Reason: {c['reason']}")
            print()
    else:
        print("\n  No cases changed WHO classification.\n")

    # --- Onset Extraction Improvement ---
    print("-" * 60)
    print("  Onset Extraction Improvement (v4.0 vs v4.1a)")
    print("-" * 60)
    improved = []
    unknown_v40 = 0
    unknown_v41a = 0
    approximate_count = 0

    for vid in common_ids:
        days40 = get_days_to_onset(v40_map[vid])
        days41a = get_days_to_onset(v41a_map[vid])
        tz40 = get_temporal_zone(v40_map[vid])
        tz41a = get_temporal_zone(v41a_map[vid])
        approx = get_onset_approximate(v41a_map[vid])

        if tz40 == "UNKNOWN":
            unknown_v40 += 1
        if tz41a == "UNKNOWN":
            unknown_v41a += 1
        if approx is True:
            approximate_count += 1

        # Onset was null in v4.0 but populated in v4.1a
        if days40 is None and days41a is not None:
            improved.append({
                "vaers_id": vid,
                "days_v41a": days41a,
                "approximate": approx,
                "tz_change": f"{tz40} -> {tz41a}",
            })

    print(f"\n  UNKNOWN onset cases: v4.0={unknown_v40}, v4.1a={unknown_v41a} "
          f"(delta={unknown_v41a - unknown_v40})")
    print(f"  onset_approximate=true cases in v4.1a: {approximate_count}")

    if improved:
        print(f"\n  {len(improved)} cases with newly extracted onset:")
        for imp in improved:
            print(f"    VAERS {imp['vaers_id']}: days={imp['days_v41a']}, "
                  f"approx={imp['approximate']}, zone: {imp['tz_change']}")
    else:
        print("\n  No new onset extractions (onset extraction was already handled by VAERS fields).")

    # --- Known Onset Consistency ---
    print("\n" + "-" * 60)
    print("  Known Onset Cases: Classification Consistency Check")
    print("-" * 60)
    known_onset_diffs = []
    for vid in common_ids:
        tz40 = get_temporal_zone(v40_map[vid])
        tz41a = get_temporal_zone(v41a_map[vid])
        # Skip early exits (no Stage 4 data) and UNKNOWN cases
        if tz40 in ("N/A", "UNKNOWN") or tz41a in ("N/A", "UNKNOWN"):
            continue
        w40 = get_who(v40_map[vid])
        w41a = get_who(v41a_map[vid])
        if w40 != w41a:
            known_onset_diffs.append({
                "vaers_id": vid,
                "v40": w40,
                "v41a": w41a,
                "tz": tz40,
            })

    if known_onset_diffs:
        print(f"\n  WARNING: {len(known_onset_diffs)} cases with known onset changed classification:")
        for d in known_onset_diffs:
            print(f"    VAERS {d['vaers_id']}: {d['v40']} -> {d['v41a']} (zone={d['tz']})")
    else:
        print("\n  ALL cases with known onset have IDENTICAL classification to v4.0.")

    # --- Error Check ---
    print("\n" + "-" * 60)
    print("  Error Summary")
    print("-" * 60)
    errors_v40 = sum(len(c.get("errors", [])) for c in v40)
    errors_v41a = sum(len(c.get("errors", [])) for c in v41a)
    print(f"\n  v4.0 errors: {errors_v40}")
    print(f"  v4.1a errors: {errors_v41a}")

    print("\n" + "=" * 70)
    print("  Comparison complete.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
