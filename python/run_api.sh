#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${LINGOVIEW_LOG_DIR:-$HOME/Library/Application Support/LingoView}"
LOG_FILE="$LOG_DIR/api.log"

mkdir -p "$LOG_DIR"

export PYTHONPATH="$ROOT:${PYTHONPATH:-}"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  if [[ -f "$ROOT/.venv/bin/activate" ]]; then
    source "$ROOT/.venv/bin/activate"
  else
    echo "Virtualenv not found at $ROOT/.venv. Run 'python -m venv .venv' first." >&2
    exit 1
  fi
fi

echo "API logs will be written to: $LOG_FILE"
uvicorn lingoview_service.api:app --host 0.0.0.0 --port 8000 --reload 2>&1 | tee "$LOG_FILE"
