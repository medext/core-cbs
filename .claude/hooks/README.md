# Claude Code Hooks — Next Core

Hooks are wired in [`.claude/settings.json`](../settings.json) and implemented as scripts in
this directory. They are written defensively: guard hooks are active immediately; quality
hooks **no-op gracefully until the Phase 1 toolchain (uv/Ruff/mypy/pytest) exists**, then
activate automatically.

| Hook | Event | Script | Behavior |
|---|---|---|---|
| Destructive-command guard | `PreToolUse` (Bash) | `guard-destructive.sh` | Blocks destructive DB/infra commands (`DROP DATABASE`, `reset_db`, `migrate --fake`, `flush`, prod-looking `kubectl`/`helm` mutations, `rm -rf` outside safe paths) unless the user has explicitly approved in the session. Active now. |
| Secret guard | `PreToolUse` (Bash `git commit`/`git add`) | `guard-secrets.sh` | Scans staged changes for secret patterns (private keys, AWS/GCP creds, tokens, passwords in config) and blocks the commit. Active now. |
| Released-migration guard | `PreToolUse` (Edit/Write on `**/migrations/*.py`) | `guard-migrations.sh` | Blocks edits to migration files already committed on the default branch (released migrations are frozen). Active from Phase 1. |
| Auto-format | `PostToolUse` (Edit/Write on `*.py`) | `format-changed.sh` | Runs Ruff format + fix on the changed file. No-ops until Ruff is installed. |
| Targeted lint+types | `PostToolUse` (Edit/Write on `src/**/*.py`) | `lint-changed.sh` | Ruff check + mypy on the touched module; reports findings back. No-ops until toolchain exists. |

## Principles

- Hooks never auto-run destructive or production commands; they only **block** or **format/lint**.
- Hooks fail *closed* for guards (block on doubt) and fail *open* for quality tooling
  (missing tool ⇒ skip, never break the session).
- Do not weaken a guard hook to make a task easier — escalate to the user instead.
