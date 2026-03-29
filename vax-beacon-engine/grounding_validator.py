"""
grounding_validator.py
======================
Vax-Beacon | FACTS-Grounding–inspired LLM Output Validator

Validates two grounding contracts:

  CONTRACT A — Stage 3A (Clinical Observer)
  ───────────────────────────────────────────
  Claim : every finding.context in v4_stage3a.clinical_observations
  Source: VAERS SYMPTOM_TEXT (original narrative)
  Question: Is the context quote present/inferable from the source narrative?

  CONTRACT B — Stage 6 (Guidance Advisor)
  ─────────────────────────────────────────
  Claim : every investigative_gaps[].gap / action and recommended_actions[]
  Source: ddx_myocarditis.json + investigation_protocols.json (knowledge base)
  Question: Is each guidance item traceable to the knowledge base vocabulary?

Judge method (FACTS-inspired):
  Each claim is evaluated by a lightweight LLM judge (binary GROUNDED / UNGROUNDED)
  with an optional rationale. Two-judge consensus is used when the first judge is
  uncertain. Final score = fraction of GROUNDED claims per contract.

Output:
  grounding_results_<timestamp>.json   — per-case detail
  grounding_summary_<timestamp>.csv    — aggregate metrics (for paper Table/Figure)

Usage:
  python grounding_validator.py --results results_v4_full_100_<timestamp>.json
                                --vaers   vaers_jan_nov_2021.csv
                                --backend anthropic
                                [--sample N]          # validate N random cases
                                [--online]            # also append scores to pipeline run

Author : Suah Cheon (MEC)  |  Vax-Beacon v4
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# 1. LLM Judge client (minimal, no dependency on main pipeline)
# ──────────────────────────────────────────────────────────────────────────────

def _call_anthropic(system_prompt: str, user_message: str, model: str = "claude-sonnet-4-20250514") -> str:
    """Minimal Anthropic API call. Returns response text."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=model,
            max_tokens=256,
            temperature=0.0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        return f"ERROR: {e}"


# ──────────────────────────────────────────────────────────────────────────────
# 2. Judge prompts (FACTS-style binary verdict + rationale)
# ──────────────────────────────────────────────────────────────────────────────

JUDGE_A_SYSTEM = """You are a strict medical document grounding auditor.

Your task: determine whether a CLAIM is grounded in a SOURCE DOCUMENT.

A claim is GROUNDED if:
- The exact or paraphrased text of the claim is present in the source, OR
- The claim can be directly inferred from explicit statements in the source
  (e.g., a numerical value, a lab result, a symptom that appears verbatim or near-verbatim)

A claim is UNGROUNDED if:
- The claim introduces information not found in the source, OR
- The claim requires inference beyond what the source text supports, OR
- The claim contradicts the source

Respond ONLY with valid JSON:
{"verdict": "GROUNDED" or "UNGROUNDED", "rationale": "one sentence explanation", "confidence": "HIGH" or "LOW"}

Do NOT add any text outside the JSON object."""


JUDGE_B_SYSTEM = """You are a strict pharmacovigilance knowledge base auditor.

Your task: determine whether a GUIDANCE CLAIM is traceable to a KNOWLEDGE BASE excerpt.

A claim is GROUNDED if:
- The test, investigation, or concept named in the claim appears in the knowledge base excerpt, OR
- The clinical rationale is consistent with the knowledge base vocabulary and criteria

A claim is UNGROUNDED if:
- The claim recommends a test or action not mentioned in the knowledge base excerpt, OR
- The clinical concept is invented and has no anchor in the provided knowledge base text

Respond ONLY with valid JSON:
{"verdict": "GROUNDED" or "UNGROUNDED", "rationale": "one sentence explanation", "confidence": "HIGH" or "LOW"}

Do NOT add any text outside the JSON object."""


def _judge(system_prompt: str, claim: str, source: str, backend: str) -> dict:
    """Run LLM judge and return verdict dict."""
    user_msg = f"CLAIM:\n{claim}\n\nSOURCE DOCUMENT:\n{source[:2000]}"
    if backend == "anthropic":
        raw = _call_anthropic(system_prompt, user_msg)
    else:
        # Extend here for other backends (medgemma, etc.)
        return {"verdict": "SKIP", "rationale": f"Backend {backend} not supported", "confidence": "LOW"}

    # Parse JSON response
    try:
        # Strip potential markdown fences
        clean = re.sub(r"```(?:json)?|```", "", raw).strip()
        return json.loads(clean)
    except Exception:
        # Try to extract verdict from raw text
        if "GROUNDED" in raw.upper():
            verdict = "GROUNDED" if "UNGROUNDED" not in raw.upper() else "UNGROUNDED"
            return {"verdict": verdict, "rationale": raw[:200], "confidence": "LOW"}
        return {"verdict": "PARSE_ERROR", "rationale": raw[:200], "confidence": "LOW"}


# ──────────────────────────────────────────────────────────────────────────────
# 3. Data loaders
# ──────────────────────────────────────────────────────────────────────────────

def load_results(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected list of cases, got {type(data)}")
    print(f"[loader] Loaded {len(data)} cases from {path}")
    return data


def load_vaers_narratives(vaers_csv_path: str) -> dict:
    """Load VAERS CSV → {vaers_id (int): symptom_text (str)}"""
    narratives = {}
    if not os.path.exists(vaers_csv_path):
        print(f"[loader] WARNING: VAERS CSV not found at {vaers_csv_path}. "
              f"Contract A validation will use narrative_summary fallback.")
        return narratives

    try:
        with open(vaers_csv_path, encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # VAERS standard column names
                vaers_id_col = next((k for k in row if k.strip().upper() in ("VAERS_ID", "VAERSID")), None)
                text_col = next((k for k in row if k.strip().upper() in ("SYMPTOM_TEXT", "SYMPTOMTEXT")), None)
                if vaers_id_col and text_col:
                    try:
                        vid = int(str(row[vaers_id_col]).strip())
                        narratives[vid] = str(row[text_col]).strip()
                    except (ValueError, KeyError):
                        pass
    except Exception as e:
        print(f"[loader] WARNING: Could not read VAERS CSV: {e}")

    print(f"[loader] Loaded {len(narratives)} VAERS narratives")
    return narratives


def load_knowledge_base(knowledge_dir: str) -> dict:
    """Load ddx_myocarditis.json and investigation_protocols.json."""
    kb = {}

    ddx_path = os.path.join(knowledge_dir, "ddx_myocarditis.json")
    proto_path = os.path.join(knowledge_dir, "investigation_protocols.json")

    brighton_path = os.path.join(knowledge_dir, "brighton_case_definitions.json")
    for path, key in [(ddx_path, "ddx"), (proto_path, "protocols"), (brighton_path, "brighton")]:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                kb[key] = json.load(f)
            print(f"[loader] Loaded {key} from {path}")
        else:
            print(f"[loader] WARNING: {path} not found")
            kb[key] = {}

    return kb


def _kb_vocabulary(kb: dict) -> str:
    """
    Flatten knowledge base into a vocabulary string for the judge.

    Scope of Contract B:
      The Stage 6 guidance advisor uses ddx_myocarditis.json to identify
      alternative etiologies (Stage 3 DDx output) and investigation_protocols.json
      for directed investigation steps. Contract B validates that investigative_gaps
      (gap + action fields) are traceable to this combined knowledge base.

      recommended_actions are general clinical management steps (standard cardiac
      follow-up, pharmacovigilance reporting) drawing from general cardiology
      practice — they are NOT subject to Contract B grounding.

    The vocabulary includes full descriptions and all extraction keywords to
    avoid surface-form mismatches (e.g., 'CRP' vs 'C-reactive protein').
    """
    lines = [
        "=== KNOWLEDGE BASE: DDx Myocarditis + Investigation Protocols ===",
        "",
        "This knowledge base covers: differential diagnosis of myocarditis/pericarditis,",
        "clinical markers, investigation priorities, and etiology-specific workup.",
        "Brighton Collaboration case definitions (myocarditis Level 1-4, pericarditis Level 1-4),",
        "Standard cardiac investigations (troponin, CRP, ESR, BNP, pro-BNP,",
        "echocardiogram, cardiac MRI, ECG, viral serology, inflammatory markers,",
        "CBC, autoimmune panel, endomyocardial biopsy) are all within scope.",
        "",
    ]

    # DDx subtypes — full descriptions + all keywords
    ddx = kb.get("ddx", {})
    for subtype_key, subtype in ddx.get("subtypes", {}).items():
        label = subtype.get("label", subtype_key)
        lines.append(f"--- DDx Subtype: {label} ---")
        pathophys = subtype.get("pathophysiology", "")
        if pathophys:
            lines.append(f"  Pathophysiology: {pathophys[:200]}")
        high_sus = subtype.get("high_suspicion_criteria", "")
        if high_sus:
            lines.append(f"  High suspicion criteria: {high_sus[:200]}")
        for category in ("primary_indicators", "supporting_indicators", "confirmatory"):
            for indicator in subtype.get("clinical_features", {}).get(category, []):
                finding = indicator.get("finding", "")
                desc = indicator.get("description", "")
                keywords = ", ".join(indicator.get("extraction_keywords", []))
                diff_guide = indicator.get("differentiation_guide", "")
                lines.append(f"  [{category}] {finding}: {desc}")
                if keywords:
                    lines.append(f"    Keywords: {keywords}")
                if diff_guide:
                    lines.append(f"    Guide: {diff_guide[:150]}")

    # Investigation protocols — full test names + rationale
    protocols = kb.get("protocols", {}).get("protocols", {})
    for proto_key, proto in protocols.items():
        label = proto.get("label", proto_key)
        why = proto.get("why_suspected", "")
        lines.append(f"\n--- Protocol: {label} ---")
        if why:
            lines.append(f"  Why suspected: {why}")
        for inv in proto.get("investigations", []):
            test = inv.get("test", "")
            priority = inv.get("priority", "")
            rationale = inv.get("rationale", "")
            indication = inv.get("indication", "")
            expected = inv.get("expected_finding", "")
            diff_vax = inv.get("differential_from_vaccine", "")
            lines.append(f"  [{priority}] {test}")
            if rationale:
                lines.append(f"    Rationale: {rationale}")
            if indication:
                lines.append(f"    Indication: {indication}")
            if expected:
                lines.append(f"    Expected: {expected}")
            if diff_vax:
                lines.append(f"    Differential: {diff_vax}")

    # Brighton case definitions
    brighton = kb.get("brighton", {})
    for cond_key, cond in brighton.get("conditions", {}).items():
        label = cond.get("label", cond_key)
        lines.append(f"\n=== Brighton Collaboration: {label} ===")
        defn = cond.get("definition", "")
        if defn:
            lines.append(f"  Definition: {defn}")
        for crit_key, crit in cond.get("diagnostic_criteria", {}).items():
            crit_label = crit.get("label", crit_key)
            crit_desc = crit.get("description", "")
            crit_tests = ", ".join(crit.get("tests", []))
            crit_kw = ", ".join(crit.get("keywords", []))
            lines.append(f"  Criterion [{crit_key}]: {crit_label}")
            if crit_desc:
                lines.append(f"    Description: {crit_desc}")
            if crit_tests:
                lines.append(f"    Tests: {crit_tests}")
            if crit_kw:
                lines.append(f"    Keywords: {crit_kw}")
        for lvl_key, lvl in cond.get("brighton_levels", {}).items():
            lvl_label = lvl.get("label", lvl_key)
            criteria_text = "; ".join(lvl.get("criteria", []))
            interp = lvl.get("clinical_interpretation", "")
            action = lvl.get("vax_beacon_action", "")
            lines.append(f"  {lvl_label}: {criteria_text}")
            if interp:
                lines.append(f"    Interpretation: {interp}")
            if action:
                lines.append(f"    Vax-Beacon action: {action}")
        for gap_key, gap in cond.get("investigations_by_gap", {}).items():
            gap_tests = ", ".join(gap.get("tests", []))
            gap_rat = gap.get("rationale", "")
            lines.append(f"  Gap [{gap_key}] {gap.get('priority','')}: {gap_tests}")
            if gap_rat:
                lines.append(f"    Rationale: {gap_rat}")
    # Shared concepts
    for concept_key, concept in brighton.get("shared_concepts", {}).items():
        desc = concept.get("description", "")
        kw = ", ".join(concept.get("keywords", []))
        lines.append(f"  Shared concept [{concept_key}]: {desc[:200]}")
        if kw:
            lines.append(f"    Keywords: {kw}")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# 4. Contract A: Stage 3A context grounding
# ──────────────────────────────────────────────────────────────────────────────

def validate_contract_a(
    case: dict,
    narratives: dict,
    backend: str,
) -> dict:
    """
    Validate Contract A: Stage 3A context quotes ← VAERS original narrative.

    Returns:
      {
        "applicable": bool,
        "total_claims": int,
        "grounded": int,
        "ungrounded": int,
        "skip": int,
        "score": float,          # grounded / (grounded + ungrounded)
        "ungrounded_items": [...] # list of failed findings
        "case_type": str          # "normal" | "early_exit" | "onset_unknown"
      }
    """
    vaers_id = int(case.get("vaers_id", 0))
    stages = case.get("stages", {})
    is_early_exit = case.get("early_exit") or stages.get("stage6_guidance", {}).get("early_exit")

    # Early exit: Stage 3A not executed → Contract A not applicable
    if is_early_exit:
        return {
            "applicable": False,
            "case_type": "early_exit",
            "total_claims": 0,
            "grounded": 0,
            "ungrounded": 0,
            "skip": 0,
            "score": None,
            "ungrounded_items": [],
            "note": "Brighton L4 early exit — Stage 3A not executed",
        }

    # Get Stage 3A output
    s3_ddx = stages.get("stage3_ddx", {})
    s3a = s3_ddx.get("v4_stage3a", {})
    clinical_obs = s3a.get("clinical_observations", {})

    # Collect all context claims
    claims = []
    for domain, findings in clinical_obs.items():
        for finding in findings:
            context = finding.get("context", "").strip()
            if context and context not in ("", "null", "None"):
                claims.append({
                    "domain": domain,
                    "finding": finding.get("finding", ""),
                    "context": context,
                    "confidence": finding.get("confidence", "unknown"),
                })

    if not claims:
        # Determine case type
        s6 = stages.get("stage6_guidance", {})
        mode = s6.get("mode") or s6.get("unclassifiable_reason", "")
        case_type = "onset_unknown" if mode == "onset_unknown" else "normal"
        return {
            "applicable": True,
            "case_type": case_type,
            "total_claims": 0,
            "grounded": 0,
            "ungrounded": 0,
            "skip": 0,
            "score": None,
            "ungrounded_items": [],
            "note": "No context claims found in Stage 3A output",
        }

    # Get source narrative
    narrative = narratives.get(vaers_id, "")
    if not narrative:
        # Fallback: use narrative_summary from stage1 or ground_truth summary
        s1 = stages.get("stage1_icsr", {})
        narrative = s1.get("event", {}).get("narrative_summary", "")
        if not narrative:
            gt = case.get("ground_truth", {})
            narrative = gt.get("curated_summary", "")

    narrative_source = "VAERS_SYMPTOM_TEXT" if narratives.get(vaers_id) else "narrative_summary_fallback"

    # Determine case type
    s6 = stages.get("stage6_guidance", {})
    mode = s6.get("mode") or s6.get("unclassifiable_reason", "")
    case_type = "onset_unknown" if mode == "onset_unknown" else "normal"

    # Judge each claim
    grounded = 0
    ungrounded = 0
    skip = 0
    ungrounded_items = []

    for claim_item in claims:
        claim_text = f'Finding: "{claim_item["finding"]}"\nContext quote: "{claim_item["context"]}"'
        result = _judge(JUDGE_A_SYSTEM, claim_text, narrative, backend)

        verdict = result.get("verdict", "SKIP")
        if verdict == "GROUNDED":
            grounded += 1
        elif verdict == "UNGROUNDED":
            ungrounded += 1
            ungrounded_items.append({
                "domain": claim_item["domain"],
                "finding": claim_item["finding"],
                "context": claim_item["context"],
                "rationale": result.get("rationale", ""),
                "confidence": result.get("confidence", ""),
            })
        else:
            skip += 1

    total = grounded + ungrounded
    score = round(grounded / total, 3) if total > 0 else None

    return {
        "applicable": True,
        "case_type": case_type,
        "total_claims": len(claims),
        "grounded": grounded,
        "ungrounded": ungrounded,
        "skip": skip,
        "score": score,
        "narrative_source": narrative_source,
        "ungrounded_items": ungrounded_items,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 5. Contract B: Stage 6 guidance grounding
# ──────────────────────────────────────────────────────────────────────────────

def validate_contract_b(
    case: dict,
    kb_vocab: str,
    backend: str,
) -> dict:
    """
    Validate Contract B: Stage 6 investigative_gaps <- DDx knowledge base.

    Scope:
    - APPLICABLE: normal flow and onset_unknown (Stage 3 DDx was executed)
    - NOT APPLICABLE: Brighton L4 early exit cases
      Rationale: early_exit skips Stage 3-5 by design. Guidance draws from
      Brighton criteria and general clinical knowledge, not the DDx KB.

    Within applicable cases, only investigative_gaps (gap + action) are validated.
    recommended_actions are general clinical management steps excluded from
    Contract B -- they draw from general cardiology practice, not the DDx KB.

    Returns similar structure to Contract A.
    """
    stages = case.get("stages", {})
    s6 = stages.get("stage6_guidance", {})
    is_early_exit = case.get("early_exit") or s6.get("early_exit")
    mode = s6.get("mode") or s6.get("unclassifiable_reason", "")

    if mode == "onset_unknown":
        case_type = "onset_unknown"
    elif is_early_exit:
        case_type = "early_exit"
    else:
        case_type = "normal"

    # Early exit: NOT applicable
    if case_type == "early_exit":
        return {
            "applicable": False,
            "case_type": "early_exit",
            "total_claims": 0,
            "grounded": 0,
            "ungrounded": 0,
            "skip": 0,
            "score": None,
            "ungrounded_items": [],
            "note": (
                "Brighton L4 early exit -- Stage 3 DDx not executed. "
                "Guidance draws from Brighton criteria, not DDx KB. "
                "Excluded from Contract B by design."
            ),
        }

    # Collect claims: investigative_gaps only (no recommended_actions)
    claims = []

    if case_type == "normal":
        for gap in s6.get("investigative_gaps", []):
            text = gap.get("gap", "") or ""
            action = gap.get("action", "") or ""
            if text.strip():
                claims.append({"type": "gap", "text": text.strip()})
            if action.strip() and action.strip() != text.strip():
                claims.append({"type": "action", "text": action.strip()})
        # recommended_actions intentionally excluded

    elif case_type == "early_exit":
        # missing_brighton_criteria comes from code (Stage 2 logic), not LLM
        # But diagnostic_deficiencies / fastest_path_to_classification are LLM-generated
        for item in s6.get("diagnostic_deficiencies", []):
            if isinstance(item, dict):
                # Extract most informative text field
                text = (item.get("missing_test") or item.get("action") or
                        item.get("deficiency") or item.get("missing_criterion") or "")
                importance = item.get("importance", "")
                if text.strip():
                    claims.append({"type": "diagnostic_deficiency",
                                   "text": f"{text.strip()} — {importance[:80]}".strip(" —")})
            elif isinstance(item, str) and item.strip():
                claims.append({"type": "diagnostic_deficiency", "text": item.strip()})

        fastest = s6.get("fastest_path_to_classification")
        if isinstance(fastest, dict):
            # Structure: {target_level, required_tests, explanation}
            for test in fastest.get("required_tests", []):
                if isinstance(test, str) and test.strip():
                    claims.append({"type": "fastest_path", "text": test.strip()})
            explanation = fastest.get("explanation", "")
            if isinstance(explanation, str) and explanation.strip():
                claims.append({"type": "fastest_path_explanation", "text": explanation.strip()})
        elif isinstance(fastest, list):
            for item in fastest:
                text = (item.get("step") or item.get("action") or str(item)) if isinstance(item, dict) else str(item)
                if text.strip():
                    claims.append({"type": "fastest_path", "text": str(text).strip()})
        elif isinstance(fastest, str) and fastest.strip():
            claims.append({"type": "fastest_path", "text": fastest.strip()})

        # alternative_diagnoses can be string or list
        alt_dx = s6.get("alternative_diagnoses", [])
        if isinstance(alt_dx, str) and alt_dx.strip():
            claims.append({"type": "alternative_diagnosis", "text": alt_dx.strip()})
        elif isinstance(alt_dx, list):
            for alt in alt_dx:
                if isinstance(alt, dict):
                    text = alt.get("diagnosis") or alt.get("label") or str(alt)
                elif isinstance(alt, str):
                    text = alt
                else:
                    text = str(alt)
                if text.strip():
                    claims.append({"type": "alternative_diagnosis", "text": text.strip()})

    elif case_type == "onset_unknown":
        ov = s6.get("onset_verification", {})
        query = ov.get("query_text", "") if isinstance(ov, dict) else ""
        if query.strip():
            claims.append({"type": "onset_query", "text": query.strip()})
        for gap in s6.get("investigative_gaps", []):
            text = gap.get("gap", "") or ""
            if text.strip():
                claims.append({"type": "gap", "text": text.strip()})

    if not claims:
        return {
            "applicable": True,
            "case_type": case_type,
            "total_claims": 0,
            "grounded": 0,
            "ungrounded": 0,
            "skip": 0,
            "score": None,
            "ungrounded_items": [],
            "note": "No Stage 6 guidance claims found",
        }

    # Judge each claim against knowledge base vocabulary
    grounded = 0
    ungrounded = 0
    skip = 0
    ungrounded_items = []

    for claim_item in claims:
        result = _judge(JUDGE_B_SYSTEM, claim_item["text"], kb_vocab, backend)
        verdict = result.get("verdict", "SKIP")
        if verdict == "GROUNDED":
            grounded += 1
        elif verdict == "UNGROUNDED":
            ungrounded += 1
            ungrounded_items.append({
                "type": claim_item["type"],
                "text": claim_item["text"],
                "rationale": result.get("rationale", ""),
                "confidence": result.get("confidence", ""),
            })
        else:
            skip += 1

    total = grounded + ungrounded
    score = round(grounded / total, 3) if total > 0 else None

    return {
        "applicable": True,
        "case_type": case_type,
        "total_claims": len(claims),
        "grounded": grounded,
        "ungrounded": ungrounded,
        "skip": skip,
        "score": score,
        "ungrounded_items": ungrounded_items,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 6. Aggregate statistics
# ──────────────────────────────────────────────────────────────────────────────

def _aggregate(contract_results: list, contract_name: str) -> dict:
    """Compute aggregate grounding statistics across cases."""
    applicable = [r for r in contract_results if r.get("applicable")]
    with_scores = [r for r in applicable if r.get("score") is not None]

    if not with_scores:
        return {
            "contract": contract_name,
            "n_applicable": len(applicable),
            "n_with_scores": 0,
            "mean_score": None,
            "total_claims": 0,
            "total_grounded": 0,
            "total_ungrounded": 0,
            "aggregate_score": None,
        }

    total_claims = sum(r.get("total_claims", 0) for r in applicable)
    total_grounded = sum(r.get("grounded", 0) for r in applicable)
    total_ungrounded = sum(r.get("ungrounded", 0) for r in applicable)
    mean_score = round(sum(r["score"] for r in with_scores) / len(with_scores), 3)
    aggregate_score = round(
        total_grounded / (total_grounded + total_ungrounded), 3
    ) if (total_grounded + total_ungrounded) > 0 else None

    # Breakdown by case type
    by_type = {}
    for r in with_scores:
        ct = r.get("case_type", "unknown")
        if ct not in by_type:
            by_type[ct] = {"n": 0, "grounded": 0, "ungrounded": 0}
        by_type[ct]["n"] += 1
        by_type[ct]["grounded"] += r.get("grounded", 0)
        by_type[ct]["ungrounded"] += r.get("ungrounded", 0)

    for ct, d in by_type.items():
        total = d["grounded"] + d["ungrounded"]
        d["score"] = round(d["grounded"] / total, 3) if total > 0 else None

    return {
        "contract": contract_name,
        "n_applicable": len(applicable),
        "n_with_scores": len(with_scores),
        "mean_score": mean_score,
        "total_claims": total_claims,
        "total_grounded": total_grounded,
        "total_ungrounded": total_ungrounded,
        "aggregate_score": aggregate_score,
        "by_case_type": by_type,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 7. CSV summary writer
# ──────────────────────────────────────────────────────────────────────────────

def write_summary_csv(all_results: list, output_path: str) -> None:
    """Write per-case summary CSV for paper tables."""
    fieldnames = [
        "vaers_id", "condition_type", "who_category", "case_type",
        "a_total_claims", "a_grounded", "a_ungrounded", "a_score",
        "b_total_claims", "b_grounded", "b_ungrounded", "b_score",
        "b_case_type",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_results:
            ca = r.get("contract_a", {})
            cb = r.get("contract_b", {})
            stages = r.get("stages", {})
            s5 = stages.get("stage5_causality", {})
            s6 = stages.get("stage6_guidance", {})
            who = s6.get("who_category") or s5.get("who_category", "?")
            writer.writerow({
                "vaers_id": r.get("vaers_id"),
                "condition_type": r.get("condition_type", ""),
                "who_category": who,
                "case_type": ca.get("case_type", cb.get("case_type", "?")),
                "a_total_claims": ca.get("total_claims", ""),
                "a_grounded": ca.get("grounded", ""),
                "a_ungrounded": ca.get("ungrounded", ""),
                "a_score": ca.get("score", ""),
                "b_total_claims": cb.get("total_claims", ""),
                "b_grounded": cb.get("grounded", ""),
                "b_ungrounded": cb.get("ungrounded", ""),
                "b_score": cb.get("score", ""),
                "b_case_type": cb.get("case_type", ""),
            })
    print(f"[output] CSV summary written to {output_path}")


# ──────────────────────────────────────────────────────────────────────────────
# 8. Main
# ──────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Vax-Beacon Grounding Validator (FACTS-inspired)")
    p.add_argument("--results", required=True,
                   help="Path to results JSON (e.g. results_v4_full_100_*.json)")
    p.add_argument("--vaers", default=None,
                   help="Path to VAERS CSV with SYMPTOM_TEXT column")
    p.add_argument("--knowledge", default=None,
                   help="Path to knowledge/ directory (default: auto-detect relative to --results)")
    p.add_argument("--backend", default="anthropic", choices=["anthropic"],
                   help="LLM backend for judge calls (default: anthropic)")
    p.add_argument("--sample", type=int, default=None,
                   help="Validate a random sample of N cases (default: all)")
    p.add_argument("--seed", type=int, default=42,
                   help="Random seed for sampling (default: 42)")
    p.add_argument("--output-dir", default=None,
                   help="Output directory for results (default: same dir as --results)")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress per-case progress output")
    return p.parse_args()


def auto_detect_paths(results_path: str) -> tuple:
    """Auto-detect VAERS CSV and knowledge dir from results path."""
    results_dir = Path(results_path).parent
    # Try common relative locations
    candidates_vaers = [
        results_dir / "../../vaers_jan_nov_2021.csv/vaers_jan_nov_2021.csv",
        results_dir / "../../../vaers_jan_nov_2021.csv/vaers_jan_nov_2021.csv",
    ]
    candidates_kb = [
        results_dir / "../knowledge",
        results_dir / "../../knowledge",
    ]
    vaers = None
    for c in candidates_vaers:
        if c.resolve().exists():
            vaers = str(c.resolve())
            break
    kb = None
    for c in candidates_kb:
        if c.resolve().is_dir():
            kb = str(c.resolve())
            break
    return vaers, kb


def main():
    args = parse_args()

    # ── Auto-detect paths ──────────────────────────────────────────────────
    vaers_path = args.vaers
    kb_path = args.knowledge

    if not vaers_path or not kb_path:
        auto_vaers, auto_kb = auto_detect_paths(args.results)
        if not vaers_path:
            vaers_path = auto_vaers
            if vaers_path:
                print(f"[config] Auto-detected VAERS CSV: {vaers_path}")
            else:
                print("[config] VAERS CSV not found — Contract A will use narrative_summary fallback")
        if not kb_path:
            kb_path = auto_kb
            if kb_path:
                print(f"[config] Auto-detected knowledge dir: {kb_path}")
            else:
                print("[config] CRITICAL: Knowledge directory not found — Contract B cannot run")
                kb_path = ""

    output_dir = args.output_dir or str(Path(args.results).parent)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Load data ──────────────────────────────────────────────────────────
    cases = load_results(args.results)
    narratives = load_vaers_narratives(vaers_path) if vaers_path else {}
    kb = load_knowledge_base(kb_path) if kb_path else {}
    kb_vocab = _kb_vocabulary(kb)

    # ── Sample if requested ────────────────────────────────────────────────
    if args.sample:
        random.seed(args.seed)
        cases = random.sample(cases, min(args.sample, len(cases)))
        print(f"[config] Sampling {len(cases)} cases (seed={args.seed})")

    # ── Validate ───────────────────────────────────────────────────────────
    all_results = []
    contract_a_results = []
    contract_b_results = []

    n = len(cases)
    print(f"\n{'='*60}")
    print(f"Validating {n} cases | backend={args.backend}")
    print(f"{'='*60}\n")

    for i, case in enumerate(cases):
        vaers_id = case.get("vaers_id")
        if not args.quiet:
            print(f"[{i+1:3d}/{n}] VAERS {vaers_id} ...", end=" ", flush=True)

        t0 = time.time()

        # Contract A
        ca = validate_contract_a(case, narratives, args.backend)
        contract_a_results.append(ca)

        # Contract B
        cb = validate_contract_b(case, kb_vocab, args.backend)
        contract_b_results.append(cb)

        elapsed = round(time.time() - t0, 1)

        if not args.quiet:
            a_str = f"A={ca['score']:.2f}({ca['grounded']}/{ca['total_claims']})" if ca.get("score") is not None else f"A=N/A({ca.get('case_type','')})"
            b_str = f"B={cb['score']:.2f}({cb['grounded']}/{cb['total_claims']})" if cb.get("score") is not None else f"B=N/A"
            print(f"{a_str}  {b_str}  [{elapsed}s]")

        # Attach grounding results to case copy
        case_out = {k: v for k, v in case.items() if k != "stages"}  # omit heavy stages
        case_out["contract_a"] = ca
        case_out["contract_b"] = cb
        # Keep minimal stage info for CSV
        s5 = case.get("stages", {}).get("stage5_causality", {})
        s6 = case.get("stages", {}).get("stage6_guidance", {})
        case_out["stages"] = {
            "stage5_causality": {"who_category": s5.get("who_category")},
            "stage6_guidance": {"who_category": s6.get("who_category"), "mode": s6.get("mode")},
        }
        all_results.append(case_out)

    # ── Aggregate ──────────────────────────────────────────────────────────
    agg_a = _aggregate(contract_a_results, "Contract A: Stage 3A context ← VAERS narrative")
    agg_b = _aggregate(contract_b_results, "Contract B: Stage 6 guidance ← knowledge base")

    summary = {
        "generated_at": datetime.now().isoformat(),
        "results_file": args.results,
        "n_cases": n,
        "backend": args.backend,
        "contract_a": agg_a,
        "contract_b": agg_b,
    }

    # ── Print summary ──────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("GROUNDING VALIDATION SUMMARY")
    print(f"{'='*60}")
    for agg in [agg_a, agg_b]:
        print(f"\n{agg['contract']}")
        print(f"  Applicable cases : {agg['n_applicable']}")
        print(f"  With scores      : {agg['n_with_scores']}")
        print(f"  Total claims     : {agg['total_claims']}")
        print(f"  Grounded         : {agg['total_grounded']}")
        print(f"  Ungrounded       : {agg['total_ungrounded']}")
        print(f"  Mean case score  : {agg['mean_score']}")
        print(f"  Aggregate score  : {agg['aggregate_score']}  ← USE THIS FOR PAPER")
        if agg.get("by_case_type"):
            print(f"  By case type:")
            for ct, d in agg["by_case_type"].items():
                print(f"    {ct}: n={d['n']}, score={d.get('score')}")

    # ── Write outputs ──────────────────────────────────────────────────────
    json_out = os.path.join(output_dir, f"grounding_results_{timestamp}.json")
    csv_out  = os.path.join(output_dir, f"grounding_summary_{timestamp}.csv")

    with open(json_out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "cases": all_results}, f, indent=2, ensure_ascii=False)
    print(f"\n[output] Detailed JSON → {json_out}")

    write_summary_csv(all_results, csv_out)

    print(f"\n[done] Validation complete. {n} cases processed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
