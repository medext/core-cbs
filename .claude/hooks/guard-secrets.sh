#!/usr/bin/env bash
# PreToolUse hook (Bash tool): block `git commit` / `git add` when staged or added content
# matches secret patterns. Exit 2 blocks; exit 0 allows.
set -euo pipefail

payload="$(cat)"
cmd="$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || true)"

# Only inspect git commit/add commands
[[ "$cmd" =~ git[[:space:]]+(commit|add) ]] || exit 0

# Patterns for common secrets (kept deliberately broad; guards fail closed)
PATTERNS='-----BEGIN (RSA|EC|OPENSSH|PGP|DSA) PRIVATE KEY-----|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|glpat-[A-Za-z0-9_-]{20}|sk-[A-Za-z0-9]{20,}|sk_live_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|eyJhbGciOi[A-Za-z0-9_-]+\.eyJ|AIza[0-9A-Za-z_-]{35}|(password|passwd|secret|api_key|apikey|client_secret)[[:space:]]*[=:][[:space:]]*["'"'"'][^"'"'"']{8,}'

staged="$(git diff --cached --no-color 2>/dev/null || true)"
if [ -n "$staged" ] && printf '%s' "$staged" | grep -Eiq "$PATTERNS"; then
  echo "BLOCKED by guard-secrets hook: staged changes match a secret pattern." >&2
  echo "Remove the secret (and rotate it if real) before committing. Use *.example templates for config." >&2
  exit 2
fi

# For `git add`, also scan the files being added
if [[ "$cmd" =~ git[[:space:]]+add ]]; then
  files="$(printf '%s' "$cmd" | sed -E 's/.*git[[:space:]]+add[[:space:]]+//' | tr ' ' '\n' | grep -v '^-' || true)"
  for f in $files; do
    [ -f "$f" ] || continue
    if grep -Eiq "$PATTERNS" "$f" 2>/dev/null; then
      echo "BLOCKED by guard-secrets hook: $f matches a secret pattern." >&2
      exit 2
    fi
  done
fi

exit 0
