#!/usr/bin/env bash
# Start the Resume-Forge backend API on http://127.0.0.1:8421 (Git Bash / macOS / Linux).
# Override the port with BACKEND_PORT if ever needed (must match the frontend proxy).
set -e
cd "$(dirname "$0")/../backend"
PORT="${BACKEND_PORT:-8421}"
if [ -x ".venv/Scripts/python.exe" ]; then
  ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
else
  ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
fi
