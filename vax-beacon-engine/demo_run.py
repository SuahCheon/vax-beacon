"""
Vax-Beacon Demo: Single Case Live Pipeline
"""
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

print("=" * 60)
print("  Vax-Beacon v4 | WHO AEFI Causality Assessment Pipeline")
print("  MedGemma 4B (4-bit quantized, 3.2 GB VRAM)")
print("  Consumer GPU: RTX 4050 | 100% Local | Zero Cloud")
print("=" * 60)
print()

from llm_client import LLMClient
llm = LLMClient(backend="medgemma")

from data_loader import load_vaers_data
from main import run_single_case, render_report

df = load_vaers_data()

print()
print("=" * 60)
print("  LIVE DEMO: Vaccine-Associated Myocarditis")
print("  14M, Pfizer D2, Day 3, Brighton L1 | Expected: A1")
print("=" * 60)
print()

t0 = time.time()
row = df[df["VAERS_ID"] == 1549179].iloc[0]
result = run_single_case(llm, row, verbose=True)

try:
    report_path = render_report(result)
    print(f"\n  Report saved: {report_path}")
except Exception as e:
    print(f"\n  Report error: {e}")

elapsed = time.time() - t0
print()
print("=" * 60)
print(f"  Pipeline complete | {elapsed:.0f}s | Consumer GPU")
print("  Now displaying officer report...")
print("=" * 60)
