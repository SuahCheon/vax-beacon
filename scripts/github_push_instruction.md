# Push Vax-Beacon to GitHub

## Pre-Push Checklist (MUST verify ALL before committing)

### 1. Update .gitignore

Replace the ENTIRE .gitignore with:

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/

# Environment
.env
.venv/
venv/

# IDE
.vscode/
.idea/
.claude/

# OS
Thumbs.db
.DS_Store
NUL

# Generated reports
reports/*.md
reports/*.docx

# Results — only benchmark CSV is committed
results/*
!results/benchmark_*.csv
!results/.gitkeep
```

### 2. Verify sensitive files are excluded

Run these checks and STOP if any fail:

```bash
# MUST NOT exist in staging area
git status | findstr ".env"
# Should return nothing

# API key check — scan all tracked files
grep -r "sk-ant-\|ANTHROPIC_API_KEY.*=.*sk" --include="*.py" --include="*.json" --include="*.md" .
# Should return nothing (only os.environ.get references are OK)
```

### 3. Verify file structure

```bash
# Root level — should NOT have these:
# - NUL (deleted)
# - agents/ (deleted)
# - analyze_*.py (moved to scripts/)
# - compare_*.py (moved to scripts/)
# - verify_results.py (moved to scripts/)

dir /b *.py
# Expected: main.py, config.py, llm_client.py, data_loader.py, knowledge_loader.py, report_renderer.py
```

### 4. Verify results/ will only commit benchmark CSV

```bash
git add -A --dry-run | findstr "results/"
# Should show ONLY:
#   results/.gitkeep
#   results/benchmark_v4_full_100_20260217_115831.csv
# Should NOT show any .json or summary_*.csv
```

### 5. Verify reports/ will only commit .gitkeep

```bash
git add -A --dry-run | findstr "reports/"
# Should show ONLY:
#   reports/.gitkeep
# Should NOT show any .md or .docx files
```

### 6. Verify no __pycache__ will be committed

```bash
git add -A --dry-run | findstr "__pycache__"
# Should return nothing
```

### 7. Check for old HexaVax references in committed files

```bash
grep -r "HexaVax" --include="*.py" --include="*.md" --include="*.json" --include="*.mermaid" . | findstr /v "results\\ _legacy\\ scripts\\ docs\\HexaVax"
# Should return nothing in active code
```

## Push Commands

Only proceed if ALL checks above pass:

```bash
cd C:\vska_original\data\vaers\vax_beacon

# Remove existing .git if inherited from parent repo
if exist .git rmdir /s /q .git

# Fresh init
git init
git add -A

# Verify what will be committed
git status

# Commit
git commit -m "initial: Vax-Beacon v4.3 — Multi-Agent AEFI Causality Pipeline"

# Connect to GitHub and push
git branch -M main
git remote add origin https://github.com/SuahCheon/vax-beacon.git
git push -u origin main
```

## Post-Push Verification

After push, check on GitHub:
1. README.md renders correctly with architecture diagram
2. No .env file visible
3. results/ contains only benchmark CSV + .gitkeep
4. reports/ contains only .gitkeep
5. No __pycache__ directories
6. pipeline/ has all stage files including renamed stage4_auditor.py and stage5_causality_assessor.py
