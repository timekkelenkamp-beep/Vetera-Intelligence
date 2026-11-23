@echo off
rem Wordt door Windows Taakplanner uitgevoerd. Logt naar data\monitor.log
cd /d "%~dp0..\backend"
if not exist "..\data" mkdir "..\data"
".venv\Scripts\python.exe" -m app.cli weekly-check >> "..\data\monitor.log" 2>&1
