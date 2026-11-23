@echo off
rem Backend-tests (pytest) en browsertests (Playwright). Eenmalig: npx playwright install chromium
cd /d "%~dp0..\backend"
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt >nul
".venv\Scripts\python.exe" -m pytest -q || exit /b 1
cd ..\frontend
call npx playwright test
pause
