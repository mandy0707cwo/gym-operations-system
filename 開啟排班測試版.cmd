@echo off
setlocal
cd /d "%~dp0"
set "SCHEDULE_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%SCHEDULE_PYTHON%" set "SCHEDULE_PYTHON=python"
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8514 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 (
  start "" "http://127.0.0.1:8514/"
  exit /b 0
)
set "PYTHONIOENCODING=utf-8"
echo Starting local v1.13.29 test app. Keep this window open while testing.
echo Demo data only. No production update.
"%SCHEDULE_PYTHON%" -m streamlit run schedule_demo.py --server.address 127.0.0.1 --server.port 8514 --server.headless false --browser.gatherUsageStats false
if errorlevel 1 (
  echo Startup failed. Please share the error message, not passwords.
  pause
)
endlocal
