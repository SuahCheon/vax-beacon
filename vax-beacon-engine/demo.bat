@echo off
chcp 65001 >nul
python demo_run.py
echo.
echo ============================================================
echo   OFFICER REPORT: VAERS 1549179
echo ============================================================
echo.
type reports\VAERS_1549179_v4.md
echo.
echo ============================================================
echo   Vax-Beacon: Expert pharmacovigilance on a consumer GPU
echo ============================================================
pause