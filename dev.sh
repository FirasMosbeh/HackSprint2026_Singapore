#!/usr/bin/env bash
# Start Sentrya: the agent API (agent/ + testing/) and the web app (app/).
#
#   ./dev.sh
#
# App:   http://localhost:5173
# Agent: http://127.0.0.1:8000  (docs at /docs)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VENV="$ROOT/.venv"

if [ ! -d "$VENV" ]; then
  echo "==> creating virtualenv"
  "$PYTHON" -m venv "$VENV"
fi

echo "==> installing agent dependencies"
"$VENV/bin/pip" install -q --disable-pip-version-check -r requirements.txt

if [ ! -d "$ROOT/app/node_modules" ]; then
  echo "==> installing app dependencies"
  (cd "$ROOT/app" && npm install)
fi

cleanup() {
  echo
  echo "==> shutting down"
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> starting agent on http://127.0.0.1:8000"
PYTHONPATH="$ROOT" "$VENV/bin/python" -m uvicorn agent.server:app \
  --host 127.0.0.1 --port 8000 &

echo "==> starting app on http://localhost:5173"
(cd "$ROOT/app" && npm run dev) &

wait
