@echo off
REM Proves the audit log has not been edited. Run this if anyone challenges you.
cd /d "%~dp0"
python keeper_audit.py --verify-log
echo.
pause
