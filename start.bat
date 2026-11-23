@echo off
setlocal
title Vetera Intelligence
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
  echo De app is nog niet geinstalleerd. Voer eerst install.bat uit.
  pause & exit /b 1
)
if not exist "frontend\dist\index.html" (
  echo De frontend is nog niet gebouwd. Voer eerst install.bat uit.
  pause & exit /b 1
)
echo Vetera Intelligence wordt gestart op http://localhost:3000
echo Sluit dit venster om de app te stoppen.
start "" /b cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:3000"
pushd backend
".venv\Scripts\python.exe" run.py
popd
