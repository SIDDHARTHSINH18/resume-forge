@echo off
rem Start the MeritOS backend API on http://127.0.0.1:8421 (serves frontend/dist when built).
rem Override the port with BACKEND_PORT if ever needed (must match the frontend proxy).
cd /d "%~dp0..\backend"
if "%BACKEND_PORT%"=="" set BACKEND_PORT=8421

rem Project stability preflight: verify repository identity and that the port is
rem free. Never terminates any process — on conflict, startup stops here.
.venv\Scripts\python.exe -m app.identity
if errorlevel 1 (
  echo MeritOS startup stopped. Resolve the issue above; no process was terminated.
  exit /b 1
)

.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT%
