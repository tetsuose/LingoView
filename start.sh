#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_SCRIPT="$ROOT/python/run_api.sh"
WEB_DIR="$ROOT/web"

if [[ ! -f "$API_SCRIPT" ]];
then
  echo "Missing $API_SCRIPT. Did you clone the repo correctly?" >&2
  exit 1
fi

cd "$ROOT/python"

if [[ -f ".venv/bin/activate" ]]; then
  VENV_DIR=".venv"
elif [[ -f ".venv/bin/activate" ]]; then
  VENV_DIR=".venv"
else
  echo "Virtualenv not found at $ROOT/python/$VENV_DIR. Please run 'python3 -m venv $VENV_DIR' and install dependencies." >&2
  exit 1
fi

echo "Activating Python environment: $VENV_DIR"
source "$VENV_DIR/bin/activate"

cd "$ROOT"

echo "Starting FastAPI backend..."
"$API_SCRIPT" &
API_PID=$!

cleanup() {
  if [[ "${CLEANUP_DONE:-0}" -eq 1 ]]; then
    return
  fi
  CLEANUP_DONE=1
  echo "\nStopping services..."

  if [[ -n "${WEB_PID:-}" ]]; then
    if kill -0 "$WEB_PID" >/dev/null 2>&1; then
      kill -INT "$WEB_PID" >/dev/null 2>&1 || kill "$WEB_PID" >/dev/null 2>&1 || true
      wait "$WEB_PID" >/dev/null 2>&1 || true
    fi
    unset WEB_PID
  fi

  if [[ -n "${API_PID:-}" ]]; then
    if kill -0 "$API_PID" >/dev/null 2>&1; then
      kill -INT "$API_PID" >/dev/null 2>&1 || kill "$API_PID" >/dev/null 2>&1 || true
      wait "$API_PID" >/dev/null 2>&1 || true
    fi
    unset API_PID
  fi
}

trap cleanup EXIT
trap 'trap - EXIT; cleanup; exit 0' INT TERM

cd "$WEB_DIR"
pnpm install --filter web >/dev/null 2>&1 || true

echo "Starting web dev server..."
VITE_BIN="$WEB_DIR/node_modules/.bin/vite"
if [[ ! -x "$VITE_BIN" ]]; then
  echo "vite executable not found at $VITE_BIN" >&2
  exit 1
fi
"$VITE_BIN" dev --clearScreen false &
WEB_PID=$!

wait "$API_PID" "$WEB_PID"
