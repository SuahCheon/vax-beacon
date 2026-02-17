# 100-Case Batch Run: Comparison CSV + Individual Reports

## Overview

Three changes to main.py:
1. Generate individual .md reports for every case in batch runs
2. Generate a new `benchmark_*.csv` alongside existing summary CSV
3. Use Haiku to generate `key_logic_reasoning` one-sentence summary per case

## Step 1: Add Haiku Model Config to config.py

```python
# Add after ANTHROPIC_MODEL line:
ANTHROPIC_MODEL_LIGHT = "claude-haiku-4-5-20251001"  # Lightweight model for summaries
```

## Step 2: Add Haiku query method to llm_client.py

Add a new method to LLMClient class:

```python
def query_light(self, system_prompt: str, user_message: str) -> str:
    """Send a query using the lightweight model (Haiku). For summaries only."""
    if self.backend == "anthropic":
        from config import ANTHROPIC_MODEL_LIGHT
        response = self.client.messages.create(
            model=ANTHROPIC_MODEL_LIGHT,
            max_tokens=256,
            temperature=0.0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip()
    elif self.backend == "medgemma":
        # Use same model for light queries in MedGemma backend
        raise NotImplementedError
```

## Step 3: Add benchmark CSV generation to main.py

### Add new function: `generate_benchmark_csv()`

```python
def generate_benchmark_csv(llm: LLMClient, results: list, tag: str = ""):
    """
    Generate benchmark comparison CSV with key_logic_reasoning via Haiku.
    Columns: vaers_id, brighton_level, max_nci_score, dominant_alternative,
             who_category, guidance_type, key_logic_reasoning
    """
    import os
    from datetime import datetime

    REASONING_SYSTEM = (
        "You are a medical regulatory expert. Given a WHO AEFI causality assessment result, "
        "produce exactly ONE sentence (max 30 words) explaining WHY this case received its WHO category. "
        "Focus on the decisive factor (temporal, NCI, Brighton level, etc). "
        "Do not include the category name itself. English only."
    )

    rows = []
    total = len(results)

    for i, r in enumerate(results):
        vaers_id = r["vaers_id"]
        s2 = r.get("stages", {}).get("stage2_brighton", {})
        s3 = r.get("stages", {}).get("stage3_ddx", {})
        s5 = r.get("stages", {}).get("stage5_causality", {})
        s6 = r.get("stages", {}).get("stage6_guidance", {})

        # WHO category
        who_cat = s5.get("who_category") or s6.get("who_category", "ERROR")

        # Guidance type: check if knowledge DB protocol was injected
        has_protocol = bool(s6.get("investigation_protocol"))
        guidance_type = "protocol_injection" if has_protocol else "gap_analysis"

        # Key logic reasoning via Haiku
        reasoning_input = (
            f"VAERS {vaers_id}: Brighton L{s2.get('brighton_level', '?')}, "
            f"NCI={s3.get('max_nci_score', 0)}, "
            f"Dominant alt: {s3.get('dominant_alternative', 'none')}, "
            f"Temporal zone: {r.get('stages', {}).get('stage4_temporal', {}).get('temporal_assessment', {}).get('temporal_zone', '?')}, "
            f"Days: {r.get('stages', {}).get('stage4_temporal', {}).get('temporal_assessment', {}).get('days_to_onset', '?')}, "
            f"WHO: {who_cat}, "
            f"Early exit: {r.get('early_exit', False)}"
        )

        try:
            key_reasoning = llm.query_light(REASONING_SYSTEM, reasoning_input)
        except Exception as e:
            key_reasoning = f"[Error: {e}]"

        if (i + 1) % 10 == 0:
            print(f"  [Benchmark] {i+1}/{total} reasoning summaries generated")

        rows.append({
            "vaers_id": vaers_id,
            "brighton_level": s2.get("brighton_level"),
            "max_nci_score": s3.get("max_nci_score", 0.0),
            "dominant_alternative": s3.get("dominant_alternative", "NONE"),
            "who_category": who_cat,
            "guidance_type": guidance_type,
            "key_logic_reasoning": key_reasoning,
        })

    # Save
    os.makedirs(RESULTS_PATH, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag_str = f"_{tag}" if tag else ""
    csv_path = os.path.join(RESULTS_PATH, f"benchmark{tag_str}_{timestamp}.csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\nBenchmark CSV: {csv_path}")
    return csv_path
```

### Add new function: `generate_batch_reports()`

```python
def generate_batch_reports(results: list):
    """Generate individual .md reports for all cases in a batch run."""
    from report_renderer import render_report
    count = 0
    errors = 0
    for r in results:
        try:
            render_report(r)
            count += 1
        except Exception as e:
            print(f"  [Report] Error on VAERS {r.get('vaers_id', '?')}: {e}")
            errors += 1
    print(f"\nReports: {count} generated, {errors} errors → reports/")
```

### Modify main() — add to post-pipeline section

After the existing `save_results(results, tag=tag)` and `print_summary_stats(results)` lines:

```python
    save_results(results, tag=tag)
    print_summary_stats(results)

    # Generate individual reports for all runs (batch and single)
    generate_batch_reports(results)

    # Generate benchmark CSV (Haiku reasoning summaries)
    print("\n  Generating benchmark CSV with Haiku reasoning summaries...")
    generate_benchmark_csv(llm, results, tag=tag)

    # Single-case docx (if requested)
    if args.case and args.docx and results:
        from report_renderer import render_docx
        md_path = os.path.join("reports", f"VAERS_{args.case}_v4.md")
        if os.path.exists(md_path):
            docx_path = render_docx(md_path)
            if docx_path:
                print(f"Word report: {docx_path}")
```

This replaces the existing single-case report generation block. Now ALL runs (batch and single) generate .md reports. The --docx flag only adds Word conversion for single-case runs.

Remove the old single-case report block if it exists separately.

## Step 4: Handle guidance_type detection

Check if `stage6_guidance` output contains `investigation_protocol` key (from Knowledge DB injection). The field name may vary — check the actual Stage 6 output structure:

```python
# In stage6_guidance_advisor.py, when protocol is injected,
# there should be a field indicating protocol source.
# Check actual output keys and adjust guidance_type detection accordingly.
```

Look at the actual Stage 6 JSON output to determine the correct key. If there's no explicit field, check if `recommended_actions` or `investigation_gaps` contain protocol-sourced content. Use a reasonable heuristic:

```python
# Heuristic: if Stage 6 has protocol-specific fields from Knowledge DB
has_protocol = bool(
    s6.get("investigation_protocol")
    or s6.get("protocol_source")
    or s6.get("etiology_specific_protocol")
)
guidance_type = "protocol_injection" if has_protocol else "gap_analysis"
```

## Step 5: Update .gitignore

Add to .gitignore:
```
reports/*.md
reports/*.docx
```

The benchmark CSV stays in results/ which is already tracked selectively.

## Step 6: Test (single case first)

```bash
# Single case — should generate .md report + benchmark CSV
python main.py --case 1347846

# Verify:
# 1. reports/VAERS_1347846_v4.md exists
# 2. results/benchmark_v4_case_1347846_*.csv exists with 1 row
# 3. key_logic_reasoning column has a one-sentence Haiku summary
```

## Step 7: Run full 100 cases

```bash
python main.py
```

Expected output:
- `results/results_v4_full_100_*.json` (existing)
- `results/summary_v4_full_100_*.csv` (existing)
- `results/benchmark_v4_full_100_*.csv` (NEW — 100 rows, 7 columns)
- `reports/VAERS_*_v4.md` (NEW — ~100 .md files)

Estimated time: ~50min pipeline + ~5min Haiku reasoning = ~55min total

## Step 8: Git commit

```bash
git add main.py llm_client.py config.py
git commit -m "feat: benchmark CSV with Haiku reasoning + batch report generation"
```

## Important Notes

- Haiku calls are sequential (100 calls ≈ 2-3 min, very fast)
- key_logic_reasoning should be English, one sentence, max 30 words
- If Haiku fails on a case, catch the error and fill with `[Error: ...]`
- Do NOT modify existing save_results() or print_summary_stats()
- The benchmark CSV is a NEW separate file, not a modification of existing summary CSV
- guidance_type field needs verification against actual Stage 6 output structure
