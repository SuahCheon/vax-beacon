"""
Data Loader for VAERS 100-Case Cohort
=======================================
Parses the curated CSV and prepares input for each pipeline stage.
"""

import pandas as pd
from config import DATA_PATH, VAERS_INPUT_COLUMNS, GROUND_TRUTH_COLUMNS


def load_vaers_data(filepath: str = None) -> pd.DataFrame:
    """Load the full VAERS 100-case cohort."""
    path = filepath or DATA_PATH
    df = pd.read_csv(path)
    print(f"Loaded {len(df)} cases from {path}")
    print(f"  Myocarditis: {(df['condition_type']=='myocarditis').sum()}")
    print(f"  Pericarditis: {(df['condition_type']=='pericarditis').sum()}")
    print(f"  Groups: {df['group'].value_counts().to_dict()}")
    return df


def get_case_input(row: pd.Series) -> str:
    """
    Format a single VAERS case as a text input for Stage 1.
    Uses ONLY the raw VAERS fields (not curated ground truth).
    """
    parts = []
    parts.append(f"=== VAERS REPORT ID: {row['VAERS_ID']} ===\n")

    # Demographics
    parts.append(f"[DEMOGRAPHICS]")
    parts.append(f"Age: {row.get('AGE_YRS', 'Unknown')}")
    parts.append(f"Sex: {row.get('SEX', 'Unknown')}")
    parts.append(f"State: {row.get('STATE', 'Unknown')}\n")

    # Vaccine Information
    parts.append(f"[VACCINE]")
    parts.append(f"Vaccine: {row.get('VAX_NAME', 'Unknown')}")
    parts.append(f"Manufacturer: {row.get('VAX_MANU', 'Unknown')}")
    parts.append(f"Dose: {row.get('VAX_DOSE_SERIES', 'Unknown')}")
    parts.append(f"Lot: {row.get('VAX_LOT', 'Unknown')}")
    parts.append(f"Vaccination Date: {row.get('VAX_DATE', 'Unknown')}")
    parts.append(f"Route: {row.get('VAX_ROUTE', 'Unknown')}")
    parts.append(f"Site: {row.get('VAX_SITE', 'Unknown')}\n")

    # Event Timeline
    parts.append(f"[EVENT TIMELINE]")
    parts.append(f"Onset Date: {row.get('ONSET_DATE', 'Unknown')}")
    parts.append(f"Days to Onset: {row.get('NUMDAYS', 'Unknown')}\n")

    # Coded Symptoms (MedDRA terms from VAERS)
    symptoms = []
    for i in range(1, 6):
        s = row.get(f'SYMPTOM{i}')
        if pd.notna(s) and str(s).strip():
            symptoms.append(str(s).strip())
    if symptoms:
        parts.append(f"[CODED SYMPTOMS (MedDRA)]")
        parts.append(f"{', '.join(symptoms)}\n")

    # Narrative (the core clinical text)
    symptom_text = row.get('SYMPTOM_TEXT', '')
    if pd.notna(symptom_text) and str(symptom_text).strip():
        parts.append(f"[NARRATIVE]")
        parts.append(f"{str(symptom_text).strip()}\n")

    # Lab Data
    lab_data = row.get('LAB_DATA', '')
    if pd.notna(lab_data) and str(lab_data).strip():
        parts.append(f"[LABORATORY DATA]")
        parts.append(f"{str(lab_data).strip()}\n")

    # Medical History
    history = row.get('HISTORY', '')
    if pd.notna(history) and str(history).strip():
        parts.append(f"[MEDICAL HISTORY]")
        parts.append(f"{str(history).strip()}\n")

    # Current Illness
    cur_ill = row.get('CUR_ILL', '')
    if pd.notna(cur_ill) and str(cur_ill).strip():
        parts.append(f"[CURRENT ILLNESS AT TIME OF VACCINATION]")
        parts.append(f"{str(cur_ill).strip()}\n")

    # Medications
    meds = row.get('OTHER_MEDS', '')
    if pd.notna(meds) and str(meds).strip():
        parts.append(f"[MEDICATIONS]")
        parts.append(f"{str(meds).strip()}\n")

    # Allergies
    allergies = row.get('ALLERGIES', '')
    if pd.notna(allergies) and str(allergies).strip():
        parts.append(f"[ALLERGIES]")
        parts.append(f"{str(allergies).strip()}\n")

    # Outcomes
    parts.append(f"[OUTCOMES]")
    parts.append(f"Died: {row.get('DIED', 'Unknown')}")
    parts.append(f"Life-threatening: {row.get('L_THREAT', 'Unknown')}")
    parts.append(f"ER Visit: {row.get('ER_VISIT', 'Unknown')}")
    parts.append(f"Hospitalized: {row.get('HOSPITAL', 'Unknown')}")
    parts.append(f"Hospital Days: {row.get('HOSPDAYS', 'Unknown')}")
    parts.append(f"Recovered: {row.get('RECOVD', 'Unknown')}")

    return "\n".join(parts)


def get_ground_truth(row: pd.Series) -> dict:
    """Extract curated ground truth fields for validation."""
    return {
        "vaers_id": row["VAERS_ID"],
        "condition_type": row.get("condition_type"),
        "group": row.get("group"),
        "curated_age": row.get("curated_age"),
        "curated_sex": row.get("curated_sex"),
        "curated_onset_days": row.get("curated_onset_days"),
        "curated_key_evidence": row.get("curated_key_evidence"),
        "curated_severity": row.get("curated_severity"),
        "curated_summary": row.get("curated_summary"),
    }


def get_cases_by_group(df: pd.DataFrame, group: str) -> pd.DataFrame:
    """Filter cases by group (G1, G2, G3, clean, confounded)."""
    return df[df["group"] == group].copy()


def get_sample_cases(df: pd.DataFrame, n_per_group: int = 2) -> pd.DataFrame:
    """Get a small sample for testing (n cases per group)."""
    samples = []
    for group in df["group"].unique():
        group_df = df[df["group"] == group].head(n_per_group)
        samples.append(group_df)
    return pd.concat(samples, ignore_index=True)


if __name__ == "__main__":
    # Quick test
    df = load_vaers_data()
    print("\n--- Sample Case Input (first row) ---")
    print(get_case_input(df.iloc[0])[:1000])
    print("\n--- Ground Truth ---")
    print(get_ground_truth(df.iloc[0]))
