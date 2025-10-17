#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_LOG_DIR="$HOME/Library/Application Support/LingoView"
LOG_DIR="${LINGOVIEW_LOG_DIR:-$DEFAULT_LOG_DIR}"
LOG_FILE="$LOG_DIR/streamlit.log"

mkdir -p "$LOG_DIR"

export PYTHONPATH="$ROOT:${PYTHONPATH:-}"

# Activate virtualenv if not already active.
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  if [[ -f "$ROOT/.venv/bin/activate" ]]; then
    source "$ROOT/.venv/bin/activate"
  else
    echo "Virtualenv not found at $ROOT/.venv. Please run 'python -m venv .venv' first." >&2
    exit 1
  fi
fi

echo "Streamlit logs will be written to: $LOG_FILE"
streamlit run "$ROOT/lingoview_service/webui.py" "$@" 2>&1 | tee "$LOG_FILE"
