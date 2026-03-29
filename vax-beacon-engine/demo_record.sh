#!/bin/bash
# ============================================================
# Vax-Beacon Demo Recording Script
# ============================================================
# INSTRUCTIONS:
#   1. cd to vax_beacon directory
#   2. Start screen recording (OBS, Windows Game Bar, etc.)
#   3. Run: bash demo_record.sh
#   4. Stop recording
#   5. Speed up to 2x in editor
#
# Expected raw time: ~3.5 min → 2x = ~1:45
# ============================================================

clear

# ============================================================
# INTRO
# ============================================================
echo ""
echo "  ╔══════════════════════════════════════════════════════════════════╗"
echo "  ║                                                                ║"
echo "  ║   VAX-BEACON: AI-Powered AEFI Causality Assessment            ║"
echo "  ║                                                                ║"
echo "  ║   Multi-Agent Pipeline for WHO Vaccine Safety Surveillance     ║"
echo "  ║   MedGemma 4B  |  4-bit Quantized  |  3.2 GB VRAM            ║"
echo "  ║   100-Case VAERS Benchmark  |  Consumer GPU (RTX 4050)        ║"
echo "  ║                                                                ║"
echo "  ║   Design Principle: LLMs OBSERVE, Deterministic Code DECIDES  ║"
echo "  ║                                                                ║"
echo "  ╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  Pipeline Architecture:"
echo "    Stage 1  ICSR Extractor .............. LLM"
echo "    Stage 2  Brighton Validator .......... Deterministic Code"
echo "    Stage 3A Clinical Observer ........... LLM"
echo "    Stage 3B DDx Matcher ................. Deterministic Code"
echo "    Stage 3C Plausibility Assessor ....... LLM"
echo "    Stage 3D NCI Calculator .............. Deterministic Code"
echo "    Stage 4  Temporal Auditor ............ Deterministic Code"
echo "    Stage 5  WHO Causality Assessor ...... Deterministic Code + LLM"
echo "    Stage 6  Investigation Advisor ....... LLM + Knowledge Base"
echo ""
sleep 10

clear

# ============================================================
# CASE 1: A1 — Vaccine-Associated (Classic)
# ============================================================
echo ""
echo "  ┌──────────────────────────────────────────────────────────────┐"
echo "  │  CASE 1 of 3: VAERS 1549179                                 │"
echo "  │                                                              │"
echo "  │  14-year-old male  |  Pfizer Dose 2  |  Myocarditis Day 3   │"
echo "  │  Expected: WHO Category A1 (Vaccine-Associated)              │"
echo "  │                                                              │"
echo "  │  Why this case: Classic presentation — young male, mRNA D2,  │"
echo "  │  peak incidence window, no alternative etiology.             │"
echo "  └──────────────────────────────────────────────────────────────┘"
echo ""
sleep 5

echo "  → Running full pipeline (Stages 1-6)..."
echo ""
python main.py --case 1549179
echo ""
sleep 3

echo "  ┌──────────────────────────────────────────────────┐"
echo "  │  Full Report: VAERS 1549179                      │"
echo "  └──────────────────────────────────────────────────┘"
echo ""
cat reports/VAERS_1549179_v4.md
echo ""
sleep 8

clear

# ============================================================
# CASE 2: C — Viral DDx (Parvovirus B19)
# ============================================================
echo ""
echo "  ┌──────────────────────────────────────────────────────────────┐"
echo "  │  CASE 2 of 3: VAERS 1347846                                 │"
echo "  │                                                              │"
echo "  │  31-year-old male  |  Moderna Dose 2  |  Myocarditis Day 3  │"
echo "  │  LVEF 34%  |  Parvovirus B19 IgM+  |  Leukocytosis 20K     │"
echo "  │  Expected: WHO Category C (Coincidental)                     │"
echo "  │                                                              │"
echo "  │  Why this case: Tests differential diagnosis capability.     │"
echo "  │  Despite Day 3 onset (peak mRNA window), Parvovirus B19     │"
echo "  │  positivity triggers NCI >= 0.7 → definite other cause.     │"
echo "  │  The treating physician was uncertain: 'unclear whether      │"
echo "  │  atypical viral myocarditis or vaccine related.'             │"
echo "  └──────────────────────────────────────────────────────────────┘"
echo ""
sleep 7

echo "  → Running full pipeline (Stages 1-6)..."
echo ""
python main.py --case 1347846
echo ""
sleep 3

echo "  ┌──────────────────────────────────────────────────┐"
echo "  │  Full Report: VAERS 1347846                      │"
echo "  └──────────────────────────────────────────────────┘"
echo ""
cat reports/VAERS_1347846_v4.md
echo ""
sleep 8

clear

# ============================================================
# CASE 3: Unclassifiable — Brighton L4 Early Exit
# ============================================================
echo ""
echo "  ┌──────────────────────────────────────────────────────────────┐"
echo "  │  CASE 3 of 3: VAERS 1321207                                 │"
echo "  │                                                              │"
echo "  │  18-year-old male  |  Pfizer  |  Chest Pain Day 5           │"
echo "  │  No troponin, no ECG, no echo, no MRI documented            │"
echo "  │  Expected: Unclassifiable (Brighton L4 Early Exit)           │"
echo "  │                                                              │"
echo "  │  Why this case: 24% of our 100-case cohort are data-poor    │"
echo "  │  reports like this. The pipeline safely refuses to classify  │"
echo "  │  without evidence, skips Stages 3-5, and instead generates  │"
echo "  │  a concrete investigation plan for the field officer.        │"
echo "  │                                                              │"
echo "  │  This is Vax-Beacon's primary real-world value.             │"
echo "  └──────────────────────────────────────────────────────────────┘"
echo ""
sleep 7

echo "  → Running pipeline (Stages 1-2, then Early Exit to Stage 6)..."
echo ""
python main.py --case 1321207
echo ""
sleep 3

echo "  ┌──────────────────────────────────────────────────┐"
echo "  │  Full Report: VAERS 1321207                      │"
echo "  └──────────────────────────────────────────────────┘"
echo ""
cat reports/VAERS_1321207_v4.md
echo ""
sleep 8

clear

# ============================================================
# CLOSING
# ============================================================
echo ""
echo "  ╔══════════════════════════════════════════════════════════════════╗"
echo "  ║                                                                ║"
echo "  ║   VAX-BEACON — Demo Complete                                   ║"
echo "  ║                                                                ║"
echo "  ╠══════════════════════════════════════════════════════════════════╣"
echo "  ║                                                                ║"
echo "  ║   3 Cases Demonstrated:                                        ║"
echo "  ║                                                                ║"
echo "  ║     Case 1549179 → A1  (Vaccine-Associated)                   ║"
echo "  ║       Classic mRNA myocarditis, no alternative etiology        ║"
echo "  ║                                                                ║"
echo "  ║     Case 1347846 → C   (Coincidental)                         ║"
echo "  ║       Parvovirus B19+ overrides temporal plausibility          ║"
echo "  ║       NCI scoring resolved physician uncertainty               ║"
echo "  ║                                                                ║"
echo "  ║     Case 1321207 → UC  (Unclassifiable — Brighton L4)         ║"
echo "  ║       Safe early exit, actionable investigation guidance       ║"
echo "  ║       Represents 24% of passive surveillance reports           ║"
echo "  ║                                                                ║"
echo "  ╠══════════════════════════════════════════════════════════════════╣"
echo "  ║                                                                ║"
echo "  ║   100-Case Benchmark:                                          ║"
echo "  ║     A1: 43%  |  C: 27%  |  UC: 25%  |  B2: 5%               ║"
echo "  ║     Claude concordance: 54.1%                                  ║"
echo "  ║     Showcase accuracy: 4/4 (100%)                              ║"
echo "  ║     Pipeline completion: 98/100 (98%)                          ║"
echo "  ║                                                                ║"
echo "  ║   Key Insight:                                                 ║"
echo "  ║     Deterministic architecture ensures classification          ║"
echo "  ║     accuracy is independent of LLM capability.                 ║"
echo "  ║     A 3.2 GB model achieves expert-level assessment            ║"
echo "  ║     when supported by the right pipeline design.               ║"
echo "  ║                                                                ║"
echo "  ║   github.com/SuahCheon/vax-beacon                             ║"
echo "  ║                                                                ║"
echo "  ╚══════════════════════════════════════════════════════════════════╝"
echo ""
sleep 12
