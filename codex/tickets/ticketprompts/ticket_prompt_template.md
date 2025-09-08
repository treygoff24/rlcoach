# Execution Prompt — Ticket {{NNN}}: {{Short Title}}

You are a coding agent working in a modern agentic environment (e.g., Codex CLI). Run a plan–execute–verify loop, use tools to inspect and modify files (don’t guess), and continue until every acceptance check passes. Favor deterministic behavior, structured outputs, explicit errors, and small, focused diffs.

## Critical Rules (repeat)
- Persist: plan, implement, validate, iterate until done.
- Read first: inspect files before changing; never assume contents.
- Tools: use planning, shell/FS inspection, and patch/diff tools; keep preambles concise before grouped actions.
- Determinism: stable paths/names, atomic writes, schema validation, fixed seeds where relevant.
- Safety: no secrets in code/logs; avoid network unless the ticket explicitly allows it; follow least-privilege and seek clarification on ambiguity.
- Style: follow project conventions (formatting, lints, tests, type hints if applicable); prefer absolute imports; keep changes minimal and scoped.
- Observability: emit clear, actionable logs and errors; document key commands and results in the ticket log.

> Tip: Repeat the Critical Rules at the bottom of long tickets to reinforce behavior in long contexts.

## Environment & Tools
- Agent context: {{your agent runtime, e.g., Codex CLI}}.
- Available tools: {{planning tool}}, {{shell/exec tool}}, {{file patch/diff tool}}, {{formatter/linter}}, {{test runner}}.
- Approvals: {{never|on-request|on-failure}}; Network: {{enabled|restricted|disabled}}; Filesystem: {{read-only|workspace-write|full}}.
- When using tools:
  - Group related actions and write a brief preamble (1–2 short sentences).
  - Prefer fast file/text search (e.g., `rg`) when available; otherwise use standard OS tools.
  - Read files in chunks to avoid verbosity; don’t dump large files unless necessary.

## Branching
- Base: {{branch to base from, e.g., main or prior ticket branch}}.
- Create: `{{feat/gpt5-NNN-short-slug}}`.
- Commit discipline: small, focused commits with imperative summaries; include brief validation evidence when helpful.

## Goal
- {{One-paragraph description of the outcome and why it matters. Keep it specific and testable.}}

## Scope
- {{In-scope bullets describing what will be implemented/changed.}}

## Out of Scope
- {{Explicit bullets of what will NOT be changed in this ticket.}}

## Primary Files to Modify or Add
- {{path/to/file_or_module}} — {{short purpose/role}}
- {{path/to/another_file}} — {{short purpose/role}}
- (Optional new) {{path/to/new_file}} — {{short purpose/role}}

## Data Models, Schemas, or Interfaces (if applicable)
- Versioning: include `schema_version` in artifacts/configs and validate on save.
- Atomicity: write to a temp file, then swap (e.g., `os.replace`) to guarantee valid-on-disk state.
- Idempotency: design “done predicates” based on artifacts (existence, counts, checksums, timestamps).

## CLI Flags / APIs (if applicable)
- {{flag or endpoint}}: {{purpose and usage}}
- {{flag or endpoint}}: {{purpose and usage}}

## Implementation Plan
1) Inspect the current code paths and related docs to confirm scope and dependencies.
2) Draft minimal helpers (e.g., atomic write, schema read/validate) if needed; keep them local and simple.
3) Implement core changes with a bias for determinism and clear logging.
4) Wire any CLI flags/APIs and ensure helpful, explicit error messages.
5) Add/update tests and smoke checks (fast, deterministic, no network unless allowed).
6) Update docs (README/guides) and any manifests/metadata.
7) Run validations; iterate on failures; keep diffs tight.

## Acceptance Checks (must pass)
- Behavior: {{Describe the observable behavior or outputs required.}}
- Artifacts: {{List required files (with schema_version) and their invariants (counts, checksums, sizes).}}
- Commands: {{List exact commands to run}} (e.g., `{{make smoke}}`, `{{pytest -q}}`, `{{python -m scripts.run_all ...}}`).
- Idempotency: Re-running with the same inputs performs no redundant work; missing/partial outputs trigger precise repair.
- Errors: Invalid inputs or states produce explicit, actionable messages.

## Validation Steps
- Lint/Format: `{{project linter/formatter command}}`.
- Unit/Integration tests: `{{test runner command}}`.
- Smoke/Preview: `{{smoke command}}` (dry-run if available; keep seeds fixed).
- Optional: Compare runs or artifacts for determinism (hashes/counts/timestamps where applicable).

## Deliverables
- Branch: `{{feat/gpt5-NNN-short-slug}}`
- Files changed/added: {{list key files}}
- Artifacts: {{list generated, versioned artifacts if relevant}}
- Log: `{{./codex/logs/NNN.md}}` (or project log path) with Action Plan, What I Did, Commands, Results, Next Steps.

## Commit & PR Guidance
- Commits: small, scoped, imperative (“Add schema v2 writer”, “Guard invalid flags”).
- PR description: what changed and why; link ticket; include acceptance evidence (commands run, outputs, paths to artifacts).
- Do not include large artifacts or secrets; reference paths instead.

## Safety & Compliance
- Secrets: never commit; prefer `.env` or secret managers. Validate loads at runtime; fail fast on missing required vars.
- Network: disabled unless explicitly required; if enabled, log what is fetched and why.
- Destructive actions: do not run unless the ticket explicitly authorizes them and they are reversible. Provide dry-run where possible.

## Observability & Logging
- Logs: concise, explicit, and user-actionable. Include reasons for skip/repair/re-run decisions.
- Tracing/metrics (if available): add spans/metrics around critical phases.

## Final Output (optional JSON summary)
Print as the last line only if your environment expects it.
```
{
  "ticket": "{{NNN}}",
  "branch": "{{feat/gpt5-NNN-short-slug}}",
  "status": "<success|needs-attention>",
  "changed_files": ["<paths>"],
  "tests": {"runner":"{{name}}","result":"<pass|fail>"},
  "notes": "<1–2 line summary or blocker>"
}
```

---

## Authoring Guidance (for the person writing this ticket)

Use the following patterns (adapt as needed) to produce a high-signal execution prompt that the agent can follow reliably across any project.

### Tone & Structure
- Be explicit and literal; avoid vague directives. State goals, constraints, acceptance, and exact output formats.
- Show, don’t tell: include small, concrete examples (commands, file paths, sample schema) where ambiguity is likely.
- Keep sections short and scannable with clear headers and 1-line bullets.

### Agentic Best Practices
- Start with Critical Rules; repeat at bottom for long tickets.
- Encourage plan–execute–verify loops and preamble messages before grouped tool calls.
- Prefer structured outputs (versioned JSON/CSV) over free text when artifacts are needed.
- Specify tool boundaries and when to use (or not use) each tool; include examples for tricky argument construction.
- Gate high-impact actions (user confirmation, least privilege, argument validation); ask clarifying questions when inputs are ambiguous.

### Determinism & Idempotency
- Stabilize file paths and names; specify atomic writes and versioned schemas.
- Define explicit done-predicates (existence, counts, checksums, timestamps) for resume/idempotent behavior.
- For any randomness (sampling/tests), fix seeds and document them.

### Safety
- Default to no network, no secrets, and non-destructive operations. If needed, call them out explicitly with conditions and safeguards.
- Provide clear rollback/repair paths when modifying stateful or persistent artifacts.

### Validation & Evidence
- Include exact commands for lints/tests/smoke so the agent can run them verbatim.
- Ask for concise logs and, if useful, a final JSON summary for automation.

---

## Minimal Example (adapt the placeholders)

Title: Execution Prompt — Ticket 012: Add schema v2 and idempotent parse

Critical Rules (repeat)
- Persist until done; use plan–execute–verify.
- Read before changing; no guessing; explicit errors.
- Determinism: stable names, atomic writes, schema validation.
- Safety: no network/secrets; small, scoped diffs.

Goal
- Upgrade parse outputs to schema_version=2 and add idempotent checks so re-runs skip when artifacts are valid.

Primary Files
- `scripts/parse_results.py` — write `predictions.csv` and `results/trial_manifest.json` (v2).
- `scoring/score_predictions.py` — ensure deterministic `per_item_scores.csv`.

Implementation Plan
1) Add a small helper for schema v2 read/validate/write with atomic swap.
2) Update parse to produce `predictions.csv` deterministically and set manifest `stage_status.parsed` with row counts.
3) Add idempotent predicate for parsed stage and skip on re-run when valid.
4) Write clear logs for skip/repair decisions.

Acceptance Checks
- `predictions.csv` exists and rows match unique IDs; manifest `schema_version==2`.
- Re-run with same inputs performs no work; deleting `predictions.csv` triggers repair only for that step.
- Tests pass locally; explicit errors on invalid inputs.

Validation Steps
- `{{test runner command}}` and `{{smoke command}}` (dry-run if available).

Deliverables
- Branch: `feat/gpt5-012-schema-v2-parse`
- Files: `scripts/parse_results.py`, `results/trial_manifest.json` (v2), updated tests.
- Log: `./codex/logs/012.md` with plan, actions, commands, results.

---

Critical Rules (repeat): Persist; read first; use tools; determinism; safety; style; observability.

