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
  python main.py --resume           # Resume batch (skip already-completed cases)
  python main.py --backend medgemma # Use MedGemma 4B local backend
"""

import argparse
import csv
import gc
import json
import logging
import os
import re
import sys
import time
import threading
import traceback
from datetime import datetime, timedelta

# Windows UTF-8 console fix — also apply to stderr
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

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

# --- Batch logger (module-level, configured per run) ---
_batch_logger: logging.Logger | None = None

# Stage 1 timeout (seconds) — MedGemma can hang on long narratives
STAGE1_TIMEOUT_SEC = 300

# --- stdout broken-pipe guard ---
_stdout_broken = False


def _safe_print(*args, **kwargs):
    """Print wrapper that survives broken stdout pipes (Windows Errno 22).

    When stdout pipe breaks (e.g. buffer overflow in long MedGemma batches),
    this silently degrades to file-only logging instead of crashing the pipeline.
    All output is mirrored to _log() file handler for guaranteed persistence.
    """
    global _stdout_broken
    msg = " ".join(str(a) for a in args)

    # Always mirror to file log (immune to stdout issues)
    if msg.strip():
        _log(f"[verbose] {msg.strip()}")

    if _stdout_broken:
        return  # stdout dead — file log already captured above

    try:
        print(*args, **kwargs)
    except OSError:
        _stdout_broken = True
        _log("[stdout broken — switching to log-only mode]", "warning")


class _StageProgressIndicator:
    """Background thread that prints stage sub-step messages while LLM runs.

    Usage:
        indicator = _StageProgressIndicator(messages, interval=5.0)
        indicator.start()
        result = llm.query(...)   # blocking LLM call
        indicator.stop()
    """

    def __init__(self, messages: list[str], interval: float = 5.0):
        self._messages = messages
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self):
        for msg in self._messages:
            if self._stop_event.wait(timeout=self._interval):
                return  # LLM finished — stop printing
            _safe_print(f"    {msg}")


_STAGE1_PROGRESS_MESSAGES = [
    "Extracting demographics...",
    "Extracting vaccine information...",
    "Extracting clinical findings...",
    "Extracting medical history...",
    "Parsing structured output...",
]


def _setup_batch_logger(tag: str) -> logging.Logger:
    """Configure file + console logger for batch runs.

    File handler always uses UTF-8 and is immune to stdout pipe issues.
    Console handler is wrapped to survive broken pipes.
    """
    global _batch_logger
    os.makedirs("logs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join("logs", f"batch_{tag}_{timestamp}.log")

    logger = logging.getLogger("vax_beacon_batch")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # File handler — detailed, always safe (UTF-8 file I/O)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-5s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(fh)

    # Console handler — wrapped with error tolerance
    class _SafeStreamHandler(logging.StreamHandler):
        """StreamHandler that silently handles broken pipe errors."""
        def emit(self, record):
            try:
                super().emit(record)
            except OSError:
                global _stdout_broken
                _stdout_broken = True

    ch = _SafeStreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("  [LOG] %(message)s"))
    logger.addHandler(ch)

    logger.info(f"Batch log: {log_path}")
    _batch_logger = logger
    return logger


def _log(msg: str, level: str = "info"):
    """Log to batch logger if available. File handler is always safe."""
    if _batch_logger:
        getattr(_batch_logger, level, _batch_logger.info)(msg)


def _vram_status() -> tuple[float, float]:
    """Return (used_gb, total_gb). Returns (0, 0) if CUDA unavailable."""
    try:
        import torch
        if torch.cuda.is_available():
            used = torch.cuda.memory_allocated() / 1e9
            total = torch.cuda.get_device_properties(0).total_memory / 1e9
            return used, total
    except Exception:
        pass
    return 0.0, 0.0


def _cleanup_vram():
    """Post-case VRAM and memory cleanup with synchronization."""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()   # Wait for all CUDA ops to finish
            torch.cuda.empty_cache()   # Release cached memory back to allocator
    except Exception:
        pass


def _run_with_timeout(func, args=(), kwargs=None, timeout_sec=300):
    """Run func(*args, **kwargs) with a timeout. Returns (result, error_str|None)."""
    kwargs = kwargs or {}
    result_holder = [None]
    error_holder = [None]

    def _target():
        try:
            result_holder[0] = func(*args, **kwargs)
        except Exception as e:
            error_holder[0] = e

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout=timeout_sec)

    if thread.is_alive():
        return None, f"Timeout after {timeout_sec}s"
    if error_holder[0]:
        return None, str(error_holder[0])
    return result_holder[0], None


def _load_checkpoint(tag: str) -> set:
    """Load already-processed VAERS IDs from results JSON or streaming CSV."""
    processed = set()
    if not os.path.exists(RESULTS_PATH):
        return processed

    # Strategy 1: Load from results JSON (most reliable — has error info)
    json_candidates = sorted([
        f for f in os.listdir(RESULTS_PATH)
        if f.startswith(f"results_{tag}_") and f.endswith(".json")
    ])
    if json_candidates:
        latest = os.path.join(RESULTS_PATH, json_candidates[-1])
        try:
            with open(latest, "r", encoding="utf-8") as f:
                data = json.load(f)
            for r in data:
                vid = r.get("vaers_id")
                errors = r.get("errors", [])
                # Only skip if completed without errors
                if vid and not errors:
                    processed.add(int(vid))
            _log(f"Checkpoint (JSON): {len(processed)} completed cases from {latest}")
        except Exception as e:
            _log(f"Checkpoint JSON load failed: {e}", "warning")

    # Strategy 2: Also load from streaming CSVs (crash-resilient)
    csv_candidates = sorted([
        f for f in os.listdir(RESULTS_PATH)
        if f.startswith(f"streaming_{tag}_") and f.endswith(".csv")
    ])
    for csv_file in csv_candidates:
        csv_path = os.path.join(RESULTS_PATH, csv_file)
        try:
            import csv as csv_mod
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv_mod.DictReader(f)
                for row in reader:
                    vid = row.get("vaers_id", "").strip()
                    errors = row.get("errors", "0").strip()
                    # Only skip if completed without errors
                    if vid and errors == "0":
                        try:
                            processed.add(int(vid))
                        except ValueError:
                            pass
            _log(f"Checkpoint (CSV): loaded from {csv_file}, total={len(processed)}")
        except Exception as e:
            _log(f"Checkpoint CSV load failed ({csv_file}): {e}", "warning")

    if processed:
        _log(f"Checkpoint total: {len(processed)} completed cases to skip")
    return processed


# --- Narrative truncation for long VAERS texts (MedGemma token budget) ---
_CLINICAL_KW_RE = re.compile(
    r"troponin|ecg|ekg|echo|mri|catheter|biopsy|ejection.fraction|"
    r"chest.pain|dyspnea|palpitation|fever|arrhythmia|edema|bnp|crp|d.dimer",
    re.IGNORECASE,
)

_NARRATIVE_MAX_CHARS = 2000
_NARRATIVE_TARGET_CHARS = 1500


def _truncate_narrative(text: str) -> str:
    """Truncate long narratives by removing non-clinical sentences first.

    If text <= 2000 chars, return as-is.
    Otherwise, split into sentences, keep all sentences containing clinical
    keywords, drop the rest (shortest first) until <= 1500 chars.
    """
    if len(text) <= _NARRATIVE_MAX_CHARS:
        return text

    # Split on sentence boundaries (period/newline followed by space or EOL)
    sentences = re.split(r'(?<=[.!?\n])\s+', text.strip())
    if not sentences:
        return text[:_NARRATIVE_TARGET_CHARS]

    # Partition: clinical (must keep) vs non-clinical (can drop)
    clinical = []
    non_clinical = []
    for s in sentences:
        if _CLINICAL_KW_RE.search(s):
            clinical.append(s)
        else:
            non_clinical.append(s)

    # If clinical sentences alone exceed target, return them truncated
    clinical_text = " ".join(clinical)
    if len(clinical_text) >= _NARRATIVE_TARGET_CHARS:
        _log(f"Narrative truncated: {len(text)} -> {_NARRATIVE_TARGET_CHARS} chars (clinical overflow)")
        return clinical_text[:_NARRATIVE_TARGET_CHARS]

    # Sort non-clinical by length DESC — drop longest first (least info-dense)
    non_clinical.sort(key=len, reverse=True)

    # Add non-clinical sentences back until we'd exceed target
    kept = list(clinical)
    budget = _NARRATIVE_TARGET_CHARS - len(clinical_text)
    for s in non_clinical:
        if len(s) + 1 <= budget:  # +1 for joining space
            kept.append(s)
            budget -= len(s) + 1

    result = " ".join(kept)
    if len(result) < len(text):
        _log(f"Narrative truncated: {len(text)} -> {len(result)} chars")
    return result


# --- Streaming CSV writer: append + flush per case ---
_SUMMARY_CSV_COLUMNS = [
    "vaers_id", "condition_type", "group", "early_exit",
    "brighton_level", "who_step1_conclusion", "max_nci", "dominant_alternative",
    "temporal_zone", "days_to_onset", "known_ae", "who_step2_met", "high_risk",
    "who_category", "confidence", "risk_signal",
    "errors", "total_time_s",
    "gt_group", "gt_severity", "gt_onset_days",
]


class _StreamingCSVWriter:
    """Write summary CSV rows incrementally with flush after each row."""

    def __init__(self, path: str):
        self.path = path
        self._file = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=_SUMMARY_CSV_COLUMNS)
        self._writer.writeheader()
        self._file.flush()

    def write_row(self, result: dict):
        """Extract summary fields from a pipeline result and write one CSV row."""
        s5 = result.get("stages", {}).get("stage5_causality", {})
        s2 = result.get("stages", {}).get("stage2_brighton", {})
        s3 = result.get("stages", {}).get("stage3_ddx", {})
        s4 = result.get("stages", {}).get("stage4_temporal", {})
        s6 = result.get("stages", {}).get("stage6_guidance", {})
        gt = result.get("ground_truth", {})

        who_cat = s5.get("who_category") or s6.get("who_category", "ERROR")

        row = {
            "vaers_id": result.get("vaers_id"),
            "condition_type": result.get("condition_type"),
            "group": result.get("group"),
            "early_exit": result.get("early_exit", False),
            "brighton_level": s2.get("brighton_level"),
            "who_step1_conclusion": s3.get("who_step1_conclusion"),
            "max_nci": s3.get("max_nci_score"),
            "dominant_alternative": s3.get("dominant_alternative"),
            "temporal_zone": s4.get("temporal_assessment", {}).get("temporal_zone"),
            "days_to_onset": s4.get("temporal_assessment", {}).get("days_to_onset"),
            "known_ae": s4.get("known_ae_assessment", {}).get("is_known_ae"),
            "who_step2_met": s4.get("who_step2_met"),
            "high_risk": s4.get("high_risk_group", {}).get("is_high_risk"),
            "who_category": who_cat,
            "confidence": s5.get("confidence"),
            "risk_signal": s6.get("overall_risk_signal"),
            "errors": len(result.get("errors", [])),
            "total_time_s": result.get("processing_time", {}).get("total"),
            "gt_group": gt.get("group"),
            "gt_severity": gt.get("curated_severity"),
            "gt_onset_days": gt.get("curated_onset_days"),
        }
        self._writer.writerow(row)
        self._file.flush()

    def close(self):
        if self._file and not self._file.closed:
            self._file.close()


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
        _safe_print(f"\n{'='*60}")
        _safe_print(f"  VAERS ID: {vaers_id} | {condition_type} | Group: {row.get('group', '?')}")
        _safe_print(f"{'='*60}")

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

    # Truncate long narratives for MedGemma token budget
    if llm.backend == "medgemma":
        original_len = len(case_text)
        case_text = _truncate_narrative(case_text)
        if len(case_text) < original_len and verbose:
            _safe_print(f"  [Truncate] {original_len} -> {len(case_text)} chars")

    # ==================================================================
    # Phase 1: Data Preprocessing & Diagnosis Filtering
    # ==================================================================

    # --- Stage 1: ICSR Extraction (LLM) — Data Intake ---
    indicator = None
    try:
        t0 = time.time()
        if verbose:
            _safe_print(f"  [Stage 1] ICSR Extractor (LLM)...")
            indicator = _StageProgressIndicator(_STAGE1_PROGRESS_MESSAGES, interval=5.0)
            indicator.start()
        # MedGemma: time limit is enforced inside model.generate() via
        # _TimeLimitCriteria (StoppingCriteria), so no external thread timeout needed.
        # This prevents zombie CUDA threads that cause intermittent hangs.
        result["stages"]["stage1_icsr"] = run_stage1(llm, case_text)
        result["processing_time"]["stage1"] = round(time.time() - t0, 2)
        if indicator:
            indicator.stop()
        if verbose:
            _safe_print(f"  [Stage 1] OK ({result['processing_time']['stage1']}s)")
        _log(f"VAERS {vaers_id} | Stage 1 | {result['processing_time']['stage1']}s | OK")
    except Exception as e:
        if indicator:
            indicator.stop()
        elapsed = round(time.time() - t0, 2)
        result["processing_time"]["stage1"] = elapsed
        result["errors"].append({"stage": 1, "error": str(e), "traceback": traceback.format_exc()})
        _log(f"VAERS {vaers_id} | Stage 1 | {elapsed}s | FAIL: {e}", "error")
        if verbose:
            _safe_print(f"  [Stage 1] FAIL: {e}")
        return result

    # --- Stage 2: Clinical Validator (Rule) — WHO Step 0: Valid Diagnosis ---
    try:
        t0 = time.time()
        if verbose:
            _safe_print(f"  [Stage 2] Clinical Validator (Rule)...", end=" ", flush=True)
        result["stages"]["stage2_brighton"] = run_stage2(result["stages"]["stage1_icsr"])
        result["processing_time"]["stage2"] = round(time.time() - t0, 2)
        brighton_lvl = result["stages"]["stage2_brighton"]["brighton_level"]
        early_exit = result["stages"]["stage2_brighton"]["early_exit"]
        _log(f"VAERS {vaers_id} | Stage 2 | {result['processing_time']['stage2']}s | Brighton L{brighton_lvl}{' EARLY_EXIT' if early_exit else ''}")
        if verbose:
            tag = " >> EARLY EXIT" if early_exit else ""
            _safe_print(f"OK -> Brighton L{brighton_lvl} ({result['processing_time']['stage2']}s){tag}")
    except Exception as e:
        result["errors"].append({"stage": 2, "error": str(e), "traceback": traceback.format_exc()})
        _log(f"VAERS {vaers_id} | Stage 2 | FAIL: {e}", "error")
        if verbose:
            _safe_print(f"FAIL: {e}")
        return result

    # --- EARLY EXIT: Brighton L4 → Skip to Stage 6 ---
    if early_exit:
        result["early_exit"] = True
        try:
            t0 = time.time()
            if verbose:
                _safe_print(f"  [Stage 6] Brighton Exit Guidance (LLM)...", end=" ", flush=True)
            result["stages"]["stage6_guidance"] = run_stage6(
                llm,
                result["stages"]["stage1_icsr"],
                result["stages"]["stage2_brighton"],
                early_exit=True,
            )
            result["processing_time"]["stage6"] = round(time.time() - t0, 2)
            s6_who = result["stages"]["stage6_guidance"].get("who_category", "Unclassifiable")
            _log(f"VAERS {vaers_id} | Stage 6 (exit) | {result['processing_time']['stage6']}s | WHO={s6_who}")
            if verbose:
                _safe_print(f"OK -> WHO: {s6_who} ({result['processing_time']['stage6']}s)")
        except Exception as e:
            elapsed6 = round(time.time() - t0, 2)
            result["processing_time"]["stage6"] = elapsed6
            result["errors"].append({"stage": 6, "error": str(e), "traceback": traceback.format_exc()})
            _log(f"VAERS {vaers_id} | Stage 6 (exit) | FAIL (fallback): {e}", "error")
            result["stages"]["stage6_guidance"] = {
                "who_category": "Unclassifiable",
                "investigation_gaps": ["Guidance generation failed — LLM error."],
                "recommended_actions": [
                    "Obtain cardiac MRI or troponin results to upgrade Brighton level.",
                    "Re-run pipeline when system resources are available.",
                ],
                "officer_summary": "Brighton L4 — insufficient diagnostic evidence. "
                                   "Manual review recommended.",
            }
            if verbose:
                _safe_print(f"FALLBACK ({elapsed6}s)")

        total = sum(result["processing_time"].values())
        result["processing_time"]["total"] = round(total, 2)
        if verbose:
            _safe_print(f"  -- Early Exit: WHO=Unclassifiable, Brighton=L4, Time={total:.1f}s")
        return result

    # ==================================================================
    # Phase 2: Mechanistic Investigation
    # ==================================================================

    # --- Stage 3: DDx Two-Pass (v4) — WHO Step 1: Other Causes? ---
    # Each sub-stage has individual fallback to prevent cascade failures
    _EMPTY_3A = {"clinical_observations": {}, "demographics": {}, "key_negatives": []}
    _EMPTY_3B = {"match_summary": {"total_candidates": 0, "total_matched_indicators": 0}, "matched_ddx": {}}

    t3a = t3b = t3c = t3d = 0.0

    # Stage 3A: Clinical Observer (LLM) — fallback: empty observations
    try:
        t0 = time.time()
        if verbose:
            _safe_print(f"  [Stage 3A] Clinical Observer (LLM)...", end=" ", flush=True)
        stage3a = run_stage3a(llm, case_text)
        t3a = round(time.time() - t0, 2)
        if verbose:
            obs_count = sum(len(v) for v in stage3a.get("clinical_observations", {}).values())
            _safe_print(f"OK -> {obs_count} observations ({t3a}s)")
    except Exception as e:
        stage3a = _EMPTY_3A
        t3a = round(time.time() - t0, 2)
        result["errors"].append({"stage": "3A", "error": str(e), "traceback": traceback.format_exc()})
        _log(f"VAERS {vaers_id} | Stage 3A | FAIL (fallback: empty obs): {e}", "error")
        if verbose:
            _safe_print(f"FALLBACK ({t3a}s) — empty observations")

    # Stage 3B: DDx Matcher (Code) — fallback: empty matches
    try:
        if verbose:
            _safe_print(f"  [Stage 3B] DDx Matcher (Code)...", end=" ", flush=True)
        t0b = time.time()
        stage3b = run_stage3b(stage3a, _KNOWLEDGE_DB["ddx"])
        t3b = round(time.time() - t0b, 2)
        if verbose:
            n_cand = stage3b["match_summary"]["total_candidates"]
            n_match = stage3b["match_summary"]["total_matched_indicators"]
            _safe_print(f"OK -> {n_cand} candidates, {n_match} matched ({t3b}s)")
    except Exception as e:
        stage3b = _EMPTY_3B
        t3b = round(time.time() - t0b, 2)
        result["errors"].append({"stage": "3B", "error": str(e), "traceback": traceback.format_exc()})
        _log(f"VAERS {vaers_id} | Stage 3B | FAIL (fallback: empty matches): {e}", "error")
        if verbose:
            _safe_print(f"FALLBACK ({t3b}s)")

    # Stage 3C: Plausibility Assessor (LLM) — fallback: empty assessments
    try:
        if verbose:
            _safe_print(f"  [Stage 3C] Plausibility Assessor (LLM)...", end=" ", flush=True)
        t0c = time.time()
        stage3c = run_stage3c(llm, case_text, stage3a, stage3b, _KNOWLEDGE_DB["ddx"])
        t3c = round(time.time() - t0c, 2)
        if verbose:
            present_count = sum(1 for v in stage3c.values() if v.get("present"))
            _safe_print(f"OK -> {present_count} markers present ({t3c}s)")
    except Exception as e:
        stage3c = {}
        t3c = round(time.time() - t0c, 2)
        result["errors"].append({"stage": "3C", "error": str(e), "traceback": traceback.format_exc()})
        _log(f"VAERS {vaers_id} | Stage 3C | FAIL (fallback: empty plausibility): {e}", "error")
        if verbose:
            _safe_print(f"FALLBACK ({t3c}s)")

    # Stage 3D: NCI Calculator (Code) — always succeeds on valid 3C input
    try:
        if verbose:
            _safe_print(f"  [Stage 3D] NCI Calculator (Code)...", end=" ", flush=True)
        t0d = time.time()
        stage3d = run_stage3d(stage3c, _KNOWLEDGE_DB["ddx"])
        t3d = round(time.time() - t0d, 2)

        s1_vaers_id = result["stages"]["stage1_icsr"].get("vaers_id", vaers_id)
        result["stages"]["stage3_ddx"] = merge_stage3(
            stage3a, stage3b, stage3c, stage3d, vaers_id=s1_vaers_id,
        )
        result["processing_time"]["stage3"] = round(t3a + t3b + t3c + t3d, 2)
        max_nci = result["stages"]["stage3_ddx"].get("max_nci_score", "?")
        step1 = result["stages"]["stage3_ddx"].get("who_step1_conclusion", "?")
        _log(f"VAERS {vaers_id} | Stage 3 | {result['processing_time']['stage3']}s | NCI={max_nci} Step1={step1}")
        if verbose:
            _safe_print(f"OK -> NCI={max_nci}, Step1={step1} ({t3d}s)")
    except Exception as e:
        result["errors"].append({"stage": "3D", "error": str(e), "traceback": traceback.format_exc()})
        _log(f"VAERS {vaers_id} | Stage 3D | FAIL: {e}", "error")
        if verbose:
            _safe_print(f"FAIL: {e}")

    # --- Stage 4: Auditor — Known AE + Temporal (Rule) — WHO Step 2 ---
    try:
        t0 = time.time()
        if verbose:
            _safe_print(f"  [Stage 4] Auditor — Known AE + Temporal (Rule)...", end=" ", flush=True)
        result["stages"]["stage4_temporal"] = run_stage4(
            result["stages"]["stage1_icsr"],
            result["stages"]["stage2_brighton"],
            result["stages"].get("stage3_ddx", {}),
        )
        result["processing_time"]["stage4"] = round(time.time() - t0, 2)
        zone = result["stages"]["stage4_temporal"]["temporal_assessment"]["temporal_zone"]
        days = result["stages"]["stage4_temporal"]["temporal_assessment"]["days_to_onset"]
        known = result["stages"]["stage4_temporal"]["known_ae_assessment"]["is_known_ae"]
        _log(f"VAERS {vaers_id} | Stage 4 | {result['processing_time']['stage4']}s | {zone} ({days}d) KnownAE={known}")
        if verbose:
            _safe_print(f"OK -> {zone} ({days}d), KnownAE={known} ({result['processing_time']['stage4']}s)")
    except Exception as e:
        result["errors"].append({"stage": 4, "error": str(e), "traceback": traceback.format_exc()})
        _log(f"VAERS {vaers_id} | Stage 4 | FAIL: {e}", "error")
        if verbose:
            _safe_print(f"FAIL: {e}")

    # ==================================================================
    # Phase 3: Judgment & Reporting
    # ==================================================================

    # --- Stage 5: Causality Assessor (Code+LLM) — WHO Step 3 & 4 ---
    # Fallback: deterministic classify() always succeeds; LLM reasoning is optional
    try:
        t0 = time.time()
        if verbose:
            _safe_print(f"  [Stage 5] Causality Assessor (Code+LLM)...", end=" ", flush=True)
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
        _log(f"VAERS {vaers_id} | Stage 5 | {result['processing_time']['stage5']}s | WHO={who_cat}")
        if verbose:
            _safe_print(f"OK -> WHO: {who_cat} ({result['processing_time']['stage5']}s)")
    except Exception as e:
        elapsed5 = round(time.time() - t0, 2)
        result["processing_time"]["stage5"] = elapsed5
        result["errors"].append({"stage": 5, "error": str(e), "traceback": traceback.format_exc()})
        _log(f"VAERS {vaers_id} | Stage 5 | FAIL (fallback: deterministic only): {e}", "error")
        # Fallback: run classify() without LLM reasoning
        from pipeline.stage5_causality_assessor import classify
        _b = result["stages"].get("stage2_brighton", {})
        _d = result["stages"].get("stage3_ddx", {})
        _t = result["stages"].get("stage4_temporal", {})
        _who, _chain = classify(
            brighton_level=_b.get("brighton_level", 4),
            max_nci=_d.get("max_nci_score", 0) or 0,
            known_ae=_t.get("known_ae_assessment", {}).get("is_known_ae", False),
            temporal_met=_t.get("who_step2_met", False),
            temporal_zone=_t.get("temporal_assessment", {}).get("temporal_zone", "UNKNOWN"),
            who_step1_conclusion=_d.get("who_step1_conclusion", "NO_ALTERNATIVE"),
            epistemic_uncertainty=_d.get("epistemic_uncertainty", 0) or 0,
        )
        result["stages"]["stage5_causality"] = {
            "who_category": _who,
            "decision_chain": _chain,
            "confidence": "LOW",
            "reasoning": f"LLM reasoning unavailable ({e}). Classification by deterministic decision tree only.",
            "classification_source": "DETERMINISTIC_FALLBACK",
        }
        if verbose:
            _safe_print(f"FALLBACK -> WHO: {_who} ({elapsed5}s)")

    # --- Stage 6: Guidance Advisor (LLM) — Reporting ---
    # Fallback: minimal guidance template if LLM fails
    try:
        t0 = time.time()
        if verbose:
            _safe_print(f"  [Stage 6] Guidance Advisor (LLM)...", end=" ", flush=True)
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
        _log(f"VAERS {vaers_id} | Stage 6 | {result['processing_time']['stage6']}s | OK")
        if verbose:
            _safe_print(f"OK ({result['processing_time']['stage6']}s)")
    except Exception as e:
        elapsed6 = round(time.time() - t0, 2)
        result["processing_time"]["stage6"] = elapsed6
        result["errors"].append({"stage": 6, "error": str(e), "traceback": traceback.format_exc()})
        _log(f"VAERS {vaers_id} | Stage 6 | FAIL (fallback: minimal guidance): {e}", "error")
        _who = result["stages"].get("stage5_causality", {}).get("who_category", "Unclassifiable")
        result["stages"]["stage6_guidance"] = {
            "who_category": _who,
            "investigation_gaps": ["Full guidance unavailable — LLM error during generation."],
            "recommended_actions": [
                "Review raw clinical data and Brighton classification manually.",
                "Re-run pipeline when system resources are available.",
            ],
            "officer_summary": f"WHO category {_who} assigned by deterministic pipeline. "
                               "Automated guidance generation failed; manual review recommended.",
        }
        if verbose:
            _safe_print(f"FALLBACK ({elapsed6}s)")

    # --- Summary ---
    total = sum(result["processing_time"].values())
    result["processing_time"]["total"] = round(total, 2)
    if verbose:
        who_cat = result["stages"].get("stage5_causality", {}).get("who_category", "N/A")
        brighton = result["stages"].get("stage2_brighton", {}).get("brighton_level", "N/A")
        known = result["stages"].get("stage4_temporal", {}).get("known_ae_assessment", {}).get("is_known_ae", "?")
        _safe_print(f"  -- Complete: WHO={who_cat}, Brighton=L{brighton}, KnownAE={known}, Time={total:.1f}s")

    n_errors = len(result.get("errors", []))
    who_final = (result["stages"].get("stage5_causality", {}).get("who_category")
                 or result["stages"].get("stage6_guidance", {}).get("who_category", "N/A"))
    _log(f"VAERS {vaers_id} | DONE | {total:.1f}s | WHO={who_final} | Errors={n_errors}")

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
    _safe_print(f"\nFull results: {json_path}")

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
    _safe_print(f"Summary CSV: {csv_path}")

    return json_path, csv_path


def _save_incremental(results: list, tag: str):
    """Save intermediate results for crash recovery (overwrites same file)."""
    os.makedirs(RESULTS_PATH, exist_ok=True)
    path = os.path.join(RESULTS_PATH, f"results_{tag}_incremental.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str, ensure_ascii=False)
        _log(f"Incremental save: {len(results)} cases -> {path}")
    except Exception as e:
        _log(f"Incremental save failed: {e}", "warning")


def print_summary_stats(results: list):
    """Print aggregate statistics."""
    total = len(results)
    early_exits = sum(1 for r in results if r.get("early_exit"))
    errors = sum(len(r.get("errors", [])) for r in results)

    _safe_print(f"\n{'='*60}")
    _safe_print(f"  Vax-Beacon v4 Pipeline Summary")
    _safe_print(f"  WHO AEFI Digital Manual Architecture (Deterministic Refactoring)")
    _safe_print(f"{'='*60}")
    _safe_print(f"  Total: {total} | Early Exit(L4): {early_exits} | Full Pipeline: {total - early_exits} | Errors: {errors}")

    # WHO Categories
    who_cats = {}
    for r in results:
        s5 = r.get("stages", {}).get("stage5_causality", {})
        s6 = r.get("stages", {}).get("stage6_guidance", {})
        cat = s5.get("who_category") or s6.get("who_category", "ERROR")
        who_cats[cat] = who_cats.get(cat, 0) + 1
    _safe_print(f"\n  WHO Category Distribution:")
    for cat in sorted(who_cats.keys()):
        count = who_cats[cat]
        pct = count / total * 100
        bar = "█" * int(pct / 2)
        _safe_print(f"    {cat:5s}: {count:3d} ({pct:5.1f}%) {bar}")

    # Brighton Levels
    brighton = {}
    for r in results:
        lvl = r.get("stages", {}).get("stage2_brighton", {}).get("brighton_level", "?")
        brighton[lvl] = brighton.get(lvl, 0) + 1
    _safe_print(f"\n  Brighton Level Distribution:")
    for lvl in sorted(brighton.keys(), key=str):
        _safe_print(f"    Level {lvl}: {brighton[lvl]}")

    # Known AE check
    known_ae_count = sum(
        1 for r in results
        if r.get("stages", {}).get("stage4_temporal", {}).get("known_ae_assessment", {}).get("is_known_ae")
    )
    _safe_print(f"\n  Known AE (Established): {known_ae_count} cases")
    _safe_print(f"  Early Exit (Brighton L4): {early_exits} cases")

    # Timing
    times = [r.get("processing_time", {}).get("total", 0) for r in results]
    if times:
        full_times = [t for t, r in zip(times, results) if not r.get("early_exit")]
        exit_times = [t for t, r in zip(times, results) if r.get("early_exit")]
        _safe_print(f"\n  Processing Time:")
        _safe_print(f"    Full pipeline mean: {sum(full_times)/max(len(full_times),1):.1f}s/case")
        if exit_times:
            _safe_print(f"    Early exit mean: {sum(exit_times)/len(exit_times):.1f}s/case")
        _safe_print(f"    Total: {sum(times):.0f}s ({sum(times)/60:.1f}min)")


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
            _safe_print(f"  [Benchmark] {i+1}/{total} reasoning summaries generated")

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
    _safe_print(f"\nBenchmark CSV: {csv_path}")
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
            _safe_print(f"  [Report] Error on VAERS {r.get('vaers_id', '?')}: {e}")
            errors += 1
    _safe_print(f"\nReports: {count} generated, {errors} errors → reports/")


def main():
    parser = argparse.ArgumentParser(description="Vax-Beacon v4 — WHO AEFI Digital Manual (Deterministic)")
    parser.add_argument("--sample", type=int, default=0, help="N cases per group (test)")
    parser.add_argument("--case", type=int, default=0, help="Single VAERS_ID")
    parser.add_argument("--group", type=str, default="", help="Group filter (G1/G2/G3/clean/confounded)")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    parser.add_argument("--docx", action="store_true", help="Also generate Word report")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Launch interactive case selection mode")
    parser.add_argument("--backend", type=str, default="medgemma",
                        choices=["anthropic", "medgemma"],
                        help="LLM backend (default: medgemma)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume batch: skip cases already in latest results JSON")
    args = parser.parse_args()

    llm = LLMClient(backend=args.backend)
    df = load_vaers_data()

    # Interactive mode takes priority
    if args.interactive:
        try:
            run_interactive(llm, df)
        except KeyboardInterrupt:
            _safe_print("\n\n  Interrupted. Goodbye!\n")
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

    _safe_print(f"\n  Vax-Beacon v4 | WHO AEFI Digital Manual (Deterministic)")
    _safe_print(f"  {len(df)} cases | tag: {tag}")
    _safe_print(f"  Architecture: Two-Pass DDx + Deterministic Classification + Knowledge DB")
    _safe_print(f"  Stage 1(LLM) -> 2(Rule) -> [Exit?] -> 3A(LLM)->3B(Code)->3C(LLM)->3D(Code) -> 4(Rule) -> 5(Code+LLM) -> 6(LLM+DB)")
    backend_label = "MedGemma 4B (local)" if args.backend == "medgemma" else "Anthropic Claude API"
    _safe_print(f"  Backend: {backend_label}\n")

    # --- Setup batch logging and checkpoint ---
    is_batch = len(df) > 1
    if is_batch:
        logger = _setup_batch_logger(tag)
        logger.info(f"Batch start: {len(df)} cases | tag={tag} | backend={args.backend}")

    # Checkpoint/resume: skip already-processed cases
    checkpoint_ids = set()
    if is_batch and args.resume:
        checkpoint_ids = _load_checkpoint(tag)
        if checkpoint_ids:
            _safe_print(f"  Checkpoint: skipping {len(checkpoint_ids)} already-processed cases")

    batch_start = time.time()
    results = []
    failed_cases = []  # (vaers_id, stage, error_msg)
    n_success = 0
    n_skipped = 0

    # --- Streaming CSV: open writer before loop, flush per case ---
    streaming_csv = None
    if is_batch:
        os.makedirs(RESULTS_PATH, exist_ok=True)
        timestamp_csv = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_stream_path = os.path.join(RESULTS_PATH, f"streaming_{tag}_{timestamp_csv}.csv")
        streaming_csv = _StreamingCSVWriter(csv_stream_path)
        _log(f"Streaming CSV: {csv_stream_path}")
        _safe_print(f"  Streaming CSV: {csv_stream_path}")

    for idx, (_, row) in enumerate(df.iterrows()):
        vid = row["VAERS_ID"]

        # Skip checkpoint cases
        if int(vid) in checkpoint_ids:
            n_skipped += 1
            if not args.quiet:
                _safe_print(f"\n  [SKIP] VAERS {vid} (already processed)")
            _log(f"[{idx+1}/{len(df)}] VAERS {vid} | SKIPPED (checkpoint)")
            continue

        try:
            _log(f"[{idx+1}/{len(df)}] VAERS {vid} | START")
            result = run_single_case(llm, row, verbose=not args.quiet)
            results.append(result)

            # Track success/failure
            case_errors = result.get("errors", [])
            if case_errors:
                for err in case_errors:
                    failed_cases.append((vid, err.get("stage", "?"), err.get("error", "?")))
            else:
                n_success += 1

            # Streaming CSV: write + flush immediately
            if streaming_csv:
                streaming_csv.write_row(result)

        except Exception as e:
            tb_str = traceback.format_exc()
            _safe_print(f"\n  FATAL on {vid}: {e}")
            traceback.print_exc()
            _log(f"[{idx+1}/{len(df)}] VAERS {vid} | FATAL: {e}\n{tb_str}", "error")
            fatal_result = {
                "vaers_id": vid,
                "condition_type": row.get("condition_type"),
                "group": row.get("group"),
                "stages": {},
                "ground_truth": {},
                "errors": [{"stage": "fatal", "error": str(e), "traceback": tb_str}],
                "processing_time": {},
                "early_exit": False,
            }
            results.append(fatal_result)
            failed_cases.append((vid, "fatal", str(e)))
            # Streaming CSV: write fatal case too
            if streaming_csv:
                streaming_csv.write_row(fatal_result)

        # --- Per-case VRAM cleanup ---
        if llm.backend == "medgemma":
            _cleanup_vram()

        # --- Every 10 cases: progress summary + VRAM check ---
        completed = idx + 1
        if is_batch and completed % 10 == 0:
            elapsed = time.time() - batch_start
            processed = len(results)
            remaining = len(df) - completed - n_skipped
            avg_time = elapsed / max(processed, 1)
            eta = datetime.now() + timedelta(seconds=avg_time * remaining)

            progress_msg = (
                f">>> Progress: {completed}/{len(df)} | "
                f"Success={n_success} Fail={len(failed_cases)} Skip={n_skipped} | "
                f"Elapsed={elapsed/60:.1f}min | Avg={avg_time:.1f}s/case | "
                f"ETA={eta.strftime('%H:%M')}"
            )
            if not args.quiet:
                _safe_print(f"\n  {progress_msg}\n")
            _log(progress_msg)

            # VRAM check
            if llm.backend == "medgemma":
                used, total_vram = _vram_status()
                vram_msg = f"VRAM: {used:.2f} / {total_vram:.1f} GB ({used/max(total_vram,0.1)*100:.0f}%)"
                _log(vram_msg)
                if used > 5.5:
                    _log(f"WARNING: VRAM usage high ({used:.2f} GB > 5.5 GB threshold)", "warning")

        # --- Incremental save every 25 cases (crash protection) ---
        if is_batch and len(results) > 0 and len(results) % 25 == 0:
            _save_incremental(results, tag)

    # --- Close streaming CSV ---
    if streaming_csv:
        streaming_csv.close()
        _log(f"Streaming CSV closed: {len(results)} rows written")

    # --- Final save & summary ---
    save_results(results, tag=tag)
    print_summary_stats(results)

    # Batch failure report
    if failed_cases:
        _safe_print(f"\n{'='*60}")
        _safe_print(f"  FAILED CASES ({len(failed_cases)})")
        _safe_print(f"{'='*60}")
        for vid, stage, err_msg in failed_cases:
            _safe_print(f"    VAERS {vid} | Stage {stage} | {err_msg[:100]}")
            _log(f"FAILED: VAERS {vid} | Stage {stage} | {err_msg}", "error")

    if is_batch:
        total_elapsed = time.time() - batch_start
        summary_msg = (
            f"Batch complete: {len(results)} processed, "
            f"{n_success} success, {len(failed_cases)} failed, {n_skipped} skipped, "
            f"{total_elapsed/60:.1f} min total"
        )
        _log(summary_msg)
        _safe_print(f"\n  {summary_msg}")

    # Generate individual reports for all runs (batch and single)
    generate_batch_reports(results)

    # Generate benchmark CSV (Haiku reasoning summaries) — skip for MedGemma
    if args.backend != "medgemma":
        _safe_print("\n  Generating benchmark CSV with Haiku reasoning summaries...")
        generate_benchmark_csv(llm, results, tag=tag)
    else:
        _safe_print("\n  Skipping benchmark CSV (MedGemma backend — no Haiku available)")

    # Single-case docx (if requested)
    if args.case and args.docx and results:
        md_path = os.path.join("reports", f"VAERS_{args.case}_v4.md")
        if os.path.exists(md_path):
            docx_path = render_docx(md_path)
            if docx_path:
                _safe_print(f"Word report: {docx_path}")


if __name__ == "__main__":
    main()
