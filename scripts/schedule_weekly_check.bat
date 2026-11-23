@echo off
rem Registreert een wekelijkse Windows-taak (maandag 09:00). Draait alleen als de computer aan staat;
rem 'StartWhenAvailable' laat een gemiste taak zo snel mogelijk alsnog uitvoeren.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0schedule_weekly_check.ps1"
pause
