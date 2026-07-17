#!/usr/bin/env bash
# PreToolUse hook (Edit|Write): block modification of migration files that already exist on
# the default branch (released migrations are frozen). Exit 2 blocks; exit 0 allows.
set -euo pipefail

payload="$(cat)"
file="$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null || true)"

[ -z "$file" ] && exit 0
[[ "$file" == */migrations/*.py ]] || exit 0
[[ "$file" == */migrations/__init__.py ]] && exit 0

# Determine default branch (origin/HEAD), fall back to main
default_ref="$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/@@' || echo 'origin/main')"

rel="$(git -C "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" ls-files --full-name -- "$file" 2>/dev/null || true)"
[ -z "$rel" ] && rel="${file#"$(git rev-parse --show-toplevel 2>/dev/null || echo)/"}"

if git cat-file -e "${default_ref}:${rel}" 2>/dev/null; then
  echo "BLOCKED by guard-migrations hook: ${rel} exists on ${default_ref} and is frozen." >&2
  echo "Released migrations must never be edited. Create a NEW migration instead (see .claude/rules/migrations.md)." >&2
  exit 2
fi

exit 0
