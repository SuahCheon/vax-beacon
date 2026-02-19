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

MedGemma Hybrid:
  - Code builds complete JSON skeleton (vaers_id, confidence, key_factors)
  - LLM writes only a 2-3 sentence reasoning_summary (plain text, no JSON)
  - Fallback: code generates template reasoning if LLM fails
"""

import json
from llm_client import LLMClient
from prompts.system_prompts import STAGE5_CAUSALITY_INTEGRATOR, STAGE5_REASONING_MEDGEMMA


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
    vaers_id = icsr_data.get("vaers_id")

    # Key factors (code-determined)
    key_factors = [f"Brighton L{brighton_level}", f"NCI {max_nci:.2f}", temporal_zone]
    if known_ae:
        key_factors.append("Known AE (ESTABLISHED)")
    if temporal_met:
        key_factors.append(f"Temporal met ({temporal_zone})")

    # Confidence (code-determined)
    if who_category in ("A1", "C"):
        confidence = "HIGH"
    elif who_category in ("B1", "B2"):
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    # MedGemma hybrid: code skeleton + plain text reasoning
    if llm.backend == "medgemma":
        reasoning = _generate_reasoning_medgemma(
            llm, vaers_id, who_category, brighton_level, max_nci,
            known_ae, temporal_met, temporal_zone, condition_type,
        )
    else:
        # Anthropic: full JSON query
        slim_input = {
            "vaers_id": vaers_id,
            "condition_type": condition_type,
            "brighton_level": brighton_level,
            "max_nci": max_nci,
            "known_ae": known_ae,
            "temporal_met": temporal_met,
            "temporal_zone": temporal_zone,
            "who_step1_conclusion": who_step1,
            "epistemic_uncertainty": epistemic,
            "assigned_who_category": who_category,
            "assigned_who_label": _who_label(who_category),
            "decision_chain": decision_chain,
            "investigation_context": {
                "intensity": temporal_data.get("temporal_assessment", {}).get("investigation_intensity"),
                "focus": temporal_data.get("temporal_assessment", {}).get("investigation_focus"),
                "description": temporal_data.get("temporal_assessment", {}).get("investigation_description"),
            },
        }
        try:
            llm_result = llm.query_json(
                system_prompt=STAGE5_CAUSALITY_INTEGRATOR,
                user_message=(
                    "Explain why this WHO AEFI causality category was assigned. "
                    "The classification has already been determined by the decision tree.\n\n"
                    f"{json.dumps(slim_input, indent=2)}"
                ),
            )
            reasoning = llm_result.get("reasoning_summary", "") or llm_result.get("reasoning", "")
            confidence = llm_result.get("confidence", confidence)
            key_factors = llm_result.get("key_factors", key_factors)
        except Exception as e:
            reasoning = (
                f"Classification {who_category} determined by decision tree. "
                f"LLM reasoning unavailable: {e}"
            )

    # Build final result — who_category is ALWAYS from code, never from LLM
    result = {
        "vaers_id": vaers_id,
        "who_category": who_category,
        "who_category_label": _who_label(who_category),
        "confidence": confidence,
        "decision_chain": decision_chain,
        "key_factors": key_factors,
        "reasoning": reasoning,
        "override_applied": False,
        "classification_source": "DETERMINISTIC (v4 decision tree)",
    }

    return result


def _generate_reasoning_medgemma(
    llm, vaers_id, who_category, brighton_level, max_nci,
    known_ae, temporal_met, temporal_zone, condition_type,
) -> str:
    """
    MedGemma hybrid: LLM writes plain text reasoning, code provides context.
    Fallback: code generates template reasoning if LLM fails.
    """
    # Build a concise input for LLM
    input_text = (
        f"WHO={who_category}, Brighton L{brighton_level}, "
        f"NCI={max_nci:.2f}, temporal={temporal_zone}, "
        f"known_ae={known_ae}, {condition_type}"
    )

    try:
        reasoning = llm.query_text(
            system_prompt=STAGE5_REASONING_MEDGEMMA,
            user_message=input_text,
        )
        # Validate: must be non-empty and not JSON
        reasoning = reasoning.strip()
        if reasoning and not reasoning.startswith("{"):
            return reasoning[:500]  # Cap length
    except Exception:
        pass

    # Fallback: code-generated reasoning
    if who_category == "A1":
        return (
            f"Classification A1 (Consistent with causal association): "
            f"{condition_type} is an established adverse event of mRNA COVID-19 vaccines. "
            f"Brighton Level {brighton_level} confirms diagnostic certainty. "
            f"Onset falls within {temporal_zone} window. "
            f"NCI score {max_nci:.2f} indicates no significant alternative etiology."
        )
    elif who_category == "C":
        return (
            f"Classification C (Coincidental): "
            f"NCI score {max_nci:.2f} indicates a definite alternative cause. "
            f"Temporal zone: {temporal_zone}. Brighton Level {brighton_level}."
        )
    elif who_category == "B1":
        return (
            f"Classification B1 (Indeterminate — potential signal): "
            f"Temporal relationship is {temporal_zone} but {condition_type} "
            f"is not an established AE for this vaccine. NCI {max_nci:.2f}."
        )
    elif who_category == "B2":
        return (
            f"Classification B2 (Indeterminate — conflicting factors): "
            f"Evidence both for and against vaccine causation. "
            f"NCI {max_nci:.2f}, temporal zone {temporal_zone}."
        )
    else:
        return (
            f"Classification {who_category}: "
            f"Brighton L{brighton_level}, NCI {max_nci:.2f}, temporal {temporal_zone}."
        )
