"""Quick verification script for pipeline results."""
import sys
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

df = pd.read_csv("results/summary_sample_1_20260215_005329.csv")

print("=== RESULT VERIFICATION ===")
print(f"Total cases: {len(df)}")
print(f"Error cases: {df['errors'].sum()}")

print("\n--- WHO Category Distribution ---")
print(df["who_category"].value_counts().to_string())

print("\n--- Brighton Level Distribution ---")
print(df["brighton_level"].value_counts().sort_index().to_string())

print("\n--- Shadow Scoring Analysis ---")
shadow_df = df[df["shadow_applied"] == True]
print(f"Shadow applied: {len(shadow_df)} cases")
print(f"Condition types with shadow: {shadow_df['condition_type'].tolist()}")
all_peri = all(c == "pericarditis" for c in shadow_df["condition_type"])
print(f"Only applied to pericarditis: {'PASS' if all_peri else 'FAIL'}")

print("\n--- Detailed Case Results ---")
for _, r in df.iterrows():
    print(
        f"  {r['vaers_id']:>8} | {r['condition_type']:12} | {r['group']:12} "
        f"| WHO={r['who_category']:3} | Brighton=L{r['brighton_level']} "
        f"| Shadow={str(r['shadow_applied']):5} | Zone={r['temporal_zone']:15} "
        f"| Onset={r['days_to_onset']}d | Time={r['total_time_s']:.1f}s"
    )
