#!/usr/bin/env bash
# PostToolUse hook (Edit|Write on *.py): format the changed file with Ruff.
# Fails OPEN: if the toolchain is not installed yet (pre-Phase-1), silently no-op.
set -euo pipefail

payload="$(cat)"
file="$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null || true)"

[ -z "$file" ] && exit 0
[[ "$file" == *.py ]] || exit 0
[ -f "$file" ] || exit 0

run_ruff() {
  if command -v ruff >/dev/null 2>&1; then ruff "$@"
  elif command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ]; then uv run ruff "$@" 2>/dev/null
  else return 0
  fi
}

run_ruff format "$file" >/dev/null 2>&1 || true
run_ruff check --fix --exit-zero "$file" >/dev/null 2>&1 || true
exit 0
