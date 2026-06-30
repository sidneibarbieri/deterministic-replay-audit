#!/usr/bin/env bash
# Local verification for the Python package and browser app.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
  if [[ ! -x "$ROOT/.venv/bin/pytest" || ! -x "$ROOT/.venv/bin/ruff" ]]; then
    echo "The local .venv exists but dev dependencies are missing." >&2
    echo "Run: make setup" >&2
    exit 1
  fi
  PY="$ROOT/.venv/bin/pytest"
elif command -v pytest >/dev/null 2>&1; then
  PY="pytest"
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON="python3.11"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
  else
    echo "Install Python 3.11 or activate .venv before running verification." >&2
    exit 1
  fi
else
  echo "Install dependencies: python -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi

"$PYTHON" -m ruff check .
"$PY" tests/ -q

cd "$ROOT/frontend"
npm run build
npm run lint

echo "OK: pytest + frontend build + eslint"
