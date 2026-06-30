#!/usr/bin/env bash
# Start the API and web app with readiness checks.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_HOST="127.0.0.1"
API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-5173}"
API_URL="http://${API_HOST}:${API_PORT}"
UI_URL="http://${API_HOST}:${UI_PORT}"

cd "$ROOT_DIR"

cleanup() {
  if [ -n "${API_PID:-}" ]; then
    kill "$API_PID" 2>/dev/null || true
  fi
  if [ -n "${UI_PID:-}" ]; then
    kill "$UI_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

require_free_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -tiTCP:"${port}" -sTCP:LISTEN || true)"
    if [ -n "$pids" ]; then
      echo "Port ${port} is already in use. Set API_PORT or UI_PORT to another port." >&2
      return 1
    fi
  fi
}

wait_for_url() {
  local url="$1"
  local label="$2"
  for _attempt in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "${label} ready: ${url}"
      return 0
    fi
    sleep 0.5
  done
  echo "${label} did not become ready: ${url}" >&2
  return 1
}

if [ ! -d ".venv" ]; then
  echo "Installing Python dependencies"
  if command -v uv >/dev/null 2>&1; then
    uv sync --frozen --extra dev
  else
    python3.11 -m venv .venv
    .venv/bin/pip install -e ".[dev]"
  fi
fi

if [ ! -x ".venv/bin/uvicorn" ]; then
  echo "Installing Python dependencies"
  if command -v uv >/dev/null 2>&1; then
    uv sync --frozen --extra dev
  else
    .venv/bin/pip install -e ".[dev]"
  fi
fi

if [ ! -d "frontend/node_modules" ]; then
  echo "Installing frontend dependencies"
  npm --prefix frontend ci
fi

require_free_port "$API_PORT"
require_free_port "$UI_PORT"

echo "Starting API on ${API_URL}"
.venv/bin/python -m uvicorn arenawealth.api.main:app --host "$API_HOST" --port "$API_PORT" \
  > /tmp/actionaudit-api.log 2>&1 &
API_PID="$!"

wait_for_url "${API_URL}/api/v1/health" "API"

echo "Starting UI on ${UI_URL}"
VITE_API_PROXY_TARGET="${VITE_API_PROXY_TARGET:-$API_URL}" \
  npm --prefix frontend run dev -- --host "$API_HOST" --port "$UI_PORT" \
  > /tmp/actionaudit-ui.log 2>&1 &
UI_PID="$!"

wait_for_url "$UI_URL" "UI"

cat <<EOF

ActionAudit is running.
  App:      ${UI_URL}
  API:      ${API_URL}
  API docs: ${API_URL}/docs

Logs:
  API: /tmp/actionaudit-api.log
  UI:  /tmp/actionaudit-ui.log

Press Ctrl+C to stop.
EOF

wait
