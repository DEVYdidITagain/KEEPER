@echo off
REM Double-click this to run the audit and open the report.
REM Settings live in keeper.config.json - no arguments needed here.
cd /d "%~dp0"
python keeper_audit.py --receipts --open
echo.
pause
