@echo off
rem Ontwikkelmodus: backend op 3000 en Vite (hot reload) op http://127.0.0.1:5173
cd /d "%~dp0.."
start "Vetera backend" cmd /k "cd backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 3000 --reload"
cd frontend
call npm run dev
