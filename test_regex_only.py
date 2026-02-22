"""
Unit test: _extract_onset_days_from_narrative regex patterns
No MedGemma needed — pure Python regex test against actual VAERS narratives.

Run: python test_regex_only.py
"""

import re
import csv


def _extract_onset_days_from_narrative(narrative: str) -> float:
    """Fallback: extract days_to_onset from narrative text when CSV fields are empty."""
    text = narrative.lower()

    # Pattern 1: "Days from administration to presentation: 3 days" (literature format)
    m = re.search(r"days?\s+from\s+(?:administration|vaccination)\s+to\s+presentation[:\s]+(?:is\s+)?(\d+)", text)
    if m:
        return float(m.group(1))

    # Pattern 2: onset verb + "X days after/post/following" (requires clinical context)
    m = re.search(r"(?:present(?:ed|ing)|develop(?:ed|ing)|experienc(?:ed|ing)|onset|symptoms?\s+(?:started|began|appeared))\s+(\d+)\s*days?\s+(?:after|post|following)", text)
    if m:
        return float(m.group(1))

    # Pattern 3: "X days after/post vaccine dose" (explicit dose reference)
    m = re.search(r"(\d+)\s*days?\s+(?:after|post|following)\s+(?:the\s+)?(?:vaccine|vaccination|second|first|2nd|1st)\s+dose", text)
    if m:
        return float(m.group(1))

    # Pattern 4: "the next day" / "the following day" -> 1 day
    if re.search(r"(?:the\s+)?next\s+day|the\s+following\s+day", text):
        return 1.0

    # Pattern 5: "same day" / "day of vaccination" -> 0 days
    if re.search(r"same\s+day|day\s+of\s+(?:the\s+)?vaccin", text):
        return 0.0

    return None


# ---- Test against actual VAERS narratives (the 3 CSV-empty cases) ----
print("=" * 70)
print("TEST 1: Actual VAERS narratives (3 literature cases without CSV dates)")
print("=" * 70)

DATA_PATH = "data/vaers_100_cohort.csv"
target_ids = {"1299305", "1482907", "1482909"}

try:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["VAERS_ID"] in target_ids:
                narr = row.get("SYMPTOM_TEXT", "")
                result = _extract_onset_days_from_narrative(narr)
                status = "OK" if result is not None else "FAIL (None)"
                print(f"\n  VAERS {row['VAERS_ID']}: days_to_onset = {result}  [{status}]")
                # Show which pattern matched
                if result is not None:
                    text = narr.lower()
                    m1 = re.search(r"days?\s+from\s+(?:administration|vaccination)\s+to\s+presentation[:\s]+(?:is\s+)?(\d+)", text)
                    if m1:
                        print(f"    Matched pattern 1: '{m1.group(0)}'")
                        continue
                    m2 = re.search(r"(?:present(?:ed|ing)|develop(?:ed|ing)|experienc(?:ed|ing)|onset|symptoms?\s+(?:started|began|appeared))\s+(\d+)\s*days?\s+(?:after|post|following)", text)
                    if m2:
                        print(f"    Matched pattern 2: '{m2.group(0)}'")
except FileNotFoundError:
    print("  [SKIP] CSV not found at", DATA_PATH)

# ---- Synthetic edge case tests ----
print("\n" + "=" * 70)
print("TEST 2: Synthetic edge cases")
print("=" * 70)

tests = [
    ("lit_pattern1a", "Days from administration to presentation is 3 days.", 3.0),
    ("lit_pattern1b", "Days from administration to presentation: 3 Days.", 3.0),
    ("onset_verb", "Symptoms appeared 2 days after vaccination.", 2.0),
    ("presented", "presented 9 days after her first vaccine dose", 9.0),
    ("developed", "developed symptoms 5 days post the second dose", 5.0),
    ("next_day", "The patient presented the next day with chest pain.", 1.0),
    ("same_day", "Chest pain started same day as vaccination.", 0.0),
    ("hosp_stay", "Hospital length of stay was 3 days", None),
    ("cmr_timing", "CMR between 3 and 37 days after vaccination", None),
    ("vague", "Over the next 3 days went to ED with worsening CP.", None),
]

all_pass = True
print(f"\n  {'Case':<16} {'Expected':>10} {'Got':>10} {'Status':>8}")
print("  " + "-" * 48)
for name, text, expected in tests:
    result = _extract_onset_days_from_narrative(text)
    ok = result == expected
    if not ok:
        all_pass = False
    print(f"  {name:<16} {str(expected):>10} {str(result):>10} {'OK' if ok else 'FAIL':>8}")

print("\n" + "=" * 70)
print(f"RESULT: {'ALL PASSED' if all_pass else 'SOME FAILED'}")
print("=" * 70)
