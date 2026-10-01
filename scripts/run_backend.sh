#!/usr/bin/env bash
# Start the backend API on http://127.0.0.1:8100 (Git Bash / macOS / Linux).
set -e
cd "$(dirname "$0")/../backend"
if [ -x ".venv/Scripts/python.exe" ]; then
  ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100
else
  ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
fi
