"""
Vax-Beacon v4 | Stage 3B: DDx Matcher (Deterministic Code)
==============================================================
100% deterministic keyword matching — identical input always produces identical output.

Input:  Stage 3A output + ddx_myocarditis.json
Output: DDx candidate list (1-N) + matched markers + differentiation questions

Matching Rules:
  - Case-insensitive matching of extraction_keywords against 3A observations
  - Short keywords (<=3 chars) use word-boundary matching to prevent false positives
  - Longer keywords use substring matching
  - If negative_keywords match the same observation → exclude that indicator
  - Subtypes with 0 matched indicators → excluded from candidates
  - narrative_nuance handled separately (outside DB)
"""

import re


def _get_all_indicators(subtype_data: dict) -> list:
    """Extract all indicators from a subtype's clinical_features."""
    features = subtype_data.get("clinical_features", {})
    indicators = []
    for tier in ["primary_indicators", "supporting_indicators", "confirmatory"]:
        indicators.extend(features.get(tier, []))
    return indicators


def _keyword_in_text(keyword: str, text_lower: str) -> bool:
    """
    Match a keyword in text. Short keywords (<=3 chars) use word-boundary
    matching to prevent false positives (e.g., "RA" matching "rapid").
    Longer keywords use substring matching.
    """
    kw_lower = keyword.lower()
    if len(kw_lower) <= 3:
        return bool(re.search(r'\b' + re.escape(kw_lower) + r'\b', text_lower))
    return kw_lower in text_lower


def _text_matches_keywords(text: str, keywords: list) -> str | None:
    """
    Check if any keyword matches in the text (case-insensitive).
    Short keywords use word-boundary matching; longer use substring.
    Returns the first matched keyword, or None.
    """
    text_lower = text.lower()
    for kw in keywords:
        if _keyword_in_text(kw, text_lower):
            return kw
    return None


def _text_matches_negative(text: str, negative_keywords: list) -> bool:
    """Check if any negative keyword matches in the text."""
    if not negative_keywords:
        return False
    text_lower = text.lower()
    for nkw in negative_keywords:
        if _keyword_in_text(nkw, text_lower):
            return True
    return False


def _collect_observation_texts(stage3a_output: dict) -> list:
    """
    Collect all observation texts from 3A output, including both
    the 'finding' description and the 'context' verbatim quote.
    Each entry: (domain, finding_text, context_text, full_combined_text)
    """
    observations = stage3a_output.get("clinical_observations", {})
    texts = []
    for domain, entries in observations.items():
        for entry in entries:
            finding = entry.get("finding", "")
            context = entry.get("context", "")
            combined = f"{finding} {context}"
            texts.append({
                "domain": domain,
                "finding": finding,
                "context": context,
                "combined": combined,
            })
    # Also check key_negatives — these could be relevant for negative_keywords
    return texts


def _collect_narrative_nuance(stage3a_output: dict) -> list:
    """Extract narrative_uncertainty observations from 3A for separate handling."""
    observations = stage3a_output.get("clinical_observations", {})
    return observations.get("narrative_uncertainty", [])


def run_stage3b(stage3a_output: dict, ddx_db: dict) -> dict:
    """
    Stage 3B: Deterministic DDx matching against knowledge DB.

    Args:
        stage3a_output: Output from Stage 3A (clinical observations by domain)
        ddx_db: Loaded ddx_myocarditis.json content

    Returns:
        Dict with ddx_candidates, narrative_nuance_observations, match_summary
    """
    subtypes = ddx_db.get("subtypes", {})
    observation_texts = _collect_observation_texts(stage3a_output)
    key_negatives = stage3a_output.get("key_negatives", [])
    negatives_combined = " ".join(str(n) for n in key_negatives).lower()

    ddx_candidates = []
    total_matched_indicators = 0

    for subtype_key, subtype_data in subtypes.items():
        indicators = _get_all_indicators(subtype_data)
        matched_indicators = []
        unmatched_indicators = []
        differentiation_questions = []

        for indicator in indicators:
            finding_name = indicator["finding"]
            ext_keywords = indicator.get("extraction_keywords", [])
            neg_keywords = indicator.get("negative_keywords", [])
            diff_guide = indicator.get("differentiation_guide", "")
            weight = indicator.get("weight", 0.0)

            # Search all 3A observations for keyword matches
            best_match = None
            for obs in observation_texts:
                matched_kw = _text_matches_keywords(obs["combined"], ext_keywords)
                if matched_kw:
                    # Check negative keywords against this same observation
                    if _text_matches_negative(obs["combined"], neg_keywords):
                        continue
                    # Also check if key_negatives contradict this finding
                    if _text_matches_negative(negatives_combined, ext_keywords[:3]):
                        # Key negatives mention this finding → skip
                        continue
                    best_match = {
                        "finding": finding_name,
                        "matched_keyword": matched_kw,
                        "source_observation": obs["finding"],
                        "source_context": obs["context"],
                        "source_domain": obs["domain"],
                        "differentiation_guide": diff_guide,
                        "weight": weight,
                    }
                    break  # Take first match per indicator

            if best_match:
                matched_indicators.append(best_match)
                if diff_guide:
                    differentiation_questions.append(diff_guide)
            else:
                unmatched_indicators.append(finding_name)

        # Only include subtypes with at least one matched indicator
        if matched_indicators:
            total_matched_indicators += len(matched_indicators)
            ddx_candidates.append({
                "subtype": subtype_key,
                "label": subtype_data.get("label", subtype_key),
                "matched_indicators": matched_indicators,
                "unmatched_indicators": unmatched_indicators,
                "differentiation_questions": differentiation_questions,
            })

    # Sort candidates by total matched weight (descending)
    ddx_candidates.sort(
        key=lambda c: sum(m["weight"] for m in c["matched_indicators"]),
        reverse=True,
    )

    # Narrative nuance — handled separately, not in DB
    narrative_nuance_observations = _collect_narrative_nuance(stage3a_output)

    return {
        "ddx_candidates": ddx_candidates,
        "narrative_nuance_observations": narrative_nuance_observations,
        "match_summary": {
            "total_candidates": len(ddx_candidates),
            "total_matched_indicators": total_matched_indicators,
        },
    }
