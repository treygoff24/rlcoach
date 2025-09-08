# Effective Prompting for GPT-5: Software Development and Agentic Coding Workflows

**Date:** September 08, 2025  
**Author:** AI Assistant

## Table of Contents
- [Introduction](#introduction)
- [Best Practices from OpenAI](#best-practices-from-openai)
  - [Model & API Choices](#model--api-choices)
  - [Tool/Function Calling](#toolfunction-calling)
  - [Structured Outputs](#structured-outputs)
  - [Prompt Architecture for Agentic Workflows](#prompt-architecture-for-agentic-workflows)
  - [Long-Context & Prompt Organization](#long-context--prompt-organization)
  - [MCP (Model Context Protocol) & Hosted Tools](#mcp-model-context-protocol--hosted-tools)
  - [Observability, Evals & Iteration](#observability-evals--iteration)
  - [Safety & Human-in-the-Loop](#safety--human-in-the-loop)
- [Effective Prompting Strategies (Software Dev & Agentic Workflows)](#effective-prompting-strategies-software-dev--agentic-workflows)
  - [A. High-Signal Prompt Template for Coding Agents](#a-high-signal-prompt-template-for-coding-agents)
  - [B. Planning–Execute–Verify Loops](#b-planningexecuteverify-loops)
  - [C. Tool Boundaries & Call Ordering](#c-tool-boundaries--call-ordering)
  - [D. Patch/Diff and PR-Style Workflows](#d-patchdiff-and-pr-style-workflows)
  - [E. Long-Repo Navigation & Retrieval](#e-long-repo-navigation--retrieval)
  - [F. Determinism & Output Controls](#f-determinism--output-controls)
  - [G. Observability & Tracing](#g-observability--tracing)
  - [H. Safeguards](#h-safeguards)
- [General Guidance](#general-guidance)
- [References](#references)

---

## Introduction
This report consolidates the latest *official OpenAI* guidance and other reputable sources to present best practices for prompting **GPT‑5** with a focus on **software development** and **agentic coding** (tool-using) workflows. It emphasizes model/API selection, structured outputs, tool calling, MCP, orchestration patterns, and rigorous safety/evaluation practices. citeturn18view0turn6view0

---

## Best Practices from OpenAI

### Model & API Choices
- **Prefer the Responses API for agentic apps.** It unifies tool use, supports background mode for long tasks, and exposes *reasoning summaries* and *encrypted reasoning items*; these improve reliability, observability, and privacy in production. citeturn6view0
- **Persist model reasoning items between tool calls** (where supported) to improve tool selection and reduce latency/cost in multi-tool turns. citeturn11view0
- **GPT‑5 adds agentic strengths** for multi-step coding and long chains of tool calls, and introduces an API **verbosity** control (plus “minimal” reasoning mode). Use low verbosity for terse outputs and higher for richer explanations. citeturn18view0

### Tool/Function Calling
- **Define tools via the `tools` parameter** (not free‑text) and write **clear names/descriptions** plus parameter docs; models choose and populate arguments more reliably with native schemas. citeturn10view0
- **Specify call ordering for frequent flows** and **when to use (or not use) each tool** to avoid misrouting and over/under-use. Include *few‑shot* examples where argument construction is error‑prone. citeturn11view0
- **Validate and gate high‑impact calls** (e.g., user confirmation, least privilege, and argument validation). Encourage **clarifying questions** when inputs are ambiguous. citeturn16view0

### Structured Outputs
- Favor **schema‑validated function calls** (tool outputs) over free‑form text; treat function descriptions as an **interface contract** for the agent. citeturn11view0

### Prompt Architecture for Agentic Workflows
- Start agent prompts with three **system/developer reminders**: **Persistence** (keep going until done), **Tool use** (don’t guess; use tools to inspect/act), and optional **Planning** (explicit plan & reflection between calls). These have shown large gains in agentic coding tasks. citeturn10view0
- Keep instructions **specific & literal** (GPT‑4.1+ families adhere closely). When behavior drifts, a single clarifying sentence often suffices. citeturn10view0

### Long-Context & Prompt Organization
- For very long prompts/contexts, **repeat critical instructions at the top (and optionally bottom)**; if only once, **put instructions above** the context. citeturn10view0

### Observability, Evals & Iteration
- Treat prompt engineering as **empirical**: define task‑level **evals**, iterate often, and migrate older prompts with a structured critique–revise–retest loop. citeturn10view0turn12view0
- The **Agents SDK** provides a minimal set of primitives (agents, handoffs, guardrails, sessions) with **built‑in tracing** to visualize/debug agent runs. citeturn7view0

### Safety & Human-in-the-Loop
- Build **guardrails** (tripwires, validations, escalation rules). Start with single‑agent + tools; split into multi‑agent only when logic/tool overlap demands it; always plan **human intervention** for high‑risk actions. citeturn14view0

---

## Effective Prompting Strategies (Software Dev & Agentic Workflows)

### A. High-Signal Prompt Template for Coding Agents
Use this minimal structure as a reusable template:
```
# Role & Objective
You are a coding agent. Resolve the user's request end-to-end.

# Persistence
Continue working and using tools until the task is fully solved; only stop when done.

# Tool Use
If codebase details are uncertain, inspect files with tools—do not guess. Prefer tools for math/data/code execution.

# Planning (optional)
Before each tool call: plan steps. After each call: reflect and decide next action.

# Decision Rules
- When to use <tool_A> vs <tool_B>.
- Call order for common flows.
- Ask clarifying questions if inputs are missing.

# Output Rules
- Prefer diffs/patches for edits.
- Keep answers terse unless verbosity is requested.
```
This aligns with OpenAI’s guidance on agentic reminders, tool usage via native schemas, and explicit decision rules. citeturn10view0turn11view0

### B. Planning–Execute–Verify Loops
1. **Plan**: List concrete subgoals & required inspections.  
2. **Execute**: Call tools to read files, run code/tests, or modify state.  
3. **Verify**: Re-run tests/lints; summarize what changed; propose next steps.  
Use higher **verbosity** only when you want detailed reasoning visible to the user; otherwise keep outputs concise. citeturn18view0

### C. Tool Boundaries & Call Ordering
- Encode *when to use each tool* and *call order* for frequent scenarios (e.g., check for directory existence before file writes).  
- Provide **few-shot examples** inside tool descriptions where argument formats are tricky.  
- In ambiguous cases, instruct the model to **ask a question** instead of guessing. citeturn11view0turn16view0

### D. Patch/Diff and PR-Style Workflows
- Request **unified diffs/patches** for code edits to simplify review & application; avoid “whole file” rewrites.  
- Ask the agent to **add/update tests** and run them before declaring completion. citeturn10view0

### E. Long-Repo Navigation & Retrieval
- Have the agent:  
  1) enumerate the relevant files/modules;  
  2) open/inspect only what’s necessary;  
  3) summarize findings; then  
  4) proceed with edits/tests.  
- For external systems & knowledge, connect via **MCP** and hosted tools; **whitelist only needed tools**. citeturn15view0

### F. Determinism & Output Controls
- For **reproducibility** in API workflows, set a **`seed`** and keep other parameters constant (prompt, temperature, etc.); expect “similar”, not perfect, determinism.  
- For **code generation**, begin with **low temperature** and scale up only if needed; use GPT‑5’s **verbosity** to control explanation length without inflating token costs. citeturn17search10turn18view0

### G. Observability & Tracing
- Use the **Agents SDK tracing** to inspect tool decisions, handoffs, and loops; attach evals to regressions and migrate prompts with a repeatable process. citeturn7view0turn12view0

### H. Safeguards
- Validate function arguments; **confirm** before irreversible actions; apply **least privilege** to tools.  
- Add **tripwires** for risky intents (refunds, payments, destructive ops) to hand off to a human or require multi‑step confirmation. citeturn16view0turn14view0

---

## General Guidance
- **Be explicit.** State the goal, constraints, acceptance criteria, and the exact output format. Avoid ambiguity (“do it better”) in favor of concrete directives (“limit to 80 cols; add unit tests for edge cases”). citeturn20view0
- **Show, don’t tell.** Provide *examples* (inputs/outputs/tests) to anchor behavior—especially for argument formats or domain-specific APIs. citeturn20view0
- **Chunk complex tasks.** Break work into steps; ask for a plan first if the scope is broad. citeturn20view0
- **Keep context relevant.** Start a new thread for new tasks; prune stale context to reduce distraction. citeturn20view0
- **Prefer structured results.** Use JSON Schema / Structured Outputs for anything you need to parse; treat free text as last resort. citeturn9search2
- **Iterate with evals.** Define measurable checks (tests, linters, task pass/fail), iterate, and migrate prompts systematically over time. citeturn12view0

---

## References
- [GPT‑5 is here | OpenAI](https://openai.com/gpt-5/)
- [New tools and features in the Responses API | OpenAI](https://openai.com/index/new-tools-and-features-in-the-responses-api/)
- [GPT‑4.1 Prompting Guide | OpenAI Cookbook](https://cookbook.openai.com/examples/gpt4-1_prompting_guide)
- [o3/o4‑mini Function Calling Guide | OpenAI Cookbook](https://cookbook.openai.com/examples/o-series/o3o4-mini_prompting_guide)
- [Introduction to Structured Outputs | OpenAI Cookbook](https://cookbook.openai.com/examples/structured_outputs_intro)
- [Structured Outputs | OpenAI Docs](https://platform.openai.com/docs/guides/structured-outputs)
- [Function Calling | OpenAI Docs](https://platform.openai.com/docs/guides/function-calling)
- [Responses API Reference | OpenAI Docs](https://platform.openai.com/docs/api-reference/responses)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [A practical guide to building agents (PDF) | OpenAI](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf)
- [Guide to Using the Responses API’s MCP Tool | OpenAI Cookbook](https://cookbook.openai.com/examples/mcp/mcp_tool_guide)
- [Deep Research API with the Agents SDK | OpenAI Cookbook](https://cookbook.openai.com/examples/deep_research_api/introduction_to_deep_research_api_agents)
- [Prompt Migration Guide | OpenAI Cookbook](https://cookbook.openai.com/examples/prompt_migration_guide)
- [Reproducible outputs with the `seed` parameter | OpenAI Cookbook](https://cookbook.openai.com/examples/reproducible_outputs_with_the_seed_parameter)
- [How to use function calling with Azure OpenAI | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/function-calling)
- [How to generate reproducible output with Azure OpenAI | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/reproducible-output)
- [Prompt engineering for GitHub Copilot Chat | GitHub Docs](https://docs.github.com/en/copilot/concepts/prompt-engineering)
- [Best practices for using GitHub Copilot | GitHub Docs](https://docs.github.com/en/copilot/get-started/best-practices)

