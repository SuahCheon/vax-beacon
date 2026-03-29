"""
Unit tests for Stage 5A deterministic classify() function.
Tests the WHO AEFI decision tree including v4.1a UNKNOWN onset path.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.stage5_causality_assessor import classify


def test_unknown_onset():
    """Onset unknown -> Unclassifiable."""
    cat, dc = classify(3, 0.0, True, False, "UNKNOWN", "NO_ALTERNATIVE")
    assert cat == "Unclassifiable"
    assert dc["onset_unknown"] == True

    cat, dc = classify(3, 0.0, False, False, "UNKNOWN", "NO_ALTERNATIVE")
    assert cat == "Unclassifiable"


def test_unknown_onset_high_nci():
    """NCI >= 0.7 -> C even with unknown onset."""
    cat, dc = classify(3, 0.8, True, False, "UNKNOWN", "DEFINITE_OTHER_CAUSE")
    assert cat == "C"


def test_brighton_l4():
    assert classify(4, 0.0, True, True, "STRONG_CAUSAL", "NO_ALTERNATIVE")[0] == "Unclassifiable"


def test_known_ae_strong_low_nci():
    assert classify(3, 0.0, True, True, "STRONG_CAUSAL", "NO_ALTERNATIVE")[0] == "A1"


def test_known_ae_strong_high_nci():
    assert classify(3, 0.5, True, True, "STRONG_CAUSAL", "POSSIBLE_OTHER_CAUSE")[0] == "B2"


def test_known_ae_unlikely():
    assert classify(3, 0.0, True, False, "UNLIKELY", "NO_ALTERNATIVE")[0] == "C"


def test_not_known_ae_temporal_low_nci():
    assert classify(3, 0.0, False, True, "STRONG_CAUSAL", "NO_ALTERNATIVE")[0] == "B1"


def test_not_known_ae_temporal_high_nci():
    assert classify(3, 0.5, False, True, "STRONG_CAUSAL", "POSSIBLE_OTHER_CAUSE")[0] == "B2"


def test_not_known_ae_no_temporal():
    assert classify(3, 0.0, False, False, "UNLIKELY", "NO_ALTERNATIVE")[0] == "C"


def test_nci_threshold():
    assert classify(3, 0.7, True, True, "STRONG_CAUSAL", "DEFINITE_OTHER_CAUSE")[0] == "C"


def test_determinism():
    results = set()
    for _ in range(10):
        cat, _ = classify(3, 0.35, True, True, "STRONG_CAUSAL", "WEAK_ALTERNATIVE")
        results.add(cat)
    assert len(results) == 1


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        try:
            t()
            print(f"  PASS: {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL: {t.__name__} -- {e}")
            sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
