"""
Vax-Beacon Configuration
===========================
MedGemma PoC for Global Vaccine Safety Surveillance
- Local prototype: Anthropic Claude API
- Final Kaggle: MedGemma 4B (unified)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Project root: directory containing this config.py file
PROJECT_ROOT = str(Path(__file__).resolve().parent)

# Load .env file (override=True to ensure .env values take precedence)
load_dotenv(override=True)

# --- API Configuration ---
# Local prototype uses Anthropic API; Kaggle version will swap to MedGemma 4B
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"  # Local proxy for MedGemma 4B
ANTHROPIC_MODEL_LIGHT = "claude-haiku-4-5-20251001"  # Lightweight model for summaries
MAX_TOKENS = 4096
TEMPERATURE = 0.1  # Low temperature for regulatory precision

# --- Clinical Constants (NAM 2024 & WHO AEFI) ---
# NAM 2024 Evidence Review: mRNA vaccine → myocarditis causal window
NAM_CAUSAL_WINDOW_DAYS = 7       # 0-7 days: strong causal association
MECHANISTIC_THRESHOLD_DAYS = 22  # Innate immune overactivation window
BACKGROUND_RATE_ZONE_START = 22  # 22-42 days: background rate zone
BACKGROUND_RATE_ZONE_END = 42

# Brighton Collaboration Diagnostic Criteria Levels
BRIGHTON_LEVELS = {
    1: "Definite (endomyocardial biopsy OR CMR + biomarkers + symptoms)",
    2: "Probable (biomarkers + imaging OR ECG + symptoms)",
    3: "Possible (biomarkers OR imaging + symptoms)",
    4: "Reported (insufficient evidence for Level 1-3)",
}

# WHO AEFI Causality Assessment Categories
WHO_CATEGORIES = {
    "A1": "Consistent causal association to immunization",
    "A2": "Consistent causal association to immunization (known vaccine product reaction)",
    "A3": "Consistent causal association to immunization (immunization error)",
    "A4": "Consistent causal association to immunization (immunization anxiety)",
    "B1": "Indeterminate",
    "B2": "Inconsistent with causal association (coincidental)",
    "C":  "Unclassifiable (insufficient information)",
}

# NAM 2024 Shadow Scoring: Pericarditis reclassification criteria
# Isolated pericarditis without troponin elevation → B1 (Indeterminate)
PERICARDITIS_SHADOW_CRITERIA = {
    "requires_troponin_elevation": True,
    "requires_mri_confirmation": False,  # Not mandatory per NAM 2024
    "default_reclassification": "B1",
}

# Severity Tiers for G3 classification
SEVERITY_TIERS = {
    "CRITICAL": ["ECMO", "Cardiac arrest", "Death", "Fatal", "Fulminant"],
    "HIGH": ["Cardiogenic shock", "VT", "VF", "Heart block", "Inotropes", "Dobutamine", "Vasopressors"],
    "MODERATE": ["ICU", "EF <50%", "EF 3", "EF 4"],  # EF 30-49%
    "RECORDED": [],  # Default for G3 cases not matching above
}

# --- Data Configuration (relative to PROJECT_ROOT) ---
DATA_PATH = os.path.join(PROJECT_ROOT, "data", "vaers_100_cohort.csv")
RESULTS_PATH = os.path.join(PROJECT_ROOT, "results")
KNOWLEDGE_DB_PATH = os.path.join(PROJECT_ROOT, "knowledge")

# Key VAERS columns for pipeline input
VAERS_INPUT_COLUMNS = [
    "VAERS_ID", "SYMPTOM_TEXT", "LAB_DATA", "HISTORY", "CUR_ILL",
    "OTHER_MEDS", "ALLERGIES", "VAX_DATE", "ONSET_DATE", "NUMDAYS",
    "AGE_YRS", "SEX", "VAX_NAME", "VAX_MANU", "VAX_DOSE_SERIES",
    "DIED", "L_THREAT", "ER_VISIT", "HOSPITAL", "HOSPDAYS",
    "SYMPTOM1", "SYMPTOM2", "SYMPTOM3", "SYMPTOM4", "SYMPTOM5",
]

# Curated columns for ground truth validation
GROUND_TRUTH_COLUMNS = [
    "condition_type", "group", "curated_age", "curated_sex",
    "curated_onset_days", "curated_key_evidence", "curated_severity",
    "curated_summary",
]
