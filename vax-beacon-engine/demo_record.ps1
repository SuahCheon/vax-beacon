# ============================================================
# Vax-Beacon Demo Recording Script (PowerShell) — FINAL
# ============================================================
# Case 1 (1549179 A1):  LIVE execution (~40s)
# Case 2 (1347846 C):   pre-computed report
#
# INSTRUCTIONS:
#   1. cd C:\vska_original\data\vaers\vax_beacon
#   2. Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   3. Start screen recording
#   4. Run: .\demo_record.ps1
#   5. Stop recording
# ============================================================

Clear-Host

# ============================================================
# INTRO
# ============================================================
Write-Host ""
Write-Host "  +================================================================+" -ForegroundColor Cyan
Write-Host "  |                                                                |" -ForegroundColor Cyan
Write-Host "  |   VAX-BEACON: AI-Powered AEFI Causality Assessment            |" -ForegroundColor Cyan
Write-Host "  |                                                                |" -ForegroundColor Cyan
Write-Host "  |   Multi-Agent Pipeline for WHO Vaccine Safety Surveillance     |" -ForegroundColor Cyan
Write-Host "  |   MedGemma 4B  |  4-bit Quantized  |  3.2 GB VRAM            |" -ForegroundColor Cyan
Write-Host "  |   100-Case VAERS Benchmark  |  Consumer GPU (RTX 4050)        |" -ForegroundColor Cyan
Write-Host "  |                                                                |" -ForegroundColor Cyan
Write-Host "  |   Design Principle: LLMs OBSERVE, Deterministic Code DECIDES  |" -ForegroundColor Cyan
Write-Host "  |                                                                |" -ForegroundColor Cyan
Write-Host "  +================================================================+" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Pipeline Architecture:" -ForegroundColor White
Write-Host "    Stage 1  ICSR Extractor .............. LLM" -ForegroundColor Gray
Write-Host "    Stage 2  Brighton Validator .......... Deterministic Code" -ForegroundColor Yellow
Write-Host "    Stage 3A Clinical Observer ........... LLM" -ForegroundColor Gray
Write-Host "    Stage 3B DDx Matcher ................. Deterministic Code" -ForegroundColor Yellow
Write-Host "    Stage 3C Plausibility Assessor ....... LLM" -ForegroundColor Gray
Write-Host "    Stage 3D NCI Calculator .............. Deterministic Code" -ForegroundColor Yellow
Write-Host "    Stage 4  Temporal Auditor ............ Deterministic Code" -ForegroundColor Yellow
Write-Host "    Stage 5  WHO Causality Assessor ...... Deterministic Code + LLM" -ForegroundColor Yellow
Write-Host "    Stage 6  Investigation Advisor ....... LLM + Knowledge Base" -ForegroundColor Gray
Write-Host ""
Start-Sleep -Seconds 8

Clear-Host

# ============================================================
# CASE 1: A1 -- LIVE EXECUTION
# ============================================================
Write-Host ""
Write-Host "  +--------------------------------------------------------------+" -ForegroundColor Green
Write-Host "  |  CASE 1 of 2: VAERS 1549179  *** LIVE EXECUTION ***         |" -ForegroundColor Green
Write-Host "  |                                                              |" -ForegroundColor Green
Write-Host "  |  14-year-old male  |  Pfizer Dose 2  |  Myocarditis Day 3   |" -ForegroundColor Green
Write-Host "  |  Expected: WHO Category A1 (Vaccine-Associated)              |" -ForegroundColor Green
Write-Host "  |                                                              |" -ForegroundColor Green
Write-Host "  |  Classic presentation: young male, mRNA dose 2, onset in     |" -ForegroundColor Green
Write-Host "  |  peak incidence window (Day 2-4), no alternative etiology.   |" -ForegroundColor Green
Write-Host "  +--------------------------------------------------------------+" -ForegroundColor Green
Write-Host ""
Start-Sleep -Seconds 5

Write-Host "  -> LIVE: Running full 9-stage pipeline (MedGemma 4B, 4-bit)..." -ForegroundColor White
Write-Host ""
python main.py --case 1549179
Write-Host ""
Start-Sleep -Seconds 3

Write-Host "  +------------------------------------------------+" -ForegroundColor Green
Write-Host "  |  Full Report: VAERS 1549179 (LIVE)             |" -ForegroundColor Green
Write-Host "  +------------------------------------------------+" -ForegroundColor Green
Write-Host ""
Get-Content reports\VAERS_1549179_v4.md
Write-Host ""
Start-Sleep -Seconds 10

Clear-Host

# ============================================================
# CASE 2: C -- Pre-computed Report (DDx Showcase)
# ============================================================
Write-Host ""
Write-Host "  +--------------------------------------------------------------+" -ForegroundColor Red
Write-Host "  |  CASE 2 of 2: VAERS 1347846                                 |" -ForegroundColor Red
Write-Host "  |                                                              |" -ForegroundColor Red
Write-Host "  |  31-year-old male  |  Moderna Dose 2  |  Myocarditis Day 3  |" -ForegroundColor Red
Write-Host "  |  LVEF 34%  |  Parvovirus B19 IgM+  |  Leukocytosis 20K     |" -ForegroundColor Red
Write-Host "  |  Expected: WHO Category C (Coincidental)                     |" -ForegroundColor Red
Write-Host "  |                                                              |" -ForegroundColor Red
Write-Host "  |  Differential diagnosis test: despite Day 3 onset (peak      |" -ForegroundColor Red
Write-Host "  |  mRNA window), Parvovirus B19 positivity triggers NCI >=     |" -ForegroundColor Red
Write-Host "  |  0.7 -> definite other cause. The treating physician was     |" -ForegroundColor Red
Write-Host "  |  uncertain: 'unclear whether atypical viral myocarditis      |" -ForegroundColor Red
Write-Host "  |  or vaccine related.' Pipeline resolved the ambiguity.       |" -ForegroundColor Red
Write-Host "  +--------------------------------------------------------------+" -ForegroundColor Red
Write-Host ""
Start-Sleep -Seconds 7

Write-Host "  +------------------------------------------------+" -ForegroundColor Red
Write-Host "  |  Report: VAERS 1347846 (MedGemma 4B)          |" -ForegroundColor Red
Write-Host "  +------------------------------------------------+" -ForegroundColor Red
Write-Host ""
Get-Content reports\VAERS_1347846_v4.md
Write-Host ""
Start-Sleep -Seconds 10

Clear-Host

# ============================================================
# CLOSING
# ============================================================
Write-Host ""
Write-Host "  +================================================================+" -ForegroundColor Cyan
Write-Host "  |                                                                |" -ForegroundColor Cyan
Write-Host "  |   VAX-BEACON -- Demo Complete                                  |" -ForegroundColor Cyan
Write-Host "  |                                                                |" -ForegroundColor Cyan
Write-Host "  +================================================================+" -ForegroundColor Cyan
Write-Host ""
Write-Host "  2 Cases Demonstrated:" -ForegroundColor White
Write-Host ""
Write-Host "    Case 1549179 -> " -NoNewline -ForegroundColor White
Write-Host "A1  (Vaccine-Associated)" -ForegroundColor Green
Write-Host "      Classic mRNA myocarditis, no alternative etiology" -ForegroundColor Gray
Write-Host "      Full 9-stage pipeline, 40s on consumer GPU" -ForegroundColor Gray
Write-Host ""
Write-Host "    Case 1347846 -> " -NoNewline -ForegroundColor White
Write-Host "C   (Coincidental)" -ForegroundColor Red
Write-Host "      Parvovirus B19+ overrides temporal plausibility" -ForegroundColor Gray
Write-Host "      NCI scoring resolved physician uncertainty" -ForegroundColor Gray
Write-Host ""
Write-Host "  +----------------------------------------------------------------+" -ForegroundColor Cyan
Write-Host ""
Write-Host "  100-Case Benchmark:" -ForegroundColor White
Write-Host "    A1: 43%  |  C: 27%  |  UC: 25%  |  B2: 5%" -ForegroundColor Gray
Write-Host "    Pipeline completion: 98/100 (98%)" -ForegroundColor Gray
Write-Host ""
Write-Host "  Key Insight:" -ForegroundColor White
Write-Host "    Deterministic architecture ensures classification" -ForegroundColor Gray
Write-Host "    accuracy is independent of LLM capability." -ForegroundColor Gray
Write-Host "    A 3.2 GB model achieves expert-level assessment" -ForegroundColor Gray
Write-Host "    when supported by the right pipeline design." -ForegroundColor Gray
Write-Host ""
Write-Host "  github.com/SuahCheon/vax-beacon" -ForegroundColor Cyan
Write-Host ""
Write-Host "  +================================================================+" -ForegroundColor Cyan
Write-Host ""
Start-Sleep -Seconds 10
