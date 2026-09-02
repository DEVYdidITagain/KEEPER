@echo off
REM Dry run against a live token, using the same promise shape as launch day.
REM Writes to test_* files so it never touches your real audit log or site.
cd /d "%~dp0"
echo Dry run against a live pump.fun token...
echo.
python keeper_audit.py 773HkBm12VrYroNfnZeba3xQSrVkc3uFMFHE5dyupump ^
  --dev-wallet B1bsL7JW52CicRwZdkLvsd7G8fvZtB18QjcpzNPZDUSY ^
  --ops-wallet FCHZSWkhqVUuFughPwataoxGsKr19kW8vuzssNDjapAG ^
  --declared-sol 2 --lock-until 2026-10-15 --ticker "$TESTRUN" ^
  --config nonexistent.json --log-path test_log.jsonl ^
  --report docs/test-audit.html --card docs/test-card.html ^
  --receipts --log --open
echo.
echo Dry run only. Nothing here touches audit_log.jsonl or your live site.
pause
