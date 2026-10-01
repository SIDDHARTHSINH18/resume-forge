@echo off
rem Start the backend API on http://127.0.0.1:8100 (serves frontend/dist when built).
cd /d "%~dp0..\backend"
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100
