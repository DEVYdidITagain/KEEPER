@echo off
REM Proves the whole pipeline works BEFORE you have your own coin.
REM Runs a real audit against a live pump.fun token and builds every output.
REM Writes to test_* files so it never touches your real audit log.
cd /d "%~dp0"
echo Dry run against a live token...
echo.
python keeper_audit.py 773HkBm12VrYroNfnZeba3xQSrVkc3uFMFHE5dyupump ^
  --dev-wallet suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK ^
  --declared-pct 3 --lock-until 2026-10-15 --ticker "$TESTRUN" ^
  --config nonexistent.json --log-path test_log.jsonl ^
  --report docs/test-audit.html --card docs/test-card.html ^
  --receipts --log --open
echo.
echo Dry run only. test_log.jsonl is separate from your real audit_log.jsonl.
pause
