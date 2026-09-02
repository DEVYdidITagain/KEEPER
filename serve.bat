@echo off
REM Serves the audit page as a real website on your machine.
REM Only the 'public' folder is exposed - your config and log stay private.
cd /d "%~dp0"
if not exist public\audit.html (
  echo No report yet. Run check.bat first.
  pause
  exit /b
)
echo.
echo   Audit page:  http://localhost:8000/audit.html
echo.
echo   On your phone, same wifi, use this machine's IP instead of localhost:
ipconfig | findstr /C:"IPv4"
echo.
echo   Press Ctrl+C to stop the server.
echo.
start "" http://localhost:8000/audit.html
python -m http.server 8000 --directory public
