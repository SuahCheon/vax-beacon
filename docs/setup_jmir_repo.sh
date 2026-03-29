#!/bin/bash
# ============================================================
# Vax-Beacon JMIR — 별도 repo 생성 + GitHub Pages 배포
# 터미널 또는 Claude Code에서 실행
# ============================================================
set -e

REPO_NAME="vax-beacon-jmir"
GITHUB_USER="SuahCheon"

echo "=== Step 1: Create repo directory ==="
mkdir -p ~/$REPO_NAME
cd ~/$REPO_NAME

echo "=== Step 2: Initialize git ==="
git init
git branch -M main

echo "=== Step 3: Create README ==="
cat > README.md << 'README'
# Vax-Beacon (JMIR Publication Version)

**AI-Generated Investigation Guidance for Vaccine Adverse Event Surveillance**

A neuro-symbolic AI pipeline that processes passive surveillance reports of suspected vaccine adverse events and generates structured investigation guidance for field epidemiologists.

## Live Demo

👉 **[Interactive Case Report Viewer](https://suahcheon.github.io/vax-beacon-jmir/)**

4 representative VAERS myocarditis/pericarditis cases demonstrating distinct pipeline pathways:
- **Brighton L4** → Early exit with targeted investigation guidance
- **WHO A1** → Vaccine-associated with monitoring recommendations
- **WHO B2** → Indeterminate with targeted viral testing guidance
- **WHO C** → Coincidental with escalation for giant cell myocarditis

## Architecture

6-agent, 9-stage neuro-symbolic pipeline:
- **Neural perception**: LLM extracts clinical observations (Claude Sonnet 4)
- **Symbolic reasoning**: Deterministic code executes all classification decisions
- **Investigation guidance**: Structured recommendations via Claude Haiku 4.5

Every classification is reproducible. Every reasoning step is traceable to published evidence.

## Key Design Principle: Designed Deference

When data is too incomplete for assessment (20% of cases), the system doesn't guess — it defers. It generates targeted investigation guidance specifying what tests to order, in what priority, and what certainty level each unlocks.

## Paper

Submitted to **JMIR Public Health and Surveillance** (2026).

> Cheon ME, Son EC. AI-Generated Investigation Guidance for Vaccine Adverse Event Surveillance: Development and Evaluation of a Neuro-Symbolic Causality Assessment Pipeline.

## Related

- **Pipeline code (MedGemma 4B edge deployment version)**: [github.com/SuahCheon/vax-beacon](https://github.com/SuahCheon/vax-beacon)
- **Validation dataset**: [Kaggle](https://www.kaggle.com/datasets/myeongeuncheon/hexavax-maps-100-case-validation-cohort)

## License

MIT
README

echo "=== Step 4: Create docs/ with index.html ==="
mkdir -p docs

# Copy index.html if it exists in a known location, otherwise prompt
if [ -f ~/docs/index.html ]; then
  cp ~/docs/index.html docs/index.html
  echo "✅ Copied index.html from ~/docs/"
elif [ -f ~/Downloads/index.html ]; then
  cp ~/Downloads/index.html docs/index.html
  echo "✅ Copied index.html from ~/Downloads/"
else
  echo ""
  echo "⚠️  docs/index.html not found automatically."
  echo "    Please copy your index.html to: ~/$REPO_NAME/docs/index.html"
  echo "    Then re-run from Step 5 below."
  echo ""
fi

echo "=== Step 5: Create LICENSE ==="
cat > LICENSE << 'LIC'
MIT License

Copyright (c) 2026 Myeong-eun Cheon

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
LIC

echo "=== Step 6: Git add & commit ==="
git add -A
git commit -m "Initial commit: Vax-Beacon JMIR publication version

- Interactive case report viewer (GitHub Pages)
- 4 showcase cases: Brighton L4, WHO A1, B2, C
- Split layout: VAERS original / pipeline output
- Designed Deference investigation guidance"

echo "=== Step 7: Create GitHub repo & push ==="
echo ""
echo "Choose one of these methods:"
echo ""
echo "--- Method A: GitHub CLI (if 'gh' is installed) ---"
echo "  gh repo create $GITHUB_USER/$REPO_NAME --public --source=. --push"
echo ""
echo "--- Method B: Manual ---"
echo "  1. Go to https://github.com/new"
echo "  2. Name: $REPO_NAME"
echo "  3. Public, no README (we already have one)"
echo "  4. Create repository"
echo "  5. Then run:"
echo "     git remote add origin https://github.com/$GITHUB_USER/$REPO_NAME.git"
echo "     git push -u origin main"
echo ""
echo "=== Step 8: Enable GitHub Pages ==="
echo "  1. https://github.com/$GITHUB_USER/$REPO_NAME/settings/pages"
echo "  2. Source: Deploy from a branch"
echo "  3. Branch: main / Folder: /docs"
echo "  4. Save"
echo ""
echo "=== Done! ==="
echo "  Demo URL:  https://$GITHUB_USER.github.io/$REPO_NAME/"
echo "  Repo URL:  https://github.com/$GITHUB_USER/$REPO_NAME"
echo ""
echo "LinkedIn에 이 두 URL을 넣으세요!"
