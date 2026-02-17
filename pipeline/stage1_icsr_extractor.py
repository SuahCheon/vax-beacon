"""
Stage 1: ICSR Extractor
========================
Converts unstructured VAERS narrative into structured JSON.
MedGemma advantage: Medical entity recognition (MedDRA terms, Brighton criteria markers)
"""

from llm_client import LLMClient
from prompts.system_prompts import STAGE1_ICSR_EXTRACTOR


def run_stage1(llm: LLMClient, case_text: str) -> dict:
    """
    Extract structured ICSR data from a raw VAERS report.

    Args:
        llm: LLM client instance
        case_text: Formatted VAERS case text (from data_loader.get_case_input)

    Returns:
        Structured ICSR dict with demographics, vaccine, event, clinical data, etc.
    """
    result = llm.query_json(
        system_prompt=STAGE1_ICSR_EXTRACTOR,
        user_message=f"Parse the following VAERS report into structured ICSR format:\n\n{case_text}",
    )
    return result
