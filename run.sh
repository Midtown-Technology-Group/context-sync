#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TARGET_DATE="${1:-today}"
shift || true

ensure_python() {
  if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
  else
    PYTHON_BIN="$(command -v python3)"
  fi
}

run_sync() {
  if [[ $# -gt 0 ]]; then
    PYTHONPATH=src "$PYTHON_BIN" -u -m work_context_sync.app sync "$TARGET_DATE" --config config.json --sources "$@"
  else
    PYTHONPATH=src "$PYTHON_BIN" -u -m work_context_sync.app sync "$TARGET_DATE" --config config.json
  fi
}

ensure_python

case "$TARGET_DATE" in
  teams)
    TARGET_DATE="today"
    run_sync teams_meetings teams_chats
    ;;
  core)
    TARGET_DATE="today"
    run_sync calendar mail todo
    ;;
  all)
    TARGET_DATE="today"
    run_sync
    ;;
  help|-h|--help)
    cat <<'EOF'
Usage:
  ./run.sh                    # sync today, all default sources
  ./run.sh today              # sync today
  ./run.sh 2026-04-10         # sync a specific day
  ./run.sh teams             # sync today's Teams meetings + chats only
  ./run.sh core              # sync today's calendar + mail + todo only
  ./run.sh all               # sync today, all default sources
  ./run.sh today teams_meetings teams_chats

Examples:
  ./run.sh
  ./run.sh teams
  ./run.sh 2026-04-10 calendar mail todo
EOF
    ;;
  *)
    run_sync "$@"
    ;;
esac
