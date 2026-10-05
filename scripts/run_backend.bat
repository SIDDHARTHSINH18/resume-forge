@echo off
rem Start the Resume-Forge backend API on http://127.0.0.1:8421 (serves frontend/dist when built).
rem Override the port with BACKEND_PORT if ever needed (must match the frontend proxy).
cd /d "%~dp0..\backend"
if "%BACKEND_PORT%"=="" set BACKEND_PORT=8421
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT%
