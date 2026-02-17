"""
Vax-Beacon v4 | Stage 5: Causality Assessor (Deterministic + LLM Explanation)
===================================================================================
WHO Step 3 & 4: Review & Final Classification

v4 Architecture:
  Stage 5A (classify)  — Code, 100% Deterministic: Decision tree classification
  Stage 5B (LLM)       — Reasoning Generator: Explains the already-decided category

The LLM CANNOT change the classification. It only generates the reasoning summary.
This eliminates the v3.1 "Pattern B" problem where LLM contradicted its own decision
chain, and removes the need for _apply_decision_guard().
"""

import json
from llm_client import LLMClient
from prompts.system_prompts import STAGE5_CAUSALITY_INTEGRATOR


# ============================================================
# Stage 5A: Deterministic Decision Tree (100% Code)
# ============================================================

def classify(
    brighton_level: int,
    max_nci: float,
    known_ae: bool,
    temporal_met: bool,
    temporal_zone: str,
    who_step1_conclusion: str,
    epistemic_uncertainty: float = 0.0,
) -> tuple:
    """
    Deterministic WHO AEFI classification following the decision tree exactly.

    Returns:
        (who_category, decision_chain_dict)
    """
    dc = {
        "q1_valid_diagnosis": brighton_level <= 3,
        "q2_definite_other_cause": False,
        "q3_known_ae": known_ae,
        "q4_temporal_met": temporal_met,
        "q5_conflicting_alternatives": False,
        "brighton_level": brighton_level,
        "temporal_zone": temporal_zone,
        "max_nci": max_nci,
        "step1_conclusion": who_step1_conclusion,
    }

    # Rule 1: Brighton L4 → Unclassifiable (defensive; early exit normally catches this)
    if brighton_level > 3:
        return "Unclassifiable", dc

    # Rule 2: Definite alternative cause → C
    if max_nci >= 0.7:
        dc["q2_definite_other_cause"] = True
        return "C", dc

    # Rule 2.5: Onset unknown → Unclassifiable (temporal assessment essential for WHO AEFI)
    if temporal_zone == "UNKNOWN":
        dc["onset_unknown"] = True
        return "Unclassifiable", dc

    # Rule 3: Known AE pathway
    if known_ae:
        if temporal_met:
            if max_nci >= 0.4:
                dc["q5_conflicting_alternatives"] = True
                return "B2", dc  # Vaccine causation + alternative cause conflict
            else:
                return "A1", dc  # Vaccine causation confirmed, weak alternative
        else:
            if temporal_zone in ("UNLIKELY", "BACKGROUND_RATE"):
                return "C", dc   # Clear temporal inconsistency
            else:
                return "B2", dc  # Temporal uncertainty

    # Rule 4: Not Known AE pathway
    else:
        if temporal_met:  # temporal_zone in ("STRONG_CAUSAL", "PLAUSIBLE")
            if max_nci >= 0.4:
                dc["q5_conflicting_alternatives"] = True
                return "B2", dc
            else:
                return "B1", dc  # Potential new signal
        else:
            return "C", dc


def _who_label(category: str) -> str:
    """Map WHO category code to official label."""
    labels = {
        "A1": "Consistent with causal association (Vaccine product-related)",
        "A2": "Consistent with causal association (Vaccine quality defect)",
        "A3": "Consistent with causal association (Immunization error)",
        "A4": "Consistent with causal association (Immunization anxiety)",
        "B1": "Indeterminate (potential signal)",
        "B2": "Indeterminate (conflicting factors)",
        "C": "Inconsistent with causal association (Coincidental)",
        "Unclassifiable": "Insufficient data for meaningful assessment",
    }
    return labels.get(category, category)


# ============================================================
# Stage 5B: LLM Reasoning Generator (Explain-Only)
# ============================================================

def run_stage5(
    llm: LLMClient,
    icsr_data: dict,
    brighton_data: dict,
    ddx_data: dict,
    temporal_data: dict,
    condition_type: str = "myocarditis",
) -> dict:
    """
    WHO Step 3 & 4: Deterministic classification + LLM reasoning.

    v4 flow:
      1. Code classify() determines WHO category (100% deterministic)
      2. LLM generates reasoning explanation for the assigned category
      3. LLM output is merged but who_category is NEVER overridden

    Args:
        llm: LLM client instance
        icsr_data: Structured ICSR from Stage 1
        brighton_data: Brighton assessment from Stage 2 (rule-based)
        ddx_data: DDx assessment from Stage 3
        temporal_data: Known AE + Temporal from Stage 4 (rule-based)
        condition_type: "myocarditis" or "pericarditis"

    Returns:
        Final WHO causality category with reasoning chain.
    """
    # --- Stage 5A: Deterministic classification ---
    brighton_level = brighton_data.get("brighton_level", 4)
    max_nci = ddx_data.get("max_nci_score", 0) or 0
    who_step1 = ddx_data.get("who_step1_conclusion", "NO_ALTERNATIVE")
    epistemic = ddx_data.get("epistemic_uncertainty", 0) or 0

    known_ae = temporal_data.get(
        "known_ae_assessment", {},
    ).get("is_known_ae", False)
    temporal_met = temporal_data.get("who_step2_met", False)
    temporal_zone = temporal_data.get(
        "temporal_assessment", {},
    ).get("temporal_zone", "UNKNOWN")

    who_category, decision_chain = classify(
        brighton_level=brighton_level,
        max_nci=max_nci,
        known_ae=known_ae,
        temporal_met=temporal_met,
        temporal_zone=temporal_zone,
        who_step1_conclusion=who_step1,
        epistemic_uncertainty=epistemic,
    )

    # --- Stage 5B: LLM reasoning for the assigned category ---
    combined_input = {
        "icsr": icsr_data,
        "stage2_brighton": brighton_data,
        "stage3_ddx": ddx_data,
        "stage4_temporal_known_ae": temporal_data,
        "condition_type": condition_type,
        "assigned_who_category": who_category,
        "assigned_who_label": _who_label(who_category),
        "decision_chain": decision_chain,
        # v4.1b: investigation context for reasoning
        "investigation_context": {
            "intensity": temporal_data.get("temporal_assessment", {}).get("investigation_intensity"),
            "focus": temporal_data.get("temporal_assessment", {}).get("investigation_focus"),
            "description": temporal_data.get("temporal_assessment", {}).get("investigation_description"),
        },
    }

    llm_result = llm.query_json(
        system_prompt=STAGE5_CAUSALITY_INTEGRATOR,
        user_message=(
            "Explain why this WHO AEFI causality category was assigned. "
            "The classification has already been determined by the decision tree.\n\n"
            f"{json.dumps(combined_input, indent=2)}"
        ),
    )

    # Build final result — who_category is ALWAYS from code, never from LLM
    vaers_id = icsr_data.get("vaers_id")

    result = {
        "vaers_id": vaers_id,
        "who_category": who_category,
        "who_category_label": _who_label(who_category),
        "confidence": llm_result.get("confidence", "HIGH"),
        "decision_chain": decision_chain,
        "key_factors": llm_result.get("key_factors", []),
        "reasoning": llm_result.get("reasoning_summary", "")
                     or llm_result.get("reasoning", ""),
        "override_applied": False,
        "classification_source": "DETERMINISTIC (v4 decision tree)",
    }

    return result
