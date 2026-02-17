# Implement Interactive Mode for Vax-Beacon v4

## Overview

Add `--interactive` (or `-i`) flag to main.py that launches a guided CLI workflow: case selection → pipeline execution → report format selection. All prompts in English.

## Existing CLI (DO NOT CHANGE)

```bash
python main.py                    # 100-case batch (unchanged)
python main.py --case 1347846     # single case (unchanged)
python main.py --sample 2         # sample mode (unchanged)
python main.py --group G2         # group mode (unchanged)
python main.py --case 1347846 --docx  # with Word report (unchanged)
```

## New CLI

```bash
python main.py -i                 # interactive mode
python main.py --interactive      # same thing
```

## Interactive Flow

### Step 1: Welcome Banner

```
══════════════════════════════════════════════════════════
  Vax-Beacon v4.3 | Interactive Case Analysis
  100 cases loaded (90 myocarditis, 10 pericarditis)
══════════════════════════════════════════════════════════

How would you like to select a case?

  [1] Browse case list
  [2] Enter VAERS ID directly
  [3] Filter by group (G1/G2/G3)
  [4] Filter by condition (myocarditis/pericarditis)
  [5] Quit

Select (1-5):
```

### Step 2a: Browse Case List (option 1)

Display paginated table of all 100 cases:

```
  #   VAERS_ID    Age  Sex  Vaccine    Group  Condition
  1   0925542     24   M    MODERNA    G1     myocarditis
  2   0930050     28   M    PFIZER     G1     myocarditis
  3   0943699     52   F    MODERNA    G2     myocarditis
  ...
  -- Page 1/5 (20 per page) --
  [N]ext page  [P]rev page  [#] Select case number  [Q]uit

Select:
```

Implementation:
- Load from `data/vaers_100_cohort.csv`
- Show 20 cases per page
- User enters case number (1-100) to select
- Show basic info from the CSV columns: VAERS_ID, age (AGE_YRS), sex (SEX), vaccine (VAX_NAME or VAX_MANU), group, condition_type

### Step 2b: Enter VAERS ID (option 2)

```
Enter VAERS ID: 1347846

  Found: VAERS 1347846 | 31M | MODERNA Dose 2 | G2 | myocarditis

Proceed? [Y/n]:
```

If not found: `VAERS ID not found in cohort. Try again.`

### Step 2c: Filter by Group (option 3)

```
Available groups:
  [1] G1 - Clean cases (N=xx)
  [2] G2 - Confounded cases (N=xx)
  [3] G3 - Complex cases (N=xx)

Select group (1-3):
```

Then show filtered case list (same format as Step 2a but only matching cases).

### Step 2d: Filter by Condition (option 4)

```
  [1] myocarditis (N=90)
  [2] pericarditis (N=10)

Select (1-2):
```

Then show filtered case list.

### Step 3: Confirm & Run

```
══════════════════════════════════════════════════════════
  Running Vax-Beacon v4.3 on VAERS 1347846
  31M | MODERNA Dose 2 | myocarditis | Group G2
══════════════════════════════════════════════════════════
```

Then execute the normal pipeline (same as `run_single_case()`), showing stage-by-stage progress as usual.

### Step 4: Post-Pipeline — Report Format Selection

After pipeline completes successfully:

```
══════════════════════════════════════════════════════════
  Pipeline Complete | WHO: C | Brighton: L1 | 52.6s
══════════════════════════════════════════════════════════

Generate report?

  [1] Markdown only (.md)
  [2] Markdown + Word (.docx)
  [3] Skip report

Select (1-3):
```

Based on selection:
- Option 1: `render_report(result)` → print path
- Option 2: `render_report(result)` + `render_docx(md_path)` → print both paths
- Option 3: Skip

### Step 5: Continue or Quit

```
What next?

  [1] Analyze another case
  [2] Quit

Select (1-2):
```

Option 1 loops back to Step 1. Option 2 exits.

## Implementation

### File: Do NOT create a new file. Add to `main.py`.

Add a function `run_interactive(llm, df)` that implements the flow above.

### Integration in main()

```python
def main():
    parser = argparse.ArgumentParser(...)
    # ... existing arguments ...
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Launch interactive case selection mode")
    args = parser.parse_args()

    llm = LLMClient(backend="anthropic")
    df = load_vaers_data()

    # Interactive mode takes priority
    if args.interactive:
        run_interactive(llm, df)
        return

    # ... existing logic unchanged ...
```

### Key Implementation Rules

1. Use `input()` for all user prompts
2. Validate all inputs — show error and re-prompt on invalid input
3. Handle Ctrl+C gracefully (print goodbye, exit cleanly)
4. The pipeline execution part reuses `run_single_case()` exactly as-is
5. Report generation reuses existing `render_report()` and `render_docx()`
6. Save results via existing `save_results()` after each case
7. All text in English
8. Keep the interactive function self-contained — don't modify existing functions

### Edge Cases

- VAERS ID not in dataset → re-prompt
- Invalid menu selection → re-prompt
- python-docx not installed + user selects Word → show skip message, generate .md only
- Pipeline error → show error, offer to try another case
- Empty filter result → "No cases match. Try different filter."

## Test

```bash
python main.py -i
```

Walk through:
1. Select option 1 (browse), pick a case, run, generate Markdown
2. Select option 2 (VAERS ID), enter 1313197, run, generate Markdown + Word
3. Select option 3 (filter G2), pick from list
4. Verify existing modes still work:
   - `python main.py --case 1347846` (unchanged)
   - `python main.py --case 1347846 --docx` (unchanged)
   - `python main.py` (100-case batch, unchanged)

## Git

```bash
git add main.py
git commit -m "feat: add --interactive mode for guided case analysis"
```
