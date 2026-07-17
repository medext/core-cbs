#!/usr/bin/env bash
# PostToolUse hook (Edit|Write on src/**/*.py): lint + typecheck the touched file and surface
# findings to the agent. Fails OPEN pre-Phase-1 (missing toolchain => no-op).
set -euo pipefail

payload="$(cat)"
file="$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null || true)"

[ -z "$file" ] && exit 0
[[ "$file" == *src/*.py || "$file" == *tests/*.py ]] || exit 0
[ -f "$file" ] || exit 0
[ -f pyproject.toml ] || exit 0

out=""
if command -v uv >/dev/null 2>&1; then
  out+="$(uv run ruff check "$file" 2>/dev/null || true)"
  out+=$'\n'
  out+="$(uv run mypy --no-error-summary "$file" 2>/dev/null || true)"
elif command -v ruff >/dev/null 2>&1; then
  out+="$(ruff check "$file" 2>/dev/null || true)"
fi

# Trim whitespace-only output
if [ -n "${out//[$'\n\t ']/}" ]; then
  echo "lint-changed hook findings for ${file}:" >&2
  echo "$out" >&2
  exit 2   # exit 2 feeds findings back to the agent for correction
fi
exit 0
