"""
Vax-Beacon: Three-Way Comparison Script (v3.0 vs v3.1 vs v4)
================================================================
Compares classification distributions, marker flip counts, NCI drift,
and Stage 6 specificity across three pipeline versions.

Usage:
  python compare_v30_v31_v4.py                          # Auto-detect latest v4 results
  python compare_v30_v31_v4.py --v4 results/results_v4_full_100_XXXXXX.json
"""

import argparse
import json
import os
import sys
from collections import Counter

# Windows UTF-8 console fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


# ── File paths ───────────────────────────────────────────────────────────────
V30_PATH = "results/results_v30_final.json.json"
V31_PATH = "results/results_v31.json.json"


def find_latest_v4_results():
    """Auto-detect the latest v4 full_100 results file."""
    results_dir = "results"
    candidates = []
    for f in os.listdir(results_dir):
        if f.startswith("results_v4_full_100_") and f.endswith(".json"):
            candidates.append(os.path.join(results_dir, f))
    if not candidates:
        # Fallback: any v4 results
        for f in os.listdir(results_dir):
            if "v4" in f and f.endswith(".json") and "summary" not in f:
                candidates.append(os.path.join(results_dir, f))
    if not candidates:
        return None
    return sorted(candidates)[-1]  # Latest by filename (timestamp)


def load_results(path):
    """Load results JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Extraction helpers ───────────────────────────────────────────────────────

def get_who_category(case):
    """Extract WHO category from a case result."""
    s5 = case.get("stages", {}).get("stage5_causality", {})
    cat = s5.get("who_category")
    if cat:
        return cat
    s6 = case.get("stages", {}).get("stage6_guidance", {})
    return s6.get("who_category", "Unclassifiable")


def get_max_nci(case):
    """Extract max NCI score."""
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("max_nci_score")


def get_dominant(case):
    """Extract dominant alternative etiology."""
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("dominant_alternative", "N/A")


def get_error_count(case):
    """Extract error count."""
    return len(case.get("errors", []))


def get_markers(case):
    """Extract present marker names from Stage 3 nci_detailed subtypes.

    Markers are stored as:
      markers_passed:   list of {"marker": name, "weight": ..., "gate": "PASSED ...", ...}
      markers_filtered: list of {"marker": name, "weight_blocked": ..., "gate": "FILTERED ...", ...}
    Both represent markers judged as *present* by the LLM (passed = contributed to NCI,
    filtered = present but gated out due to plausibility/acuity).
    markers_absent is a flat list of names (not present).
    """
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    nci_detailed = s3.get("nci_detailed", {})
    present = set()
    for subtype_key, subtype_data in nci_detailed.items():
        if not isinstance(subtype_data, dict):
            continue
        # markers_passed: markers that contributed to NCI score
        for m in subtype_data.get("markers_passed", []):
            if isinstance(m, dict):
                name = m.get("marker", "")
                if name:
                    present.add(name)
            elif isinstance(m, str):
                present.add(m)
        # markers_filtered: present but gated out (still "present" in the clinical sense)
        for m in subtype_data.get("markers_filtered", []):
            if isinstance(m, dict):
                name = m.get("marker", "")
                if name:
                    present.add(name)
            elif isinstance(m, str):
                present.add(m)
    return present


def get_stage6_text(case):
    """Extract Stage 6 guidance as text for keyword search."""
    s6 = case.get("stages", {}).get("stage6_guidance", {})
    return json.dumps(s6, ensure_ascii=False).lower()


def build_case_map(results):
    """Build vaers_id → case dict."""
    return {r["vaers_id"]: r for r in results}


# ── Comparison functions ─────────────────────────────────────────────────────

def compare_who_distribution(v30, v31, v4):
    """Compare WHO category distributions across versions."""
    print("\n" + "=" * 80)
    print("  1. WHO CATEGORY DISTRIBUTION")
    print("=" * 80)

    cats_30 = Counter(get_who_category(r) for r in v30)
    cats_31 = Counter(get_who_category(r) for r in v31)
    cats_4 = Counter(get_who_category(r) for r in v4)

    all_cats = sorted(set(cats_30.keys()) | set(cats_31.keys()) | set(cats_4.keys()))

    print(f"\n  {'Category':<18} {'v3.0':>8} {'v3.1':>8} {'v4':>8}  {'v3.0→v3.1':>10} {'v3.1→v4':>10}")
    print(f"  {'-'*18} {'-'*8} {'-'*8} {'-'*8}  {'-'*10} {'-'*10}")

    for cat in all_cats:
        c30 = cats_30.get(cat, 0)
        c31 = cats_31.get(cat, 0)
        c4 = cats_4.get(cat, 0)
        delta_31 = c31 - c30
        delta_4 = c4 - c31
        d31_str = f"{delta_31:+d}" if delta_31 != 0 else "-"
        d4_str = f"{delta_4:+d}" if delta_4 != 0 else "-"
        print(f"  {cat:<18} {c30:>8} {c31:>8} {c4:>8}  {d31_str:>10} {d4_str:>10}")

    print(f"  {'-'*18} {'-'*8} {'-'*8} {'-'*8}")
    print(f"  {'TOTAL':<18} {len(v30):>8} {len(v31):>8} {len(v4):>8}")


def compare_classification_changes(v30, v31, v4):
    """Show per-case classification changes between versions."""
    print("\n" + "=" * 80)
    print("  2. PER-CASE CLASSIFICATION CHANGES")
    print("=" * 80)

    map30 = build_case_map(v30)
    map31 = build_case_map(v31)
    map4 = build_case_map(v4)

    common_ids = sorted(set(map30.keys()) & set(map31.keys()) & set(map4.keys()))

    changes_31_to_4 = []
    changes_30_to_4 = []

    for vid in common_ids:
        cat30 = get_who_category(map30[vid])
        cat31 = get_who_category(map31[vid])
        cat4 = get_who_category(map4[vid])
        if cat31 != cat4:
            changes_31_to_4.append((vid, cat30, cat31, cat4))
        if cat30 != cat4:
            changes_30_to_4.append((vid, cat30, cat31, cat4))

    print(f"\n  v3.1 → v4 classification changes: {len(changes_31_to_4)} cases")
    if changes_31_to_4:
        print(f"  {'VAERS_ID':<12} {'v3.0':>8} {'v3.1':>8} {'v4':>8}  {'Change':>14}")
        print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*8}  {'-'*14}")
        for vid, c30, c31, c4 in changes_31_to_4:
            print(f"  {vid:<12} {c30:>8} {c31:>8} {c4:>8}  {c31}→{c4}")

    print(f"\n  v3.0 → v4 classification changes: {len(changes_30_to_4)} cases")
    if changes_30_to_4:
        print(f"  {'VAERS_ID':<12} {'v3.0':>8} {'v3.1':>8} {'v4':>8}  {'Change':>14}")
        print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*8}  {'-'*14}")
        for vid, c30, c31, c4 in changes_30_to_4:
            print(f"  {vid:<12} {c30:>8} {c31:>8} {c4:>8}  {c30}→{c4}")


def compare_nci_drift(v30, v31, v4):
    """Compare NCI score drift between versions."""
    print("\n" + "=" * 80)
    print("  3. NCI SCORE DRIFT ANALYSIS")
    print("=" * 80)

    map30 = build_case_map(v30)
    map31 = build_case_map(v31)
    map4 = build_case_map(v4)

    common_ids = sorted(set(map30.keys()) & set(map31.keys()) & set(map4.keys()))

    drift_cases = []
    for vid in common_ids:
        nci30 = get_max_nci(map30[vid])
        nci31 = get_max_nci(map31[vid])
        nci4 = get_max_nci(map4[vid])
        if nci30 is None or nci31 is None or nci4 is None:
            continue
        delta_31 = abs(nci31 - nci30)
        delta_4 = abs(nci4 - nci31)
        delta_total = abs(nci4 - nci30)
        if delta_31 >= 0.10 or delta_4 >= 0.10:
            drift_cases.append((vid, nci30, nci31, nci4, delta_31, delta_4))

    print(f"\n  Cases with NCI drift >= 0.10 between any version pair: {len(drift_cases)}")
    if drift_cases:
        print(f"\n  {'VAERS_ID':<12} {'NCI_v30':>8} {'NCI_v31':>8} {'NCI_v4':>8}  {'|v30-v31|':>10} {'|v31-v4|':>10}")
        print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*8}  {'-'*10} {'-'*10}")
        for vid, n30, n31, n4, d31, d4 in sorted(drift_cases, key=lambda x: -max(x[4], x[5])):
            flag_31 = " ***" if d31 >= 0.15 else ""
            flag_4 = " ***" if d4 >= 0.15 else ""
            print(f"  {vid:<12} {n30:>8.2f} {n31:>8.2f} {n4:>8.2f}  {d31:>10.2f}{flag_31} {d4:>10.2f}{flag_4}")
        print(f"\n  *** = |delta| >= 0.15 (significant drift)")

    # Summary stats
    all_deltas_30_31 = []
    all_deltas_31_4 = []
    for vid in common_ids:
        nci30 = get_max_nci(map30[vid])
        nci31 = get_max_nci(map31[vid])
        nci4 = get_max_nci(map4[vid])
        if nci30 is not None and nci31 is not None:
            all_deltas_30_31.append(abs(nci31 - nci30))
        if nci31 is not None and nci4 is not None:
            all_deltas_31_4.append(abs(nci4 - nci31))

    if all_deltas_30_31:
        sig_30_31 = sum(1 for d in all_deltas_30_31 if d >= 0.15)
        print(f"\n  v3.0→v3.1: mean |delta|={sum(all_deltas_30_31)/len(all_deltas_30_31):.4f}, "
              f"max={max(all_deltas_30_31):.2f}, significant(>=0.15)={sig_30_31}")
    if all_deltas_31_4:
        sig_31_4 = sum(1 for d in all_deltas_31_4 if d >= 0.15)
        print(f"  v3.1→v4:   mean |delta|={sum(all_deltas_31_4)/len(all_deltas_31_4):.4f}, "
              f"max={max(all_deltas_31_4):.2f}, significant(>=0.15)={sig_31_4}")


def compare_marker_flips(v31, v4):
    """Compare marker flips between v3.1 and v4 (the core reproducibility metric)."""
    print("\n" + "=" * 80)
    print("  4. MARKER FLIP ANALYSIS (v3.1 → v4)")
    print("=" * 80)

    map31 = build_case_map(v31)
    map4 = build_case_map(v4)

    common_ids = sorted(set(map31.keys()) & set(map4.keys()))

    total_flips = 0
    cases_with_flips = 0
    flip_counter = Counter()  # marker_name → flip count

    for vid in common_ids:
        markers31 = get_markers(map31[vid])
        markers4 = get_markers(map4[vid])
        # Flips = markers that changed present state
        gained = markers4 - markers31  # present in v4, absent in v3.1
        lost = markers31 - markers4    # present in v3.1, absent in v4
        flips = gained | lost
        if flips:
            cases_with_flips += 1
            total_flips += len(flips)
            for m in gained:
                flip_counter[f"+{m}"] += 1
            for m in lost:
                flip_counter[f"-{m}"] += 1

    print(f"\n  Total marker flips: {total_flips}")
    print(f"  Cases with at least 1 flip: {cases_with_flips}/{len(common_ids)}")

    if flip_counter:
        print(f"\n  Top marker flips (+ = gained present, - = lost present):")
        print(f"  {'Marker':<45} {'Count':>6}")
        print(f"  {'-'*45} {'-'*6}")
        for marker, count in flip_counter.most_common(20):
            print(f"  {marker:<45} {count:>6}")


def compare_dominant_alternatives(v30, v31, v4):
    """Compare dominant alternative etiology distributions."""
    print("\n" + "=" * 80)
    print("  5. DOMINANT ALTERNATIVE ETIOLOGY DISTRIBUTION")
    print("=" * 80)

    dom30 = Counter(get_dominant(r) for r in v30)
    dom31 = Counter(get_dominant(r) for r in v31)
    dom4 = Counter(get_dominant(r) for r in v4)

    all_doms = sorted(set(dom30.keys()) | set(dom31.keys()) | set(dom4.keys()))

    print(f"\n  {'Dominant Alternative':<42} {'v3.0':>6} {'v3.1':>6} {'v4':>6}")
    print(f"  {'-'*42} {'-'*6} {'-'*6} {'-'*6}")
    for dom in all_doms:
        c30 = dom30.get(dom, 0)
        c31 = dom31.get(dom, 0)
        c4 = dom4.get(dom, 0)
        print(f"  {dom:<42} {c30:>6} {c31:>6} {c4:>6}")


def compare_stage6_specificity(v30, v31, v4):
    """Compare Stage 6 specificity: EMB, viral panel, Lake Louise output rates."""
    print("\n" + "=" * 80)
    print("  6. STAGE 6 INVESTIGATION SPECIFICITY")
    print("=" * 80)

    keywords = {
        "EMB / Biopsy": ["endomyocardial biopsy", "emb", "biopsy"],
        "Viral Panel/PCR": ["viral panel", "viral pcr", "pcr testing", "viral serology"],
        "Lake Louise / CMR": ["lake louise", "cardiac mri", "cardiac magnetic", "cmr criteria"],
        "Autoimmune Panel": ["ana", "anti-dsdna", "autoimmune panel", "autoimmune serol"],
        "Troponin": ["troponin"],
        "Echocardiography": ["echocardiograph", "echo assessment"],
    }

    results = {}
    for label, kws in keywords.items():
        counts = {}
        for name, dataset in [("v3.0", v30), ("v3.1", v31), ("v4", v4)]:
            # Only count non-early-exit cases
            non_exit = [r for r in dataset if not r.get("early_exit")]
            total = len(non_exit)
            hit = 0
            for r in non_exit:
                text = get_stage6_text(r)
                if any(kw in text for kw in kws):
                    hit += 1
            counts[name] = (hit, total)
        results[label] = counts

    print(f"\n  {'Investigation':<25} {'v3.0':>12} {'v3.1':>12} {'v4':>12}")
    print(f"  {'-'*25} {'-'*12} {'-'*12} {'-'*12}")
    for label, counts in results.items():
        strs = {}
        for name in ["v3.0", "v3.1", "v4"]:
            hit, total = counts[name]
            pct = hit / max(total, 1) * 100
            strs[name] = f"{hit}/{total} ({pct:.0f}%)"
        print(f"  {label:<25} {strs['v3.0']:>12} {strs['v3.1']:>12} {strs['v4']:>12}")


def compare_error_rates(v30, v31, v4):
    """Compare error rates across versions."""
    print("\n" + "=" * 80)
    print("  7. ERROR RATES")
    print("=" * 80)

    def error_stats(data, name):
        total_errors = sum(get_error_count(r) for r in data)
        cases_with_errors = sum(1 for r in data if get_error_count(r) > 0)
        return total_errors, cases_with_errors

    e30_total, e30_cases = error_stats(v30, "v3.0")
    e31_total, e31_cases = error_stats(v31, "v3.1")
    e4_total, e4_cases = error_stats(v4, "v4")

    print(f"\n  {'Metric':<30} {'v3.0':>8} {'v3.1':>8} {'v4':>8}")
    print(f"  {'-'*30} {'-'*8} {'-'*8} {'-'*8}")
    print(f"  {'Total errors':<30} {e30_total:>8} {e31_total:>8} {e4_total:>8}")
    print(f"  {'Cases with errors':<30} {e30_cases:>8} {e31_cases:>8} {e4_cases:>8}")
    print(f"  {'Total cases':<30} {len(v30):>8} {len(v31):>8} {len(v4):>8}")


def compare_timing(v30, v31, v4):
    """Compare processing times across versions."""
    print("\n" + "=" * 80)
    print("  8. PROCESSING TIME")
    print("=" * 80)

    def timing_stats(data):
        times = [r.get("processing_time", {}).get("total", 0) for r in data]
        full = [t for t, r in zip(times, data) if not r.get("early_exit") and t > 0]
        return {
            "mean": sum(full) / max(len(full), 1),
            "total": sum(times),
            "total_min": sum(times) / 60,
            "count_full": len(full),
        }

    t30 = timing_stats(v30)
    t31 = timing_stats(v31)
    t4 = timing_stats(v4)

    print(f"\n  {'Metric':<30} {'v3.0':>12} {'v3.1':>12} {'v4':>12}")
    print(f"  {'-'*30} {'-'*12} {'-'*12} {'-'*12}")
    print(f"  {'Mean (full pipeline) s/case':<30} {t30['mean']:>12.1f} {t31['mean']:>12.1f} {t4['mean']:>12.1f}")
    print(f"  {'Total (min)':<30} {t30['total_min']:>12.1f} {t31['total_min']:>12.1f} {t4['total_min']:>12.1f}")
    print(f"  {'Full pipeline cases':<30} {t30['count_full']:>12} {t31['count_full']:>12} {t4['count_full']:>12}")


def main():
    parser = argparse.ArgumentParser(description="Vax-Beacon v3.0 vs v3.1 vs v4 Comparison")
    parser.add_argument("--v4", type=str, default="", help="Path to v4 results JSON")
    args = parser.parse_args()

    # Load results
    print("\n  Loading results...")
    v30 = load_results(V30_PATH)
    print(f"  v3.0: {V30_PATH} ({len(v30)} cases)")

    v31 = load_results(V31_PATH)
    print(f"  v3.1: {V31_PATH} ({len(v31)} cases)")

    v4_path = args.v4 if args.v4 else find_latest_v4_results()
    if not v4_path:
        print("  ERROR: No v4 results found. Run 'python main.py' first or specify --v4 path.")
        sys.exit(1)
    v4 = load_results(v4_path)
    print(f"  v4:   {v4_path} ({len(v4)} cases)")

    # Run comparisons
    compare_who_distribution(v30, v31, v4)
    compare_classification_changes(v30, v31, v4)
    compare_nci_drift(v30, v31, v4)
    compare_marker_flips(v31, v4)
    compare_dominant_alternatives(v30, v31, v4)
    compare_stage6_specificity(v30, v31, v4)
    compare_error_rates(v30, v31, v4)
    compare_timing(v30, v31, v4)

    print("\n" + "=" * 80)
    print("  COMPARISON COMPLETE")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
