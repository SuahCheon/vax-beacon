"""
Vax-Beacon: Main Pipeline Orchestrator (v4)
===============================================
WHO AEFI Digital Manual Architecture — Deterministic Refactoring

v4 Core Changes:
  - Stage 3 Two-Pass: 3A(LLM observe) → 3B(Code match) → 3C(LLM assess) → 3D(Code calc)
  - Stage 5 Deterministic: Code classifies, LLM only explains
  - Knowledge DB: Domain knowledge in JSON, LLM references at runtime

Stage ↔ WHO Mapping:
  Stage 1 (LLM)  → Data Intake
  Stage 2 (Rule) → Step 0: Valid Diagnosis [Brighton Gatekeeper]
  Stage 3 (2xLLM + 2xCode) → Step 1: Other Causes? [DDx + NCI]
  Stage 4 (Rule) → Step 2: Known AE + Temporal [Auditor]
  Stage 5 (Code + LLM) → Step 3 & 4: Causality Assessment [Assessor]
  Stage 6 (LLM)  → Reporting [Knowledge-DB-driven Gap Analysis + HITL]

Brighton Level 4 → Early Exit → Stage 6 directly

Usage:
  python main.py                    # Run all 100 cases
  python main.py --sample 2         # Run 2 cases per group (test mode)
  python main.py --case 925542      # Run a single case by VAERS_ID
  python main.py --group G2         # Run all cases in a specific group
"""

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime

# Windows UTF-8 console fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from config import RESULTS_PATH
from llm_client import LLMClient
from data_loader import load_vaers_data, get_case_input, get_ground_truth, get_sample_cases

from pipeline.stage1_icsr_extractor import run_stage1
from pipeline.stage2_clinical_validator import run_stage2
from pipeline.stage3a_clinical_observer import run_stage3a
from pipeline.stage3b_ddx_matcher import run_stage3b
from pipeline.stage3c_plausibility import run_stage3c
from pipeline.stage3d_nci_calculator import run_stage3d, merge_stage3
from pipeline.stage4_auditor import run_stage4
from pipeline.stage5_causality_assessor import run_stage5
from pipeline.stage6_guidance_advisor import run_stage6
from knowledge_loader import load_knowledge_db
from report_renderer import render_report, render_docx

# Load Knowledge DB at module level
_KNOWLEDGE_DB = load_knowledge_db()


def run_single_case(llm: LLMClient, row: pd.Series, verbose: bool = True) -> dict:
    """
    Run the 6-stage WHO AEFI pipeline on a single VAERS case.

    Flow:
      Stage 1 (LLM) → Stage 2 (Rule) → [Early Exit?] → Stage 3 (LLM)
      → Stage 4 (Rule) → Stage 5 (LLM) → Stage 6 (LLM)
    """
    vaers_id = row["VAERS_ID"]
    condition_type = row.get("condition_type", "myocarditis")

    if verbose:
        print(f"\n{'='*60}")
        print(f"  VAERS ID: {vaers_id} | {condition_type} | Group: {row.get('group', '?')}")
        print(f"{'='*60}")

    result = {
        "vaers_id": vaers_id,
        "condition_type": condition_type,
        "group": row.get("group"),
        "ground_truth": get_ground_truth(row),
        "stages": {},
        "errors": [],
        "processing_time": {},
        "early_exit": False,
    }

    # Raw case text — used by Stage 1 and Stage 3 (DDx needs original narrative)
    case_text = get_case_input(row)

    # ==================================================================
    # Phase 1: Data Preprocessing & Diagnosis Filtering
    # ==================================================================

    # --- Stage 1: ICSR Extraction (LLM) — Data Intake ---
    try:
        t0 = time.time()
        if verbose:
            print(f"  [Stage 1] ICSR Extractor (LLM)...", end=" ", flush=True)
        result["stages"]["stage1_icsr"] = run_stage1(llm, case_text)
        result["processing_time"]["stage1"] = round(time.time() - t0, 2)
        if verbose:
            print(f"OK ({result['processing_time']['stage1']}s)")
    except Exception as e:
        result["errors"].append({"stage": 1, "error": str(e)})
        if verbose:
            print(f"FAIL: {e}")
        return result

    # --- Stage 2: Clinical Validator (Rule) — WHO Step 0: Valid Diagnosis ---
    try:
        t0 = time.time()
        if verbose:
            print(f"  [Stage 2] Clinical Validator (Rule)...", end=" ", flush=True)
        result["stages"]["stage2_brighton"] = run_stage2(result["stages"]["stage1_icsr"])
        result["processing_time"]["stage2"] = round(time.time() - t0, 2)
        brighton_lvl = result["stages"]["stage2_brighton"]["brighton_level"]
        early_exit = result["stages"]["stage2_brighton"]["early_exit"]
        if verbose:
            tag = " >> EARLY EXIT" if early_exit else ""
            print(f"OK -> Brighton L{brighton_lvl} ({result['processing_time']['stage2']}s){tag}")
    except Exception as e:
        result["errors"].append({"stage": 2, "error": str(e)})
        if verbose:
            print(f"FAIL: {e}")
        return result

    # --- EARLY EXIT: Brighton L4 → Skip to Stage 6 ---
    if early_exit:
        result["early_exit"] = True
        try:
            t0 = time.time()
            if verbose:
                print(f"  [Stage 6] Brighton Exit Guidance (LLM)...", end=" ", flush=True)
            result["stages"]["stage6_guidance"] = run_stage6(
                llm,
                result["stages"]["stage1_icsr"],
                result["stages"]["stage2_brighton"],
                early_exit=True,
            )
            result["processing_time"]["stage6"] = round(time.time() - t0, 2)
            s6_who = result["stages"]["stage6_guidance"].get("who_category", "Unclassifiable")
            if verbose:
                print(f"OK -> WHO: {s6_who} ({result['processing_time']['stage6']}s)")
        except Exception as e:
            result["errors"].append({"stage": 6, "error": str(e)})
            if verbose:
                print(f"FAIL: {e}")

        total = sum(result["processing_time"].values())
        result["processing_time"]["total"] = round(total, 2)
        if verbose:
            print(f"  -- Early Exit: WHO=Unclassifiable, Brighton=L4, Time={total:.1f}s")
        return result

    # ==================================================================
    # Phase 2: Mechanistic Investigation
    # ==================================================================

    # --- Stage 3: DDx Two-Pass (v4) — WHO Step 1: Other Causes? ---
    try:
        t0 = time.time()
        if verbose:
            print(f"  [Stage 3A] Clinical Observer (LLM)...", end=" ", flush=True)
        stage3a = run_stage3a(llm, case_text)
        t3a = round(time.time() - t0, 2)
        if verbose:
            obs_count = sum(len(v) for v in stage3a.get("clinical_observations", {}).values())
            print(f"OK -> {obs_count} observations ({t3a}s)")

        if verbose:
            print(f"  [Stage 3B] DDx Matcher (Code)...", end=" ", flush=True)
        t0b = time.time()
        stage3b = run_stage3b(stage3a, _KNOWLEDGE_DB["ddx"])
        t3b = round(time.time() - t0b, 2)
        if verbose:
            n_cand = stage3b["match_summary"]["total_candidates"]
            n_match = stage3b["match_summary"]["total_matched_indicators"]
            print(f"OK -> {n_cand} candidates, {n_match} matched ({t3b}s)")

        if verbose:
            print(f"  [Stage 3C] Plausibility Assessor (LLM)...", end=" ", flush=True)
        t0c = time.time()
        stage3c = run_stage3c(llm, case_text, stage3a, stage3b, _KNOWLEDGE_DB["ddx"])
        t3c = round(time.time() - t0c, 2)
        if verbose:
            present_count = sum(1 for v in stage3c.values() if v.get("present"))
            print(f"OK -> {present_count} markers present ({t3c}s)")

        if verbose:
            print(f"  [Stage 3D] NCI Calculator (Code)...", end=" ", flush=True)
        t0d = time.time()
        stage3d = run_stage3d(stage3c, _KNOWLEDGE_DB["ddx"])
        t3d = round(time.time() - t0d, 2)

        vaers_id = result["stages"]["stage1_icsr"].get("vaers_id", vaers_id)
        result["stages"]["stage3_ddx"] = merge_stage3(
            stage3a, stage3b, stage3c, stage3d, vaers_id=vaers_id,
        )
        result["processing_time"]["stage3"] = round(t3a + t3b + t3c + t3d, 2)
        max_nci = result["stages"]["stage3_ddx"].get("max_nci_score", "?")
        step1 = result["stages"]["stage3_ddx"].get("who_step1_conclusion", "?")
        if verbose:
            print(f"OK -> NCI={max_nci}, Step1={step1} ({t3d}s)")
    except Exception as e:
        result["errors"].append({"stage": 3, "error": str(e)})
        if verbose:
            print(f"FAIL: {e}")

    # --- Stage 4: Auditor — Known AE + Temporal (Rule) — WHO Step 2 ---
    try:
        t0 = time.time()
        if verbose:
            print(f"  [Stage 4] Auditor — Known AE + Temporal (Rule)...", end=" ", flush=True)
        result["stages"]["stage4_temporal"] = run_stage4(
            result["stages"]["stage1_icsr"],
            result["stages"]["stage2_brighton"],
            result["stages"].get("stage3_ddx", {}),
        )
        result["processing_time"]["stage4"] = round(time.time() - t0, 2)
        zone = result["stages"]["stage4_temporal"]["temporal_assessment"]["temporal_zone"]
        days = result["stages"]["stage4_temporal"]["temporal_assessment"]["days_to_onset"]
        known = result["stages"]["stage4_temporal"]["known_ae_assessment"]["is_known_ae"]
        if verbose:
            print(f"OK -> {zone} ({days}d), KnownAE={known} ({result['processing_time']['stage4']}s)")
    except Exception as e:
        result["errors"].append({"stage": 4, "error": str(e)})
        if verbose:
            print(f"FAIL: {e}")

    # ==================================================================
    # Phase 3: Judgment & Reporting
    # ==================================================================

    # --- Stage 5: Causality Assessor (Code+LLM) — WHO Step 3 & 4 ---
    try:
        t0 = time.time()
        if verbose:
            print(f"  [Stage 5] Causality Assessor (Code+LLM)...", end=" ", flush=True)
        result["stages"]["stage5_causality"] = run_stage5(
            llm,
            result["stages"]["stage1_icsr"],
            result["stages"].get("stage2_brighton", {}),
            result["stages"].get("stage3_ddx", {}),
            result["stages"].get("stage4_temporal", {}),
            condition_type=condition_type,
        )
        result["processing_time"]["stage5"] = round(time.time() - t0, 2)
        who_cat = result["stages"]["stage5_causality"].get("who_category", "?")
        if verbose:
            print(f"OK -> WHO: {who_cat} ({result['processing_time']['stage5']}s)")
    except Exception as e:
        result["errors"].append({"stage": 5, "error": str(e)})
        if verbose:
            print(f"FAIL: {e}")

    # --- Stage 6: Guidance Advisor (LLM) — Reporting ---
    try:
        t0 = time.time()
        if verbose:
            print(f"  [Stage 6] Guidance Advisor (LLM)...", end=" ", flush=True)
        result["stages"]["stage6_guidance"] = run_stage6(
            llm,
            result["stages"]["stage1_icsr"],
            result["stages"].get("stage2_brighton", {}),
            result["stages"].get("stage3_ddx", {}),
            result["stages"].get("stage4_temporal", {}),
            result["stages"].get("stage5_causality", {}),
            knowledge_db=_KNOWLEDGE_DB,
        )
        result["processing_time"]["stage6"] = round(time.time() - t0, 2)
        if verbose:
            print(f"OK ({result['processing_time']['stage6']}s)")
    except Exception as e:
        result["errors"].append({"stage": 6, "error": str(e)})
        if verbose:
            print(f"FAIL: {e}")

    # --- Summary ---
    total = sum(result["processing_time"].values())
    result["processing_time"]["total"] = round(total, 2)
    if verbose:
        who_cat = result["stages"].get("stage5_causality", {}).get("who_category", "N/A")
        brighton = result["stages"].get("stage2_brighton", {}).get("brighton_level", "N/A")
        known = result["stages"].get("stage4_temporal", {}).get("known_ae_assessment", {}).get("is_known_ae", "?")
        print(f"  -- Complete: WHO={who_cat}, Brighton=L{brighton}, KnownAE={known}, Time={total:.1f}s")

    return result


def save_results(results: list, tag: str = ""):
    """Save pipeline results to JSON and summary CSV."""
    os.makedirs(RESULTS_PATH, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag_str = f"_{tag}" if tag else ""

    # Full JSON
    json_path = os.path.join(RESULTS_PATH, f"results{tag_str}_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str, ensure_ascii=False)
    print(f"\nFull results: {json_path}")

    # Summary CSV
    summary_rows = []
    for r in results:
        s5 = r.get("stages", {}).get("stage5_causality", {})
        s2 = r.get("stages", {}).get("stage2_brighton", {})
        s3 = r.get("stages", {}).get("stage3_ddx", {})
        s4 = r.get("stages", {}).get("stage4_temporal", {})
        s6 = r.get("stages", {}).get("stage6_guidance", {})
        gt = r.get("ground_truth", {})

        # Early exit cases get WHO=Unclassifiable from Stage 6
        who_cat = s5.get("who_category") or s6.get("who_category", "ERROR")

        summary_rows.append({
            "vaers_id": r["vaers_id"],
            "condition_type": r["condition_type"],
            "group": r["group"],
            "early_exit": r.get("early_exit", False),
            "brighton_level": s2.get("brighton_level"),
            # Stage 3 = DDx (WHO Step 1)
            "who_step1_conclusion": s3.get("who_step1_conclusion"),
            "max_nci": s3.get("max_nci_score"),
            "dominant_alternative": s3.get("dominant_alternative"),
            # Stage 4 = Temporal + Known AE (WHO Step 2)
            "temporal_zone": s4.get("temporal_assessment", {}).get("temporal_zone"),
            "days_to_onset": s4.get("temporal_assessment", {}).get("days_to_onset"),
            "known_ae": s4.get("known_ae_assessment", {}).get("is_known_ae"),
            "who_step2_met": s4.get("who_step2_met"),
            "high_risk": s4.get("high_risk_group", {}).get("is_high_risk"),
            # Stage 5 = Final classification
            "who_category": who_cat,
            "confidence": s5.get("confidence"),
            # Stage 6
            "risk_signal": s6.get("overall_risk_signal"),
            "errors": len(r.get("errors", [])),
            "total_time_s": r.get("processing_time", {}).get("total"),
            # Ground truth
            "gt_group": gt.get("group"),
            "gt_severity": gt.get("curated_severity"),
            "gt_onset_days": gt.get("curated_onset_days"),
        })

    csv_path = os.path.join(RESULTS_PATH, f"summary{tag_str}_{timestamp}.csv")
    pd.DataFrame(summary_rows).to_csv(csv_path, index=False)
    print(f"Summary CSV: {csv_path}")

    return json_path, csv_path


def print_summary_stats(results: list):
    """Print aggregate statistics."""
    total = len(results)
    early_exits = sum(1 for r in results if r.get("early_exit"))
    errors = sum(len(r.get("errors", [])) for r in results)

    print(f"\n{'='*60}")
    print(f"  Vax-Beacon v4 Pipeline Summary")
    print(f"  WHO AEFI Digital Manual Architecture (Deterministic Refactoring)")
    print(f"{'='*60}")
    print(f"  Total: {total} | Early Exit(L4): {early_exits} | Full Pipeline: {total - early_exits} | Errors: {errors}")

    # WHO Categories
    who_cats = {}
    for r in results:
        s5 = r.get("stages", {}).get("stage5_causality", {})
        s6 = r.get("stages", {}).get("stage6_guidance", {})
        cat = s5.get("who_category") or s6.get("who_category", "ERROR")
        who_cats[cat] = who_cats.get(cat, 0) + 1
    print(f"\n  WHO Category Distribution:")
    for cat in sorted(who_cats.keys()):
        count = who_cats[cat]
        pct = count / total * 100
        bar = "█" * int(pct / 2)
        print(f"    {cat:5s}: {count:3d} ({pct:5.1f}%) {bar}")

    # Brighton Levels
    brighton = {}
    for r in results:
        lvl = r.get("stages", {}).get("stage2_brighton", {}).get("brighton_level", "?")
        brighton[lvl] = brighton.get(lvl, 0) + 1
    print(f"\n  Brighton Level Distribution:")
    for lvl in sorted(brighton.keys(), key=str):
        print(f"    Level {lvl}: {brighton[lvl]}")

    # Known AE check
    known_ae_count = sum(
        1 for r in results
        if r.get("stages", {}).get("stage4_temporal", {}).get("known_ae_assessment", {}).get("is_known_ae")
    )
    print(f"\n  Known AE (Established): {known_ae_count} cases")
    print(f"  Early Exit (Brighton L4): {early_exits} cases")

    # Timing
    times = [r.get("processing_time", {}).get("total", 0) for r in results]
    if times:
        full_times = [t for t, r in zip(times, results) if not r.get("early_exit")]
        exit_times = [t for t, r in zip(times, results) if r.get("early_exit")]
        print(f"\n  Processing Time:")
        print(f"    Full pipeline mean: {sum(full_times)/max(len(full_times),1):.1f}s/case")
        if exit_times:
            print(f"    Early exit mean: {sum(exit_times)/len(exit_times):.1f}s/case")
        print(f"    Total: {sum(times):.0f}s ({sum(times)/60:.1f}min)")


def _prompt_choice(prompt: str, valid: range, allow_quit: bool = False) -> str:
    """Prompt user for a numeric choice, re-prompt on invalid input."""
    while True:
        try:
            raw = input(prompt).strip().upper()
        except EOFError:
            return "Q" if allow_quit else str(valid.stop - 1)
        if allow_quit and raw == "Q":
            return "Q"
        if allow_quit and raw == "N":
            return "N"
        if allow_quit and raw == "P":
            return "P"
        try:
            val = int(raw)
            if val in valid:
                return str(val)
        except ValueError:
            pass
        print(f"  Invalid input. Please enter {valid.start}-{valid.stop - 1}.")


def _display_case_list(df_display: pd.DataFrame, page: int = 0, page_size: int = 20) -> int:
    """Display paginated case list. Returns total pages."""
    total = len(df_display)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start = page * page_size
    end = min(start + page_size, total)

    print(f"\n  {'#':>4s}   {'VAERS_ID':>10s}   {'Age':>4s}  {'Sex':>3s}  {'Vaccine':<12s}  {'Group':<6s}  {'Condition'}")
    print(f"  {'─'*4}   {'─'*10}   {'─'*4}  {'─'*3}  {'─'*12}  {'─'*6}  {'─'*12}")
    for i, (_, row) in enumerate(df_display.iloc[start:end].iterrows(), start=start + 1):
        vid = row["VAERS_ID"]
        age = row.get("AGE_YRS", "?")
        sex = row.get("SEX", "?")
        vax = str(row.get("VAX_MANU", "?"))[:12]
        group = row.get("group", "?")
        cond = row.get("condition_type", "?")
        print(f"  {i:4d}   {vid:>10d}   {str(age):>4s}  {sex:>3s}  {vax:<12s}  {group:<6s}  {cond}")

    print(f"\n  -- Page {page + 1}/{total_pages} ({start + 1}-{end} of {total}) --")
    return total_pages


def run_interactive(llm: LLMClient, df: pd.DataFrame):
    """Interactive case selection and analysis flow."""
    n_myo = len(df[df["condition_type"] == "myocarditis"])
    n_peri = len(df[df["condition_type"] == "pericarditis"])

    while True:
        # --- Step 1: Welcome Banner ---
        print(f"\n{'═'*58}")
        print(f"  Vax-Beacon v4.3 | Interactive Case Analysis")
        print(f"  {len(df)} cases loaded ({n_myo} myocarditis, {n_peri} pericarditis)")
        print(f"{'═'*58}")
        print(f"\nHow would you like to select a case?\n")
        print(f"  [1] Browse case list")
        print(f"  [2] Enter VAERS ID directly")
        print(f"  [3] Filter by group (G1/G2/G3)")
        print(f"  [4] Filter by condition (myocarditis/pericarditis)")
        print(f"  [5] Quit\n")

        choice = _prompt_choice("Select (1-5): ", range(1, 6))

        if choice == "5":
            print("\n  Goodbye!\n")
            return

        # --- Step 2: Case Selection ---
        selected_row = None

        if choice == "1":
            # Browse all cases
            selected_row = _browse_cases(df)
        elif choice == "2":
            # Enter VAERS ID directly
            selected_row = _select_by_id(df)
        elif choice == "3":
            # Filter by group
            selected_row = _select_by_group(df)
        elif choice == "4":
            # Filter by condition
            selected_row = _select_by_condition(df)

        if selected_row is None:
            continue  # Back to main menu

        # --- Step 3: Confirm & Run ---
        row = selected_row
        vid = row["VAERS_ID"]
        age = row.get("AGE_YRS", "?")
        sex = row.get("SEX", "?")
        vax = row.get("VAX_MANU", "?")
        dose = row.get("VAX_DOSE_SERIES", "?")
        cond = row.get("condition_type", "?")
        group = row.get("group", "?")

        print(f"\n{'═'*58}")
        print(f"  Running Vax-Beacon v4.3 on VAERS {vid}")
        print(f"  {age}{sex} | {vax} Dose {dose} | {cond} | Group {group}")
        print(f"{'═'*58}")

        try:
            result = run_single_case(llm, row, verbose=True)
            save_results([result], tag=f"v4_case_{vid}")
        except Exception as e:
            print(f"\n  Pipeline error: {e}")
            traceback.print_exc()
            result = None

        if result and not result.get("errors"):
            # --- Step 4: Post-Pipeline Report Selection ---
            s5 = result.get("stages", {}).get("stage5_causality", {})
            s6 = result.get("stages", {}).get("stage6_guidance", {})
            s2 = result.get("stages", {}).get("stage2_brighton", {})
            who_cat = s5.get("who_category") or s6.get("who_category", "?")
            brighton = s2.get("brighton_level", "?")
            total_time = result.get("processing_time", {}).get("total", "?")

            print(f"\n{'═'*58}")
            print(f"  Pipeline Complete | WHO: {who_cat} | Brighton: L{brighton} | {total_time}s")
            print(f"{'═'*58}")
            print(f"\nGenerate report?\n")
            print(f"  [1] Markdown only (.md)")
            print(f"  [2] Markdown + Word (.docx)")
            print(f"  [3] Skip report\n")

            report_choice = _prompt_choice("Select (1-3): ", range(1, 4))

            if report_choice in ("1", "2"):
                report_path = render_report(result)
                print(f"  Report: {report_path}")
                if report_choice == "2":
                    docx_path = render_docx(report_path)
                    if docx_path:
                        print(f"  Word report: {docx_path}")
            else:
                print("  Skipped.")
        elif result and result.get("errors"):
            print(f"\n  Pipeline completed with errors: {result['errors']}")

        # --- Step 5: Continue or Quit ---
        print(f"\nWhat next?\n")
        print(f"  [1] Analyze another case")
        print(f"  [2] Quit\n")
        next_choice = _prompt_choice("Select (1-2): ", range(1, 3))
        if next_choice == "2":
            print("\n  Goodbye!\n")
            return


def _browse_cases(df: pd.DataFrame) -> pd.Series | None:
    """Browse paginated case list and select a case."""
    page = 0
    page_size = 20
    while True:
        total_pages = _display_case_list(df, page, page_size)
        print(f"  [N]ext page  [P]rev page  [#] Select case number  [Q]uit\n")
        try:
            raw = input("Select: ").strip().upper()
        except EOFError:
            return None

        if raw == "Q":
            return None
        elif raw == "N":
            if page < total_pages - 1:
                page += 1
            else:
                print("  Already on last page.")
        elif raw == "P":
            if page > 0:
                page -= 1
            else:
                print("  Already on first page.")
        else:
            try:
                idx = int(raw)
                if 1 <= idx <= len(df):
                    return df.iloc[idx - 1]
                else:
                    print(f"  Invalid. Enter 1-{len(df)}.")
            except ValueError:
                print("  Invalid input.")


def _select_by_id(df: pd.DataFrame) -> pd.Series | None:
    """Select a case by VAERS ID."""
    while True:
        try:
            raw = input("\nEnter VAERS ID (or Q to cancel): ").strip().upper()
        except EOFError:
            return None
        if raw == "Q":
            return None
        try:
            vid = int(raw)
        except ValueError:
            print("  Invalid input. Enter a numeric VAERS ID.")
            continue
        matches = df[df["VAERS_ID"] == vid]
        if len(matches) == 0:
            print(f"  VAERS ID {vid} not found in cohort. Try again.")
            continue
        row = matches.iloc[0]
        age = row.get("AGE_YRS", "?")
        sex = row.get("SEX", "?")
        vax = row.get("VAX_MANU", "?")
        dose = row.get("VAX_DOSE_SERIES", "?")
        group = row.get("group", "?")
        cond = row.get("condition_type", "?")
        print(f"\n  Found: VAERS {vid} | {age}{sex} | {vax} Dose {dose} | {group} | {cond}\n")
        try:
            confirm = input("Proceed? [Y/n]: ").strip().lower()
        except EOFError:
            confirm = "y"
        if confirm in ("", "y", "yes"):
            return row


def _select_by_group(df: pd.DataFrame) -> pd.Series | None:
    """Filter by group and select from filtered list."""
    groups = sorted(df["group"].unique())
    counts = df["group"].value_counts()

    print(f"\nAvailable groups:")
    for i, g in enumerate(groups, 1):
        print(f"  [{i}] {g} (N={counts.get(g, 0)})")
    print()

    choice = _prompt_choice(f"Select group (1-{len(groups)}): ", range(1, len(groups) + 1))
    selected_group = groups[int(choice) - 1]
    filtered = df[df["group"] == selected_group].reset_index(drop=True)

    if len(filtered) == 0:
        print("  No cases match. Try different filter.")
        return None

    return _browse_cases(filtered)


def _select_by_condition(df: pd.DataFrame) -> pd.Series | None:
    """Filter by condition and select from filtered list."""
    n_myo = len(df[df["condition_type"] == "myocarditis"])
    n_peri = len(df[df["condition_type"] == "pericarditis"])

    print(f"\n  [1] myocarditis (N={n_myo})")
    print(f"  [2] pericarditis (N={n_peri})\n")

    choice = _prompt_choice("Select (1-2): ", range(1, 3))
    cond = "myocarditis" if choice == "1" else "pericarditis"
    filtered = df[df["condition_type"] == cond].reset_index(drop=True)

    if len(filtered) == 0:
        print("  No cases match. Try different filter.")
        return None

    return _browse_cases(filtered)


def generate_benchmark_csv(llm: LLMClient, results: list, tag: str = ""):
    """
    Generate benchmark comparison CSV with key_logic_reasoning via Haiku.
    Columns: vaers_id, brighton_level, max_nci_score, dominant_alternative,
             who_category, guidance_type, key_logic_reasoning
    """
    REASONING_SYSTEM = (
        "You are a medical regulatory expert. Given a WHO AEFI causality assessment result, "
        "produce exactly ONE sentence (max 30 words) explaining WHY this case received its WHO category. "
        "Focus on the decisive factor (temporal, NCI, Brighton level, etc). "
        "Do not include the category name itself. English only."
    )

    rows = []
    total = len(results)

    for i, r in enumerate(results):
        vaers_id = r["vaers_id"]
        s2 = r.get("stages", {}).get("stage2_brighton", {})
        s3 = r.get("stages", {}).get("stage3_ddx", {})
        s5 = r.get("stages", {}).get("stage5_causality", {})
        s6 = r.get("stages", {}).get("stage6_guidance", {})

        # WHO category
        who_cat = s5.get("who_category") or s6.get("who_category", "ERROR")

        # Guidance type: check if knowledge DB protocol was injected
        has_protocol = bool(
            s6.get("investigation_protocol")
            or s6.get("protocol_source")
            or s6.get("etiology_specific_protocol")
        )
        guidance_type = "protocol_injection" if has_protocol else "gap_analysis"

        # Key logic reasoning via Haiku
        reasoning_input = (
            f"VAERS {vaers_id}: Brighton L{s2.get('brighton_level', '?')}, "
            f"NCI={s3.get('max_nci_score', 0)}, "
            f"Dominant alt: {s3.get('dominant_alternative', 'none')}, "
            f"Temporal zone: {r.get('stages', {}).get('stage4_temporal', {}).get('temporal_assessment', {}).get('temporal_zone', '?')}, "
            f"Days: {r.get('stages', {}).get('stage4_temporal', {}).get('temporal_assessment', {}).get('days_to_onset', '?')}, "
            f"WHO: {who_cat}, "
            f"Early exit: {r.get('early_exit', False)}"
        )

        try:
            key_reasoning = llm.query_light(REASONING_SYSTEM, reasoning_input)
        except Exception as e:
            key_reasoning = f"[Error: {e}]"

        if (i + 1) % 10 == 0:
            print(f"  [Benchmark] {i+1}/{total} reasoning summaries generated")

        rows.append({
            "vaers_id": vaers_id,
            "brighton_level": s2.get("brighton_level"),
            "max_nci_score": s3.get("max_nci_score", 0.0),
            "dominant_alternative": s3.get("dominant_alternative", "NONE"),
            "who_category": who_cat,
            "guidance_type": guidance_type,
            "key_logic_reasoning": key_reasoning,
        })

    # Save
    os.makedirs(RESULTS_PATH, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag_str = f"_{tag}" if tag else ""
    csv_path = os.path.join(RESULTS_PATH, f"benchmark{tag_str}_{timestamp}.csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\nBenchmark CSV: {csv_path}")
    return csv_path


def generate_batch_reports(results: list):
    """Generate individual .md reports for all cases in a batch run."""
    count = 0
    errors = 0
    for r in results:
        try:
            render_report(r)
            count += 1
        except Exception as e:
            print(f"  [Report] Error on VAERS {r.get('vaers_id', '?')}: {e}")
            errors += 1
    print(f"\nReports: {count} generated, {errors} errors → reports/")


def main():
    parser = argparse.ArgumentParser(description="Vax-Beacon v4 — WHO AEFI Digital Manual (Deterministic)")
    parser.add_argument("--sample", type=int, default=0, help="N cases per group (test)")
    parser.add_argument("--case", type=int, default=0, help="Single VAERS_ID")
    parser.add_argument("--group", type=str, default="", help="Group filter (G1/G2/G3/clean/confounded)")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    parser.add_argument("--docx", action="store_true", help="Also generate Word report")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Launch interactive case selection mode")
    args = parser.parse_args()

    llm = LLMClient(backend="anthropic")
    df = load_vaers_data()

    # Interactive mode takes priority
    if args.interactive:
        try:
            run_interactive(llm, df)
        except KeyboardInterrupt:
            print("\n\n  Interrupted. Goodbye!\n")
        return

    if args.case:
        df = df[df["VAERS_ID"] == args.case]
        tag = f"v4_case_{args.case}"
    elif args.group:
        df = df[df["group"] == args.group]
        tag = f"v4_group_{args.group}"
    elif args.sample:
        df = get_sample_cases(df, n_per_group=args.sample)
        tag = f"v4_sample_{args.sample}"
    else:
        tag = "v4_full_100"

    print(f"\n  Vax-Beacon v4 | WHO AEFI Digital Manual (Deterministic)")
    print(f"  {len(df)} cases | tag: {tag}")
    print(f"  Architecture: Two-Pass DDx + Deterministic Classification + Knowledge DB")
    print(f"  Stage 1(LLM) -> 2(Rule) -> [Exit?] -> 3A(LLM)->3B(Code)->3C(LLM)->3D(Code) -> 4(Rule) -> 5(Code+LLM) -> 6(LLM+DB)")
    print(f"  Backend: Anthropic Claude API\n")

    results = []
    for idx, (_, row) in enumerate(df.iterrows()):
        try:
            result = run_single_case(llm, row, verbose=not args.quiet)
            results.append(result)
        except Exception as e:
            print(f"\n  FATAL on {row['VAERS_ID']}: {e}")
            traceback.print_exc()
            results.append({
                "vaers_id": row["VAERS_ID"],
                "condition_type": row.get("condition_type"),
                "group": row.get("group"),
                "errors": [{"stage": "fatal", "error": str(e)}],
                "early_exit": False,
            })

        if not args.quiet and (idx + 1) % 10 == 0:
            print(f"\n  >>> {idx+1}/{len(df)} completed <<<\n")

    save_results(results, tag=tag)
    print_summary_stats(results)

    # Generate individual reports for all runs (batch and single)
    generate_batch_reports(results)

    # Generate benchmark CSV (Haiku reasoning summaries)
    print("\n  Generating benchmark CSV with Haiku reasoning summaries...")
    generate_benchmark_csv(llm, results, tag=tag)

    # Single-case docx (if requested)
    if args.case and args.docx and results:
        md_path = os.path.join("reports", f"VAERS_{args.case}_v4.md")
        if os.path.exists(md_path):
            docx_path = render_docx(md_path)
            if docx_path:
                print(f"Word report: {docx_path}")


if __name__ == "__main__":
    main()
