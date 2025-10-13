
# Writing Excellent Tickets for **GPT‑5 Codex** (Evidence‑Based, Best‑Practices Guide)
*Version: 2025‑09‑22*

This guide distills what works in practice when you want GPT‑5 Codex (CLI/IDE/Cloud) or the GPT‑5 API to **design, implement, and land PR‑quality code** from a ticket/spec. It integrates OpenAI’s official guidance on prompting, tool use, structured outputs, reproducibility, and agentic workflows, plus field‑tested heuristics for running AI in real engineering orgs.

---

## 0) What “excellent” tickets do
An excellent ticket for GPT‑5 Codex is **specific enough to be unambiguous** but **narrow enough to be tractable in one PR**. It does four things:

1. **Pinpoints scope** — exact files, symbols, or endpoints; what *not* to touch; constraints and non‑goals.  
2. **Defines success** — runnable verification steps, acceptance tests, and exit criteria.  
3. **Supplies context** — repo coordinates, stack/version/constraints, style conventions, and links to relevant code.  
4. **Specifies output form** — *diff vs. whole‑file*, PR title/body template, and what to emit besides code (e.g., decision log).

OpenAI’s Codex docs emphasize **clear code pointers, verification steps, and splitting work**; treat your ticket as the control surface for those behaviors.

---

## 1) Ticket blueprint (copy/paste)

Use this as your default issue template. Keep it short but complete. Replace 🔷 with your values.

```yaml
title: "[🔷project] 🔷concise, outcome‑oriented title"
type: feature|bugfix|refactor|docs|infra
priority: P0|P1|P2
branch: "🔷feature/slug"
repo:
  url: 🔷
  root: 🔷
  paths_in_scope:
    - 🔷/path/one
    - 🔷/path/two
  paths_out_of_scope:
    - 🔷/do-not-touch
context:
  stack: {lang: 🔷, framework: 🔷, runtime: 🔷, package_manager: 🔷}
  versions: {🔷: 🔷}
  style_guides: [🔷link-to-lint/format rules]
  related_issues: [🔷]
problem_statement: >
  🔷 crisp description of the user-facing change or bug to fix, with business value.
non_goals:
  - 🔷
constraints:
  - Do not change public API of 🔷
  - Keep allocations under 🔷MB; P95 latency under 🔷ms
  - Follow 🔷security policy; no new network calls
artifacts_expected:
  output_mode: diff|whole_file
  pr_title_template: "[🔷component] 🔷"
  pr_body_sections: ["Context", "Implementation", "Tests", "Risks", "Follow‑ups"]
  decision_log: true   # short bullet log of assumptions/trade‑offs
acceptance_criteria:
  - [ ] 🔷 Given/When/Then #1
  - [ ] 🔷 Given/When/Then #2
verification:
  repro_steps: |
    🔷 commands / inputs to reproduce
  checks:
    - cmd: "🔷lint / 🔷typecheck / 🔷tests"
    - cmd: "🔷example e2e script with exit code 0 on success"
workflow_expectations:
  - plan-first
  - implement
  - self-check
  - emit_patch
  - run_verification
  - summarize

```

**Why this shape works**  
- **Clear pointers** let Codex and GPT‑5 jump to the right code quickly.  
- **Verification commands** enable agents to prove they’re done.  
- **Output contract** + **Structured Outputs** let you parse and apply patches safely.  
These mirror the **Codex prompting guide** and **GPT‑5 agentic prompting** recommendations. 

---

## 2) Prompt patterns that boost coding quality

You can embed these patterns in the **ticket** (for Codex).

### 2.1 Plan‑Implement‑Verify (PIV)
**Instruction snippet**
```
Before editing code:
1) Write a minimal plan (bullet list). 
2) Make the smallest viable change (diff or whole-file). 
3) Run the verification commands from the ticket. 
4) If any check fails, fix and re-run.
5) Emit final patch, then a short decision log.
```
Rationale: aligns with GPT‑5’s agentic preambles and tool‑aware behavior.

### 2.2 Diff‑first editing
Ask for **unified diff** or **search/replace blocks** to minimize token use and review overhead. GPT‑4.1 and later improved adherence to diff formats; GPT‑5 inherits and surpasses this reliability. 

**Instruction snippet**
```
Emit patches as JSON per `code_patch_v1` schema. For large rewrites, include full file content in `content` with format `whole_file`.
```

### 2.3 Rationale without chain‑of‑thought
Prefer a **short explanation** (bullet rationale/decision log) over free‑form chain‑of‑thought. GPT‑5’s cookbook notes such brief summaries can improve instruction‑following without exposing verbose reasoning.


### 2.4 Split large epics
Turn epics into **independent, verifiable sub‑tickets** (API contract, component, or service boundaries). Codex docs explicitly recommend splitting to improve throughput and reviewability.

---

## 3) Heuristics by task type

### 3.1 Bug fix
- **Ticket**: include failing test/logs, exact repro, suspected module, and non‑goals (don’t refactor unrelated code).  
- **Prompt**: PIV pattern + diff‑first + acceptance checks.

### 3.2 Feature slice (small)
- **Ticket**: new interface contract (types/endpoint), constraints (latency/allocations), and copy exact UX acceptance cases.  

### 3.3 Multi‑file refactor
- **Ticket**: name the symbols to rename/move; list directories in/out of scope; provide `codemod` rules if you have them; insist on green types/tests.  

### 3.4 Frontend polish
- **Ticket**: include screenshots/UX rules; define visual and a11y acceptance criteria; perf budgets.  

### 3.5 Test authoring
- **Ticket**: name frameworks, fixtures, and the **exact** commands to run; require coverage deltas in the PR body.  

### 3.6 Docs / READMEs / ADRs
- **Ticket**: target audience and scope; must link to the code it documents.  

---

## 4) Codex‑specific ticket addenda

For Codex (CLI/IDE/Cloud), add these **operational lines** so the agent behaves predictably:

```yaml
codex:
  approvals: on-request            # don't run untrusted commands without asking
  sandbox: workspace-write         # default sandbox; network disabled
  web_search: false                # enable only with allowlist
  progress: brief                  # tool preambles / progress updates
  review:
    ask_for_diff_format: unified   # patch preference
    pr_template: "🔷 link to template"
  agents_md: true                  # ensure AGENTS.md exists and is up-to-date
```

- The Codex prompting guide highlights **pointers**, **verification**, **customization**, and **splitting tasks**; reflect those explicitly.
- Codex security docs recommend **patch‑based workflows** and show how to configure sandbox & approvals.

---

## 5) Anti‑patterns (what to avoid)
- **Vague scopes**: “Improve performance” without a target or benchmark.  
- **Open‑ended rewrites**: allow the model to re‑architecture without an ADR.  
- **No verification**: tickets without runnable checks tend to drift.  
- **Diff + whole‑file mixed randomly**: pick a primary mode and explain when to switch.  
- **Long prompts with moving parts at the top**: breaks prompt caching benefits. 

---

## 6) Example: “Add optimistic updates to Todo list” (React + TS)

```yaml
title: "[web] Todo optimistic updates for create/delete"
type: feature
branch: "feature/todo-optimistic-updates"
repo:
  root: apps/web
  paths_in_scope: ["src/features/todos/*", "src/lib/api.ts"]
  paths_out_of_scope: ["src/features/profile/*"]
context:
  stack: {lang: TypeScript, framework: React 18, runtime: Node 20, package_manager: pnpm}
  style_guides: ["apps/web/.eslintrc.js","apps/web/.prettierrc"]
problem_statement: >
  Improve perceived performance by applying optimistic UI updates for creating and deleting todos.
constraints:
  - Keep bundle increase < 2KB gz.
  - No new runtime deps.
acceptance_criteria:
  - [ ] Creating a todo updates the list immediately; if server fails, UI rolls back with a toast.
  - [ ] Deleting a todo removes it immediately; failure rolls back and toasts.
  - [ ] No console errors; all tests pass.
verification:
  repro_steps: |
    pnpm --filter web dev
    # test by creating/deleting todos
  checks:
    - cmd: "pnpm --filter web lint && pnpm --filter web typecheck && pnpm --filter web test -w"
codex_guidance:
  pointers: ["src/features/todos/TodoList.tsx", "src/lib/api.ts"]
  split_large_tasks: true
  preambles: brief
```

Expected agent flow (PIV): plan → patch (diff) → run checks → summarize.

---

## 7) Quick checklist (paste into every ticket)

- [ ] **Scope**: files/symbols in/out; non‑goals included  
- [ ] **Pointers**: paths, stack traces, or identifiers included (greppable)  
- [ ] **Acceptance**: Given/When/Then; perf and security budgets  
- [ ] **Verification**: reproducible commands and expected exit codes  
- [ ] **Output**: diff vs whole‑file stated; JSON schema if parsed   
- [ ] **Split**: large scope broken into verifiable slices

---

## References (official OpenAI sources)

- **Introducing GPT‑5 for developers** — model capabilities; `verbosity`, `reasoning_effort` (incl. `minimal`), custom tools.  
  https://openai.com/index/introducing-gpt-5-for-developers/  
- **GPT‑5 Prompting Guide** — agentic eagerness control, tool preambles, markdown, planning.  
  https://cookbook.openai.com/examples/gpt-5/gpt-5_prompting_guide  
- **GPT‑5: New Params & Tools** — verbosity, custom tools with free‑form payloads, minimal reasoning.  
  https://cookbook.openai.com/examples/gpt-5/gpt-5_new_params_and_tools  
- **Codex prompting guide** — pointers, verification steps, customizing agent behavior, splitting tasks.  
  https://developers.openai.com/codex/prompting  
- **Codex security guide** — sandbox/approvals, patch‑based workflows, network policy.  
  https://developers.openai.com/codex/security  
- **Structured Outputs & Function Calling** — `strict: true` guarantees, JSON mode, tools.  
  https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api  
- **Reproducible outputs with `seed`** — cookbook example and cautions.  
  https://cookbook.openai.com/examples/reproducible_outputs_with_the_seed_parameter  
- **Prompt caching** — discount and placement of static vs dynamic content.  
  https://openai.com/index/api-prompt-caching/  
- **OpenAI Evals** — structured outputs/tools/web‑search evals.  
  https://cookbook.openai.com/examples/evaluation/use-cases/structured-outputs-evaluation  
  https://cookbook.openai.com/examples/evaluation/use-cases/web-search-evaluation

---

*Prepared for experienced engineering teams integrating GPT‑5 Codex with strong guardrails and a patch‑based CI/CD workflow.*
