@echo off
setlocal
title Vetera Intelligence - installatie
cd /d "%~dp0"
echo.
echo  Vetera Intelligence - installatie
echo  ==================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo [FOUT] Python 3.11 of nieuwer is niet gevonden. Installeer Python via https://www.python.org/downloads/
  echo        en vink "Add python.exe to PATH" aan.
  pause & exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
  echo [FOUT] Node.js is niet gevonden. Installeer Node.js 20 LTS of nieuwer via https://nodejs.org/
  pause & exit /b 1
)

echo [1/4] Python-omgeving aanmaken...
if not exist "backend\.venv\Scripts\python.exe" (
  %PY% -m venv backend\.venv || (echo [FOUT] venv aanmaken mislukt & pause & exit /b 1)
)
echo [2/4] Python-pakketten installeren...
"backend\.venv\Scripts\python.exe" -m pip install --upgrade pip >nul
"backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt || (echo [FOUT] pip install mislukt & pause & exit /b 1)

echo [3/4] Frontend installeren en bouwen...
pushd frontend
call npm install --no-audit --no-fund || (popd & echo [FOUT] npm install mislukt & pause & exit /b 1)
call npm run build || (popd & echo [FOUT] frontend bouwen mislukt & pause & exit /b 1)
popd

echo [4/4] Configuratie en database...
if not exist "backend\.env" copy "backend\.env.example" "backend\.env" >nul
pushd backend
".venv\Scripts\python.exe" -m app.cli migrate || (popd & echo [FOUT] database-migratie mislukt & pause & exit /b 1)
popd

echo.
echo  Installatie voltooid.
echo  - Start de app met start.bat
echo  - Optioneel: zet je Anthropic API-sleutel in backend\.env (ANTHROPIC_API_KEY=...)
echo  - Optioneel: plan de wekelijkse broncontrole met scripts\schedule_weekly_check.bat
echo.
pause
