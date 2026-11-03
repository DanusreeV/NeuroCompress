#!/usr/bin/env bash
# Ubuntu / Linux / macOS: set up everything on first run, then start backend + frontend together.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || cp .env.example .env
set -a; . ./.env; set +a

PY="${PYTHON:-python3}"
if [ ! -d .venv ]; then echo ">> creating virtual environment (.venv)"; "$PY" -m venv .venv; fi
# shellcheck disable=SC1091
. .venv/bin/activate
if [ ! -f .venv/.deps-installed ] || [ requirements.txt -nt .venv/.deps-installed ]; then
  echo ">> installing Python dependencies"; python -m pip install --upgrade pip -q; pip install -r requirements.txt; touch .venv/.deps-installed
fi
if [ ! -d frontend/node_modules ]; then echo ">> installing frontend packages"; (cd frontend && npm install); fi

BACKEND_PORT="$(python scripts/find_port.py "${BACKEND_PORT:-8000}")"
FRONTEND_PORT="$(python scripts/find_port.py "${VITE_PORT:-5173}")"
export VITE_API_PROXY_TARGET="http://127.0.0.1:${BACKEND_PORT}" VITE_PORT="${FRONTEND_PORT}"

echo ">> starting backend on :${BACKEND_PORT}"
(cd backend && exec python -m uvicorn app.main:app --host 127.0.0.1 --port "${BACKEND_PORT}") &
BPID=$!
trap 'kill $BPID 2>/dev/null || true' EXIT INT TERM

for _ in $(seq 1 60); do
  python - "$BACKEND_PORT" <<'PY' && break || sleep 0.5
import sys, urllib.request
urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/api/health", timeout=1)
PY
done
echo ">> backend ready: http://127.0.0.1:${BACKEND_PORT}/docs"
echo ">> starting frontend: open http://localhost:${FRONTEND_PORT}"
cd frontend && npm run dev
