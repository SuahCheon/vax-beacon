"""
Compare v4.1a vs v4.1b-r2 results.

v4.1b-r2 changes (cumulative from v4.1a):
  Phase 0: Code-DB sync (high_degree_av_block, recent_covid_infection removal)
  Phase 1: Weight adjustments (peripheral_eosinophilia, prior_cad_history, known_autoimmune_dx: 0.7->0.5)
  Phase 2-3: Subtype review + minor fixes (neg_kw, kw, guide expansions)
  v4.1b: Stage 4/5/6 temporal investigation chain, MIS-C differentiation, onset_unknown routing
  v4.1b: active_covid19 integration (sars_cov2_positive + recent_covid_infection absorbed)

Expected:
  - classify() unchanged -> WHO changes from weight/DB changes or LLM non-determinism
  - Stage 6 quality: temporal-aware gap scaling, bridging queries, nucleocapsid differentiation
"""

import json
import glob
import os
import sys


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

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
    s5 = case.get("stages", {}).get("stage5_causality", {})
    s6 = case.get("stages", {}).get("stage6_guidance", {})
    return s5.get("who_category") or s6.get("who_category", "ERROR")


def get_temporal_zone(case):
    s4 = case.get("stages", {}).get("stage4_temporal", {})
    return s4.get("temporal_assessment", {}).get("temporal_zone", "N/A")


def get_days_to_onset(case):
    s4 = case.get("stages", {}).get("stage4_temporal", {})
    return s4.get("temporal_assessment", {}).get("days_to_onset")


def get_max_nci(case):
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("max_nci_score", 0)


def get_decision_chain(case):
    s5 = case.get("stages", {}).get("stage5_causality", {})
    return s5.get("decision_chain", {})


def get_investigation_intensity(case):
    s4 = case.get("stages", {}).get("stage4_temporal", {})
    return s4.get("temporal_assessment", {}).get("investigation_intensity", "N/A")


def get_stage6(case):
    return case.get("stages", {}).get("stage6_guidance", {})


def get_dominant_alternative(case):
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("dominant_alternative", "NONE")


def get_alternative_etiologies(case):
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("alternative_etiologies", [])


def get_nci_detailed(case):
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("nci_detailed", {})


def get_markers_extracted(case):
    s3 = case.get("stages", {}).get("stage3_ddx", {})
    return s3.get("llm_markers_extracted", {})


def get_brighton(case):
    s2 = case.get("stages", {}).get("stage2_brighton", {})
    return s2.get("brighton_level", "N/A")


# ---------------------------------------------------------------------------
# Change categorization
# ---------------------------------------------------------------------------

def categorize_nci_change(vid, c_a, c_r2):
    """Categorize the reason for NCI score change."""
    nci_det_a = get_nci_detailed(c_a)
    nci_det_r2 = get_nci_detailed(c_r2)
    markers_a = get_markers_extracted(c_a)
    markers_r2 = get_markers_extracted(c_r2)

    reasons = []

    # Weight-adjusted markers
    weight_change_markers = {
        "peripheral_eosinophilia": ("eosinophilic_myocarditis", 0.7, 0.5),
        "prior_cad_history": ("ischemic_heart_disease", 0.7, 0.5),
        "known_autoimmune_dx": ("autoimmune_inflammatory", 0.7, 0.5),
    }

    for marker, (subtype, old_w, new_w) in weight_change_markers.items():
        m_a = markers_a.get(marker, {})
        m_r2 = markers_r2.get(marker, {})
        if m_a.get("present") or m_r2.get("present"):
            # Check if this marker passed plausibility gate in either version
            det_a = nci_det_a.get(subtype, {})
            det_r2 = nci_det_r2.get(subtype, {})
            passed_a = any(m.get("marker") == marker for m in det_a.get("markers_passed", []))
            passed_r2 = any(m.get("marker") == marker for m in det_r2.get("markers_passed", []))
            if passed_a or passed_r2:
                reasons.append(f"weight_change: {marker} ({old_w}->{new_w})")

    # high_degree_av_block (was av_block_present, now properly synced)
    for version_label, markers_dict, nci_det in [("v41a", markers_a, nci_det_a), ("v41b-r2", markers_r2, nci_det_r2)]:
        hda = markers_dict.get("high_degree_av_block", {})
        if hda.get("present"):
            gcm_det = nci_det.get("giant_cell_myocarditis", {})
            passed = any(m.get("marker") == "high_degree_av_block" for m in gcm_det.get("markers_passed", []))
            if passed:
                reasons.append(f"code_db_sync: high_degree_av_block present+passed in {version_label}")

    # COVID marker integration
    for marker in ["active_covid19", "sars_cov2_positive", "recent_covid_infection"]:
        m_a = markers_a.get(marker, {})
        m_r2 = markers_r2.get(marker, {})
        if m_a.get("present") != m_r2.get("present"):
            reasons.append(f"covid_integration: {marker} present changed")

    # Plausibility changes (guide strengthening effect)
    for marker in markers_a:
        m_a = markers_a.get(marker, {})
        m_r2 = markers_r2.get(marker, {})
        if m_a.get("present") == m_r2.get("present") and m_a.get("present"):
            p_a = m_a.get("plausibility", "none")
            p_r2 = m_r2.get("plausibility", "none")
            if p_a != p_r2:
                reasons.append(f"guide_effect: {marker} plausibility {p_a}->{p_r2}")

    if not reasons:
        reasons.append("LLM_non_determinism (no code/DB explanation)")

    return reasons


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------

def main():
    print("\n" + "=" * 75)
    print("  Vax-Beacon: v4.1a vs v4.1b-r2 Comparison")
    print("=" * 75)

    # Load results
    print("\nLoading results...")
    v41a, v41a_path = load_latest_results("results/results_v41a_full_100_*.json")
    v41b_r2, v41b_r2_path = load_latest_results("results/results_v4_full_100_*.json")

    # Filter out error cases
    v41a_valid = [c for c in v41a if not c.get("errors")]
    v41b_r2_valid = [c for c in v41b_r2 if not c.get("errors")]

    v41a_map = {c["vaers_id"]: c for c in v41a_valid}
    v41b_r2_map = {c["vaers_id"]: c for c in v41b_r2_valid}

    common_ids = sorted(set(v41a_map.keys()) & set(v41b_r2_map.keys()))
    print(f"\n  v4.1a total: {len(v41a)}, valid: {len(v41a_valid)}")
    print(f"  v4.1b-r2 total: {len(v41b_r2)}, valid: {len(v41b_r2_valid)}")
    print(f"  Common valid cases: {len(common_ids)}")

    if len(common_ids) < 90:
        print(f"\n  WARNING: Only {len(common_ids)} common cases. Results may not be reliable.")

    # ==================================================================
    # A. WHO Classification Distribution
    # ==================================================================
    print("\n" + "=" * 75)
    print("  A. WHO Classification Changes")
    print("=" * 75)

    cats_a = {}
    cats_r2 = {}
    for vid in common_ids:
        wa = get_who(v41a_map[vid])
        wr2 = get_who(v41b_r2_map[vid])
        cats_a[wa] = cats_a.get(wa, 0) + 1
        cats_r2[wr2] = cats_r2.get(wr2, 0) + 1

    all_cats = sorted(set(list(cats_a.keys()) + list(cats_r2.keys())))
    print(f"\n  {'Category':<16s} {'v4.1a':>8s} {'v4.1b-r2':>10s} {'Delta':>8s}")
    print(f"  {'-' * 46}")
    for cat in all_cats:
        ca = cats_a.get(cat, 0)
        cr2 = cats_r2.get(cat, 0)
        delta = cr2 - ca
        delta_str = f"+{delta}" if delta > 0 else str(delta) if delta < 0 else "0"
        print(f"  {cat:<16s} {ca:>8d} {cr2:>10d} {delta_str:>8s}")
    print(f"  {'-' * 46}")
    print(f"  {'Total':<16s} {len(common_ids):>8d} {len(common_ids):>10d}")

    # Individual case changes
    changed = []
    change_directions = {}
    for vid in common_ids:
        wa = get_who(v41a_map[vid])
        wr2 = get_who(v41b_r2_map[vid])
        if wa != wr2:
            direction = f"{wa}->{wr2}"
            change_directions[direction] = change_directions.get(direction, 0) + 1
            nci_a = get_max_nci(v41a_map[vid])
            nci_r2 = get_max_nci(v41b_r2_map[vid])
            reasons = categorize_nci_change(vid, v41a_map[vid], v41b_r2_map[vid])
            changed.append({
                "vaers_id": vid,
                "v41a": wa,
                "v41b_r2": wr2,
                "nci_a": nci_a,
                "nci_r2": nci_r2,
                "tz_a": get_temporal_zone(v41a_map[vid]),
                "tz_r2": get_temporal_zone(v41b_r2_map[vid]),
                "dominant_a": get_dominant_alternative(v41a_map[vid]),
                "dominant_r2": get_dominant_alternative(v41b_r2_map[vid]),
                "reasons": reasons,
            })

    if changed:
        print(f"\n  {len(changed)} cases changed:\n")
        for c in changed:
            print(f"  VAERS {c['vaers_id']}: {c['v41a']} -> {c['v41b_r2']}")
            print(f"    NCI: {c['nci_a']} -> {c['nci_r2']}, "
                  f"Temporal: {c['tz_a']} -> {c['tz_r2']}")
            print(f"    Dominant: {c['dominant_a']} -> {c['dominant_r2']}")
            for r in c["reasons"]:
                print(f"    - {r}")
            print()

        print(f"  Change direction summary:")
        for direction, count in sorted(change_directions.items()):
            print(f"    {direction}: {count}")
    else:
        print("\n  No cases changed WHO classification.")

    # ==================================================================
    # B. NCI Changes Analysis
    # ==================================================================
    print("\n" + "=" * 75)
    print("  B. NCI Changes Analysis")
    print("=" * 75)

    nci_all_a = []
    nci_all_r2 = []
    nci_changes = []
    for vid in common_ids:
        nci_a = get_max_nci(v41a_map[vid])
        nci_r2 = get_max_nci(v41b_r2_map[vid])
        nci_all_a.append(nci_a)
        nci_all_r2.append(nci_r2)
        if abs(nci_a - nci_r2) > 0.001:
            reasons = categorize_nci_change(vid, v41a_map[vid], v41b_r2_map[vid])
            nci_changes.append({
                "vaers_id": vid,
                "nci_a": nci_a,
                "nci_r2": nci_r2,
                "delta": round(nci_r2 - nci_a, 3),
                "who_a": get_who(v41a_map[vid]),
                "who_r2": get_who(v41b_r2_map[vid]),
                "reasons": reasons,
            })

    # Distribution stats
    def stats(vals):
        n = len(vals)
        mean = sum(vals) / n if n else 0
        sorted_v = sorted(vals)
        median = sorted_v[n // 2] if n else 0
        variance = sum((v - mean) ** 2 for v in vals) / n if n else 0
        std = variance ** 0.5
        return mean, median, std

    mean_a, med_a, std_a = stats(nci_all_a)
    mean_r2, med_r2, std_r2 = stats(nci_all_r2)
    print(f"\n  NCI Distribution (n={len(common_ids)}):")
    print(f"  {'':>12s} {'v4.1a':>10s} {'v4.1b-r2':>10s}")
    print(f"  {'Mean':>12s} {mean_a:>10.3f} {mean_r2:>10.3f}")
    print(f"  {'Median':>12s} {med_a:>10.3f} {med_r2:>10.3f}")
    print(f"  {'Std':>12s} {std_a:>10.3f} {std_r2:>10.3f}")

    if nci_changes:
        print(f"\n  {len(nci_changes)} cases with NCI changes:\n")
        print(f"  {'VAERS':>10s} {'v4.1a':>8s} {'v4.1b-r2':>10s} {'Delta':>8s} {'WHO':>10s} Reasons")
        print(f"  {'-' * 80}")
        for nc in nci_changes:
            sign = "+" if nc["delta"] > 0 else ""
            who_change = f"{nc['who_a']}->{nc['who_r2']}" if nc["who_a"] != nc["who_r2"] else nc["who_a"]
            reason_str = "; ".join(nc["reasons"][:2])
            print(f"  {nc['vaers_id']:>10d} {nc['nci_a']:>8.2f} {nc['nci_r2']:>10.2f} "
                  f"{sign}{nc['delta']:>7.3f} {who_change:>10s} {reason_str}")

        # Categorize by reason type
        reason_cats = {
            "weight_change": 0,
            "code_db_sync": 0,
            "guide_effect": 0,
            "covid_integration": 0,
            "LLM_non_determinism": 0,
        }
        for nc in nci_changes:
            categorized = False
            for r in nc["reasons"]:
                for cat in reason_cats:
                    if cat in r:
                        reason_cats[cat] += 1
                        categorized = True
            if not categorized:
                reason_cats["LLM_non_determinism"] += 1

        print(f"\n  NCI change reasons (may overlap):")
        for cat, count in reason_cats.items():
            if count > 0:
                print(f"    {cat}: {count}")
    else:
        print("\n  No NCI score changes.")

    # ==================================================================
    # C. Marker-specific Impact Analysis
    # ==================================================================
    print("\n" + "=" * 75)
    print("  C. Marker-specific Impact Analysis")
    print("=" * 75)

    impact_markers = {
        "high_degree_av_block": ("giant_cell_myocarditis", "Code-DB sync: weight now applied"),
        "prior_cad_history": ("ischemic_heart_disease", "Weight: 0.7 -> 0.5"),
        "peripheral_eosinophilia": ("eosinophilic_myocarditis", "Weight: 0.7 -> 0.5"),
        "known_autoimmune_dx": ("autoimmune_inflammatory", "Weight: 0.7 -> 0.5"),
        "active_covid19": ("covid19_related", "Integration: absorbed sars_cov2_positive + recent_covid_infection"),
    }

    for marker, (subtype, description) in impact_markers.items():
        print(f"\n  --- {marker} ({description}) ---")
        affected = []
        for vid in common_ids:
            m_a = get_markers_extracted(v41a_map[vid]).get(marker, {})
            m_r2 = get_markers_extracted(v41b_r2_map[vid]).get(marker, {})
            det_a = get_nci_detailed(v41a_map[vid]).get(subtype, {})
            det_r2 = get_nci_detailed(v41b_r2_map[vid]).get(subtype, {})

            passed_a = any(m.get("marker") == marker for m in det_a.get("markers_passed", []))
            passed_r2 = any(m.get("marker") == marker for m in det_r2.get("markers_passed", []))

            present_a = m_a.get("present", False)
            present_r2 = m_r2.get("present", False)
            plaus_a = m_a.get("plausibility", "none")
            plaus_r2 = m_r2.get("plausibility", "none")

            nci_sub_a = det_a.get("nci_score", 0)
            nci_sub_r2 = det_r2.get("nci_score", 0)

            if present_a or present_r2 or passed_a or passed_r2:
                affected.append({
                    "vaers_id": vid,
                    "present_a": present_a,
                    "present_r2": present_r2,
                    "plaus_a": plaus_a,
                    "plaus_r2": plaus_r2,
                    "passed_a": passed_a,
                    "passed_r2": passed_r2,
                    "sub_nci_a": nci_sub_a,
                    "sub_nci_r2": nci_sub_r2,
                })

        if affected:
            print(f"    Cases with this marker present or passed: {len(affected)}")
            for a in affected:
                present_chg = f"present:{a['present_a']}->{a['present_r2']}" if a['present_a'] != a['present_r2'] else f"present:{a['present_r2']}"
                plaus_chg = f"plaus:{a['plaus_a']}->{a['plaus_r2']}" if a['plaus_a'] != a['plaus_r2'] else f"plaus:{a['plaus_r2']}"
                nci_chg = f"sub_nci:{a['sub_nci_a']:.2f}->{a['sub_nci_r2']:.2f}" if abs(a['sub_nci_a'] - a['sub_nci_r2']) > 0.001 else f"sub_nci:{a['sub_nci_r2']:.2f}"
                print(f"      VAERS {a['vaers_id']}: {present_chg}, {plaus_chg}, {nci_chg}")
        else:
            print(f"    No cases affected by this marker.")

    # ==================================================================
    # D. Stage 6 Quality Metrics
    # ==================================================================
    print("\n" + "=" * 75)
    print("  D. Stage 6 Quality Metrics")
    print("=" * 75)

    # D1. Bridging symptom query rate
    print("\n  D1. Bridging Symptom Query Rate")
    bg_unlikely_count = 0
    bridging_found = 0
    bridging_missing = []
    for vid in common_ids:
        tz = get_temporal_zone(v41b_r2_map[vid])
        if tz in ("BACKGROUND_RATE", "UNLIKELY"):
            bg_unlikely_count += 1
            s6 = get_stage6(v41b_r2_map[vid])
            s6_str = json.dumps(s6).lower()
            if "bridging" in s6_str:
                bridging_found += 1
            else:
                bridging_missing.append(vid)

    if bg_unlikely_count > 0:
        rate = bridging_found / bg_unlikely_count * 100
        print(f"    BACKGROUND_RATE/UNLIKELY cases: {bg_unlikely_count}")
        print(f"    With bridging symptom query: {bridging_found}/{bg_unlikely_count} ({rate:.1f}%)")
        print(f"    Target: 100%")
        if bridging_missing:
            print(f"    MISSING: {bridging_missing}")
    else:
        print("    No BACKGROUND_RATE/UNLIKELY cases found.")

    # D2. MRI framing check
    print("\n  D2. MRI Framing Check ('vaccine vs viral' = bad)")
    vaccine_viral_count = 0
    vaccine_viral_cases = []
    for vid in common_ids:
        s6 = get_stage6(v41b_r2_map[vid])
        s6_str = json.dumps(s6).lower()
        if "vaccine vs viral" in s6_str or "vaccine versus viral" in s6_str:
            vaccine_viral_count += 1
            vaccine_viral_cases.append(vid)

    print(f"    'vaccine vs viral' framing: {vaccine_viral_count}")
    print(f"    Target: 0")
    if vaccine_viral_cases:
        print(f"    Found in: {vaccine_viral_cases}")

    # D3. Investigation scope scaling
    print("\n  D3. Investigation Scope Scaling")
    intensity_gaps = {}
    for vid in common_ids:
        intensity = get_investigation_intensity(v41b_r2_map[vid])
        if intensity == "N/A":
            continue
        s6 = get_stage6(v41b_r2_map[vid])
        gaps = s6.get("investigative_gaps", [])
        if intensity not in intensity_gaps:
            intensity_gaps[intensity] = []
        intensity_gaps[intensity].append(len(gaps))

    for intensity in ["STANDARD", "ENHANCED", "COMPREHENSIVE"]:
        if intensity in intensity_gaps:
            vals = intensity_gaps[intensity]
            avg = sum(vals) / len(vals) if vals else 0
            print(f"    {intensity}: avg={avg:.1f} gaps, n={len(vals)}, range=[{min(vals)}-{max(vals)}]")

    if all(k in intensity_gaps for k in ["STANDARD", "ENHANCED", "COMPREHENSIVE"]):
        avgs = {k: sum(v) / len(v) for k, v in intensity_gaps.items()}
        if avgs["STANDARD"] < avgs["ENHANCED"] < avgs["COMPREHENSIVE"]:
            print("    Monotonicity: STANDARD < ENHANCED < COMPREHENSIVE OK")
        else:
            print(f"    WARNING: Not monotonic: S={avgs['STANDARD']:.1f}, E={avgs['ENHANCED']:.1f}, C={avgs['COMPREHENSIVE']:.1f}")

    # D4. MIS-C / COVID nucleocapsid
    print("\n  D4. COVID/MIS-C Nucleocapsid Antibody Recommendation")
    misc_suspects = 0
    nucleocapsid_found = 0
    misc_details = []
    for vid in common_ids:
        dominant = get_dominant_alternative(v41b_r2_map[vid])
        alts = get_alternative_etiologies(v41b_r2_map[vid])
        is_covid = ("covid" in dominant.lower() or "mis" in dominant.lower()) if dominant != "NONE" else False
        if not is_covid:
            for a in alts:
                etio = a.get("etiology", "").lower()
                if "covid" in etio or "mis" in etio:
                    is_covid = True
                    break
        if is_covid:
            misc_suspects += 1
            s6 = get_stage6(v41b_r2_map[vid])
            s6_str = json.dumps(s6).lower()
            has_nucleo = "nucleocapsid" in s6_str
            if has_nucleo:
                nucleocapsid_found += 1
            misc_details.append({"vaers_id": vid, "dominant": dominant, "nucleocapsid": has_nucleo})

    if misc_suspects > 0:
        rate = nucleocapsid_found / misc_suspects * 100
        print(f"    COVID/MIS-C suspects: {misc_suspects}")
        print(f"    With nucleocapsid recommendation: {nucleocapsid_found}/{misc_suspects} ({rate:.1f}%)")
        print(f"    Target: 100%")
        for d in misc_details:
            status = "OK" if d["nucleocapsid"] else "MISSING"
            print(f"      VAERS {d['vaers_id']}: dominant={d['dominant']} [{status}]")
    else:
        print("    No COVID/MIS-C suspected cases found.")

    # D5. Onset unknown
    print("\n  D5. Onset Unknown Routing")
    onset_unknown_count = 0
    onset_verify_found = 0
    onset_details = []
    for vid in common_ids:
        dc = get_decision_chain(v41b_r2_map[vid])
        if dc.get("onset_unknown", False):
            onset_unknown_count += 1
            s6 = get_stage6(v41b_r2_map[vid])
            has_verify = "onset_verification" in s6
            has_possible = "possible_categories_once_onset_known" in s6
            if has_verify:
                onset_verify_found += 1
            onset_details.append({"vaers_id": vid, "verify": has_verify, "possible_cats": has_possible})

    if onset_unknown_count > 0:
        rate = onset_verify_found / onset_unknown_count * 100
        print(f"    Onset unknown cases: {onset_unknown_count}")
        print(f"    With onset_verification: {onset_verify_found}/{onset_unknown_count} ({rate:.1f}%)")
        for d in onset_details:
            v_st = "OK" if d["verify"] else "MISSING"
            p_st = "OK" if d["possible_cats"] else "MISSING"
            print(f"      VAERS {d['vaers_id']}: verification={v_st}, possible_categories={p_st}")
    else:
        print("    No onset unknown cases found.")

    # ==================================================================
    # E. Dominant Category Distribution
    # ==================================================================
    print("\n" + "=" * 75)
    print("  E. Dominant Category Distribution")
    print("=" * 75)

    dom_a = {}
    dom_r2 = {}
    dom_changed = []
    for vid in common_ids:
        da = get_dominant_alternative(v41a_map[vid])
        dr2 = get_dominant_alternative(v41b_r2_map[vid])
        dom_a[da] = dom_a.get(da, 0) + 1
        dom_r2[dr2] = dom_r2.get(dr2, 0) + 1
        if da != dr2:
            dom_changed.append({"vaers_id": vid, "v41a": da, "v41b_r2": dr2})

    all_doms = sorted(set(list(dom_a.keys()) + list(dom_r2.keys())))
    print(f"\n  {'Dominant':<35s} {'v4.1a':>8s} {'v4.1b-r2':>10s} {'Delta':>8s}")
    print(f"  {'-' * 65}")
    for dom in all_doms:
        ca = dom_a.get(dom, 0)
        cr2 = dom_r2.get(dom, 0)
        delta = cr2 - ca
        delta_str = f"+{delta}" if delta > 0 else str(delta) if delta < 0 else "0"
        print(f"  {dom:<35s} {ca:>8d} {cr2:>10d} {delta_str:>8s}")

    if dom_changed:
        print(f"\n  Dominant changed ({len(dom_changed)} cases):")
        for d in dom_changed:
            print(f"    VAERS {d['vaers_id']}: {d['v41a']} -> {d['v41b_r2']}")
    else:
        print("\n  No dominant category changes.")

    # ==================================================================
    # F. Error Summary
    # ==================================================================
    print("\n" + "=" * 75)
    print("  F. Error Summary")
    print("=" * 75)

    errors_a = [c for c in v41a if c.get("errors")]
    errors_r2 = [c for c in v41b_r2 if c.get("errors")]
    print(f"\n  v4.1a errors: {len(errors_a)} cases")
    print(f"  v4.1b-r2 errors: {len(errors_r2)} cases")

    if errors_r2:
        print("\n  v4.1b-r2 error details:")
        for c in errors_r2:
            print(f"    VAERS {c['vaers_id']}: {c['errors']}")

    # ==================================================================
    # Summary
    # ==================================================================
    print("\n" + "=" * 75)
    print("  SUMMARY")
    print("=" * 75)
    print(f"\n  Compared: {len(common_ids)} common cases")
    print(f"  WHO changed: {len(changed)} cases")
    print(f"  NCI changed: {len(nci_changes)} cases")
    print(f"  Dominant changed: {len(dom_changed)} cases")
    print(f"  v4.1b-r2 errors: {len(errors_r2)} cases")

    print("\n" + "=" * 75)
    print("  Comparison complete.")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
