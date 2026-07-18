# Development Workflow — Building Next Core with Claude Code

| | |
|---|---|
| **Purpose** | The operating manual for developing this project with Claude Code: session organization, the mandatory working loop, review gates, branch conventions, and context management. |
| **Audience** | The human product owner and every Claude Code session working on this repo. |
| **Owning phase** | Phase 0 (living). |
| **Related** | `CLAUDE.md` (repo root) · [Roadmap](roadmap.md) · `.claude/` configuration |

---

## 1. Operating model

Development is **phase-gated and slice-driven**:

- The **roadmap** defines phases; only the current phase is worked on.
- Within a phase, work is decomposed into **vertical slices** — the smallest change that
  delivers verifiable value across domain + persistence + API + tests + docs.
- Every slice runs through the **19-step loop** (§3) via the `/vertical-slice` command.
- Every phase ends with `/phase-gate`, producing a gate report that a **human must approve**
  before the next phase starts. The agent never self-approves a gate.

The human's role: approve gates and ADRs, resolve open decisions, arbitrate reviewer
conflicts, and explicitly authorize anything destructive or irreversible. Everything else is
the agent's responsibility, within the rules.

## 2. Session organization

### One session = one slice (default)

Start each Claude Code session with a scoped objective, e.g.:

```
/vertical-slice Phase 3 — implement the Posting model and the balanced-entry DB constraint
```

Why: bounded context-window usage, clean change reports, reviewable diffs, and a natural
commit/PR boundary. Avoid marathon sessions mixing unrelated slices.

### Session start ritual (any session)

0. Read **`STATUS.md`** (repo root) — the session-handoff document: current state, slice
   backlog, exact next step, environment notes. This makes any fresh session resumable from
   the repository alone.
1. Read `docs/product/roadmap.md` → current phase + remaining gate items.
2. Read the phase's relevant docs and `.claude/rules/` for paths you will touch.
3. Check `docs/decisions/open-decisions.md` for anything blocking your slice.
4. State the slice objective and proceed with the loop.

### Session end ritual

- **Update `STATUS.md` in the same commit** (backlog statuses, last-updated date, handoff
  notes) — the next session must be able to continue without this conversation.
- Change report (loop step 17), updated docs, updated open-decisions register.
- Commit(s) pushed to the working branch; gate checklist updated if applicable.
- If the slice ends at a stop-point (gate, ADR approval, destructive action): STOP and ask.

### Long-running phases

Track slice backlog for the phase either as GitHub issues (one per slice, labeled `phase-N`)
or the task list at the top of the phase in the roadmap. Each session picks exactly one.

## 3. The mandatory 19-step loop (summary)

Canonical version: `.claude/commands/vertical-slice.md` at the repository root.

Inspect → Restate objective → Identify contexts → List assumptions → Smallest safe slice →
Financial/security risks → Acceptance criteria → **Tests first** → File-level plan →
Implement in small changes → Targeted tests per change → Full quality gate → Migration
review → Authz & tenancy review → Invariants review → **Docs in same change** → Change
report → Debt list → Stop at gates.

Hard rules: never report success without executed commands and inspected output; never hide
failing tests, type errors, migration risks, or concurrency uncertainty; a violated invariant
stops the work.

## 4. Subagent review matrix

Reviews are **mandatory**, not optional, per this matrix:

| Change touches… | Required subagents |
|---|---|
| Ledger, postings, balances, money, fees, interest, reconciliation | `ledger-accounting-reviewer` + `postgres-concurrency-reviewer` |
| Any concurrent financial write path, locks, outbox, EoD jobs | `postgres-concurrency-reviewer` |
| Auth, tenancy, serializers, webhooks, logging, crypto, URLs/files | `security-reviewer` |
| New models, context boundaries, dependencies, module structure | `core-banking-architect` |
| Test design for financial slices / auditing suspicious green suites | `test-engineer` |
| Phase gates, large features, doc-heavy changes | `documentation-reviewer` |

Conflict rule: subagents advise; the **primary session reconciles** contradictions into one
coherent decision — but a BLOCKER from ledger/concurrency/security reviewers can only be
overridden by the human, never by the primary agent.

## 5. Git & GitHub conventions

- **Branches:** `phase-N/<slice-slug>` (e.g. `phase-3/posting-service-lock-ordering`).
  Default branch is protected; nothing merges without the loop's evidence.
- **Commits:** conventional style (`feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`),
  imperative, scoped to coherent change; docs updated in the same commit as behavior.
- **PRs:** one per slice. Body = change report from loop step 17: objective, contexts touched,
  evidence (commands + results), reviewer verdicts, docs updated, debt. CI must be green.
- **Releases/migrations:** released migrations frozen (hook-enforced); expand-and-contract
  for schema changes.

## 6. Context management for Claude Code

- `CLAUDE.md` stays **small and durable** — commands, boundaries, invariants summary,
  prohibitions. Details live in `.claude/rules/<area>.md`; read the relevant rule before
  touching that area, not all of them always.
- Long design context lives in `docs/` — sessions read the specific doc they need
  (glossary, lifecycle, invariants) instead of re-deriving decisions. **ADRs are memory**:
  if a session finds itself re-arguing a settled decision, it reads the ADR and moves on;
  changing direction = new superseding ADR + human approval.
- Use subagents for wide research (they burn their own context, return conclusions).
- When a session approaches context limits mid-slice: write the change report and remaining
  steps into the PR/issue, then continue in a fresh session from that record.

## 7. Stop-points requiring the human

The agent must stop and ask before:
1. Passing any phase gate (approval recorded in roadmap).
2. Accepting an ADR (status Proposed → Accepted) or superseding one.
3. Any destructive/irreversible action (data deletion, force-push, dropping constraints,
   weakening a guard hook) — also enforced by hooks.
4. Resolving an open decision that the register marks as human-owned.
5. Any change that would violate or weaken an accounting invariant (this should never be
   needed; escalation, not implementation).
6. Publishing anything externally (packages, images, docs sites).

## 8. Quality gates & CI

Current pipeline (`.github/workflows/ci.yml`, since Phase 1): Ruff lint+format, mypy strict,
pytest on real PostgreSQL 16 + Redis 7 services with coverage, migration check
(`makemigrations --check`), strict MkDocs build, security scans (Bandit, pip-audit, gitleaks
full-history), and a compose runtime smoke job (build image, start stack, assert health).
`make check` reproduces the quality gates locally — run it before every PR.

Planned additions land with their owning phases: property suites join the tests job in
Phase 3; concurrency and e2e suites run on ledger-touching PRs and in a nightly workflow
from Phase 3; performance jobs in Phase 9.

## 9. Definition of Done (per slice)

Domain behavior + authorization + tenant isolation + DB constraints where appropriate +
unit/property/integration/concurrency tests as relevant + API contract documented + audit
evidence + observability + failure behavior documented + security & accounting review clean +
docs updated + no known invariant violation. (Master prompt §22 — binding.)
