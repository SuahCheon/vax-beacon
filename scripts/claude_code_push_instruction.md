# Vax-Beacon GitHub Push — Claude Code Instructions

## Context
- Repo: https://github.com/SuahCheon/vax-beacon.git
- Local: `C:\vska_original\data\vaers\vax_beacon`
- This is an UPDATE push (repo already has initial commit)
- Key changes: docs/cohort_curation_guide.md added, .gitignore updated

## Pre-Push Checklist (run ALL before committing)

### 1. Verify .gitignore is correct
```bash
cat .gitignore
```
Confirm these lines exist:
- `docs/*.pdf`
- `docs/technical_overview.md`
- `reports/*.md`, `reports/*.docx`
- `results/*` with `!results/benchmark_*.csv` and `!results/.gitkeep`
- `.env`, `__pycache__/`, `.claude/`

### 2. Verify NO API keys in tracked files
```bash
grep -r "sk-ant-" --include="*.py" --include="*.json" --include="*.md" .
```
Expected: NO output. If any match found, DO NOT PROCEED.

### 3. Verify docs/ will only include md + json
```bash
git status docs/
```
Expected tracked files in docs/:
- `docs/cohort_curation_guide.md` ✓
- `docs/schema.json` ✓
- `docs/technical_overview.md` ✗ (gitignored)
- `docs/*.pdf` ✗ (gitignored)

### 4. Verify results/ only includes benchmark CSV + .gitkeep
```bash
git add -n results/
```
Expected: only `results/benchmark_*.csv` and `results/.gitkeep`

### 5. Verify reports/ only includes .gitkeep
```bash
git add -n reports/
```
Expected: only `reports/.gitkeep`

### 6. Verify no __pycache__ or .claude
```bash
find . -name "__pycache__" -o -name ".claude" | head -20
```
These should NOT be in git staging.

### 7. Verify no "HexaVax" references in active code
```bash
grep -ri "hexavax" --include="*.py" --include="*.md" . | grep -v ".gitignore" | grep -v "__pycache__"
```
Expected: NO output in active code files. (OK if found in old PDF filenames which are gitignored anyway)

## Push Commands

```bash
cd C:\vska_original\data\vaers\vax_beacon

# Stage all changes
git add -A

# Verify what will be committed
git status

# Commit
git commit -m "docs: add cohort curation guide, update .gitignore

- Add docs/cohort_curation_guide.md (N=100 cohort design, group definitions, case registry, benchmark results)
- Update .gitignore: exclude docs/*.pdf and docs/technical_overview.md
- Exclude PDFs from docs/ (size + legacy HexaVax naming)"

# Push
git push origin main
```

## Post-Push Verification

After push, verify on GitHub:
1. `docs/cohort_curation_guide.md` renders correctly
2. `docs/schema.json` present
3. No PDF files in `docs/`
4. No `technical_overview.md` in `docs/`
5. No `.env` file anywhere
6. `results/benchmark_*.csv` present
7. `reports/` contains only `.gitkeep`
