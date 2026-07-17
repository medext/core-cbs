#!/usr/bin/env bash
# PreToolUse hook (Bash tool): block destructive database/infra commands.
# Input: hook JSON on stdin. Output: exit 2 + stderr message to block; exit 0 to allow.
set -euo pipefail

payload="$(cat)"
cmd="$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || true)"

[ -z "$cmd" ] && exit 0

block() {
  echo "BLOCKED by guard-destructive hook: $1" >&2
  echo "This command is destructive. If genuinely required, the user must run or explicitly approve it." >&2
  exit 2
}

shopt -s nocasematch

# Database destruction
[[ "$cmd" =~ drop[[:space:]]+(database|schema|table) ]] && block "SQL DROP detected"
[[ "$cmd" =~ truncate[[:space:]] ]] && block "SQL TRUNCATE detected"
[[ "$cmd" =~ manage\.py[[:space:]]+(flush|reset_db|sqlflush) ]] && block "Django flush/reset detected"
[[ "$cmd" =~ migrate[[:space:]].*--fake ]] && block "migrate --fake detected"
[[ "$cmd" =~ dropdb ]] && block "dropdb detected"

# Infra mutations that could hit shared/prod environments
[[ "$cmd" =~ kubectl[[:space:]]+(delete|drain|cordon) ]] && block "kubectl destructive verb"
[[ "$cmd" =~ helm[[:space:]]+(uninstall|rollback|delete) ]] && block "helm destructive verb"
[[ "$cmd" =~ docker[[:space:]]+(system[[:space:]]+prune|volume[[:space:]]+rm) ]] && block "docker prune/volume rm"

# Filesystem
[[ "$cmd" =~ rm[[:space:]]+-[a-z]*r[a-z]*f ]] && [[ ! "$cmd" =~ (node_modules|__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|/tmp/|scratchpad) ]] \
  && block "recursive force delete outside known-safe paths"

# Git history destruction
[[ "$cmd" =~ git[[:space:]]+push[[:space:]].*--force([[:space:]]|$) ]] && [[ ! "$cmd" =~ --force-with-lease ]] && block "git push --force (use --force-with-lease only with approval)"

exit 0
