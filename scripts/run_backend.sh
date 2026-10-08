#!/usr/bin/env bash
# Start the MeritOS backend API on http://127.0.0.1:8421 (Git Bash / macOS / Linux).
# Override the port with BACKEND_PORT if ever needed (must match the frontend proxy).
set -e
cd "$(dirname "$0")/../backend"
PORT="${BACKEND_PORT:-8421}"

# Project stability preflight: verify repository identity and that the port is
# free. Never terminates any process — on conflict, startup stops here.
if [ -x ".venv/Scripts/python.exe" ]; then
  PY=./.venv/Scripts/python.exe
else
  PY=./.venv/bin/python
fi
"$PY" -m app.identity

"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
