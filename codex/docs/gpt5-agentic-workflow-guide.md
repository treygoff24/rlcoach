# GPT-5 Agentic Workflow Guide

> **Build reliable, observable, and safe agentic systems with GPT‑5 using the Responses API and the OpenAI Agents SDK.**

---

### Pre‑draft Checklist (what this guide does first)
- Survey latest **official OpenAI docs, cookbooks, and blog posts** on GPT‑5, the Responses API, Realtime, and the Agents SDK.
- Synthesize **core capabilities**: verbosity, minimal reasoning, hosted tools, custom tools (plaintext + grammar constraints), preamble messages, and state carry‑over.
- Distill **design patterns** for single/multi‑agent orchestration with **guardrails, handoffs, sessions, and tracing**.
- Compile **prompting guidance** specific to GPT‑5’s steerability and agentic behavior.
- Provide **worked examples** (Responses API + Agents SDK) with runnable or near‑runnable code/pseudocode.
- Enumerate **pitfalls/limitations** and mitigations (tool calling, safety, injection, naming drift).

---

## Table of Contents
- [What are Agentic Workflows?](#what-are-agentic-workflows)
- [Key Concepts and Terminology](#key-concepts-and-terminology)
- [Core Design Patterns](#core-design-patterns)
- [Prompt Engineering for Agentic GPT‑5 Apps](#prompt-engineering-for-agentic-gpt-5-apps)
- [Example Workflows](#example-workflows)
- [Pitfalls and Limitations](#pitfalls-and-limitations)
- [References](#references)

---

## What are Agentic Workflows?

**Agentic workflows** delegate *planning + action* to an LLM that can call tools, reason over multi‑turn state, and decide when to fetch knowledge, ask for help, or hand off to a specialist. In OpenAI’s ecosystem, the **Responses API** provides a stateful substrate for tool‑calling and multi‑turn context, and the **Agents SDK** offers orchestration primitives (agents, handoffs, guardrails, sessions, tracing) to compose larger systems.

With **GPT‑5**, agentic tasks become more predictable and controllable thanks to:

- **`verbosity`** (short vs. comprehensive answers), **`reasoning.effort: "minimal"`** to reduce latency when deep reasoning isn’t needed, and **preamble messages** (visible planning/progress messages between tool calls).
- **Built‑in tools** (e.g., `web_search`, `file_search`, and others) to reduce glue code and deliver citations.
- **Custom tools** that accept **plaintext payloads** and can be constrained by **context‑free grammars (CFG)**—ideal when JSON escaping is brittle (e.g., long code, SQL, configs).
- **State carry‑over** across turns using `previous_response_id` so reasoning context can be reused efficiently.
- **Realtime** support for production voice agents (async function calling, SIP phone calling, image input, and MCP server support).

---

## Key Concepts and Terminology

| Term | Definition / Why it matters |
|---|---|
| **Responses API** | Stateful API for multi‑turn, tool‑using interactions. Supports hosted tools (e.g., `web_search`, `file_search`) and carries state across turns (`previous_response_id`). Prefer for agentic apps. |
| **Built‑in tools** | OpenAI‑hosted tools like `web_search`, `file_search`, Code Interpreter, image generation, etc. The model selects/invokes them; responses can include citations or artifacts. |
| **Custom tools** | Developer‑defined tools the model can call with **raw text** (plaintext). Optionally constrain payloads via **CFG/regex** to enforce syntax (SQL/DSLs). *Note:* Custom tools currently **don’t support parallel tool calls**. |
| **Structured Outputs** | Guarantee schema‑conformant JSON (via `strict` + JSON Schema), improving type safety for automation/evals. |
| **`verbosity`** | GPT‑5 parameter (`low`/`medium`/`high`) to modulate *final answer* length without changing prompts. Useful for terse UX. |
| **`reasoning.effort`** | Controls depth of internal reasoning. Use `minimal` for extraction/formatting; higher for planning/tool‑heavy steps. |
| **Preamble messages** | Visible “plan/progress” hints the model may emit before/between tool calls; improves transparency and user trust. |
| **Agents SDK** | Orchestration primitives: **Agents, Handoffs, Guardrails, Sessions**, and **Tracing**. Production‑ready upgrade of prior “Swarm”. |
| **Handoffs** | Delegate to another agent via a tool (e.g., `transfer_to_refund_agent`), with optional input schemas and filters. |
| **Guardrails** | Input/output checks running alongside agents; tripwires can abort runs early (cheap model screens expensive work). |
| **Sessions/Memory** | Conversation state for multi‑turn workflows (SQLite, Conversations API, SQLAlchemy). |
| **Tracing** | First‑class spans for generations, tool calls, handoffs; visible in **OpenAI Traces** and exportable to observability stacks. |
| **MCP (Model Context Protocol)** | Standardized way to expose tools/prompts via remote servers; supported in Realtime and the Agents SDK. |
| **ChatGPT Agent (product)** | End‑user agent that browses, runs code, and uses tools; its system card documents mitigations for **prompt injection** and risky actions—insights transfer to API apps. |

---

## Core Design Patterns

### 1) Single Agent + Hosted Tools (Generalist)
- **Use when:** One model can plan/act with hosted + custom tools.
- **Stack:** Responses API + hosted tools; optional custom tool for code/SQL.
- **Notes:** Keep prompts tight, enforce structure for machine‑consumed outputs; enable preambles for UX.

### 2) Plan‑and‑Execute (Planner → Worker)
- **Use when:** You want a distinct planning step (outline/sub‑tasks) then execution with tools.
- **Stack:** Responses API turns with `previous_response_id`; or two **Agents** with a handoff.
- **Notes:** Set **`reasoning.effort: "minimal"`** for simple workers; higher effort for planners.

### 3) Router‑Specialist (Multi‑Agent with Handoffs)
- **Use when:** Specialized domains (policy, research, coding).  
- **Stack:** Agents SDK (**handoffs**) + **guardrails**; shared **session** for context.  
- **Notes:** Add handoff prompts; filter or redact history on transfer (e.g., remove tool logs).

### 4) Guardrail‑Gated Expensive Agent
- **Use when:** You want to block disallowed inputs/outputs before expensive reasoning or sensitive tools.  
- **Stack:** Agents SDK **input/output guardrails** (fast model), then run main agent.  
- **Notes:** Abort early on tripwire; log via tracing.

### 5) Realtime Voice Agent with Tools
- **Use when:** Low‑latency phone/voice experiences with function calling and images.  
- **Stack:** Realtime API + Agents SDK **realtime**; async function calls, SIP, MCP.  
- **Notes:** Keep turns short; specify voice/speaking style; confirm sensitive actions.

---

## Prompt Engineering for Agentic GPT‑5 Apps

**High‑leverage defaults for GPT‑5**

- **Prefer Responses API** for multi‑turn + tool use. Persist threads with `previous_response_id`; let the API manage context.
- Set **`text.verbosity`** globally (e.g., `low`), then override locally by instruction (e.g., “When emitting diffs, use high verbosity.”).
- Tune **`reasoning.effort`** per step: `minimal` for extraction/formatting; `high` for planning.
- Encourage **preamble messages** for visible plans/progress between tool calls.

**Tool definitions**

- Use **hosted tools** (`web_search`, `file_search`, etc.) when possible; they minimize glue code and preserve citations/artifacts.
- For custom integrations, prefer **Custom Tools** + **CFG/regex** to enforce syntax (SQL dialects, shell). *Note:* custom tools **don’t call in parallel**.
- Provide concise **descriptions** and **input contracts**. For JSON tools, use **Structured Outputs** with `strict` to guarantee types.

**Controlling agentic “eagerness”**

- GPT‑5 is *thorough* by default in agentic contexts; reduce tangential tool calls by explicitly scoping actions and tightening success criteria.
- Use **allow‑lists** (domains/APIs), **max tool‑calls per turn**, and **stop conditions** in the prompt to curb exploration.

**Instruction pattern: R²OC (Role + Rules + Resources + Outputs + Checks)**

- *Role:* “You are a research agent that answers with cited sources.”  
- *Rules:* “Never leak secrets; never run destructive commands.”  
- *Resources:* “You may use `web_search` and `file_search`.”  
- *Outputs:* “Return `Answer`, `Sources[]`, `Confidence(0–1)` JSON.” (use `strict`)  
- *Checks:* “If sources < 2, search again once; else finalize.”

**Safety & robustness**

- **Prompt injection:** Treat third‑party content as hostile. Require **explicit user confirmation** before high‑impact actions; add watch‑mode/human‑in‑the‑loop where warranted.  
- **Evals:** Write evals for tool‑use correctness, format adherence, and refusal handling; automate regressions.  
- **Sessions & Tracing:** Persist conversations for durability; trace tool calls/handoffs for debugging and audits.

---

## Example Workflows

### A) Single‑Agent “Research & Brief” (Responses API + hosted tools)

**Goal:** Given a topic, produce a 1‑page brief with inline citations and a JSON metadata block; minimize unnecessary tool calls.

```python
# Python 3.10+
from openai import OpenAI

client = OpenAI()

SYSTEM = """You are a research agent. Scope strictly to the user's topic.
Tools: web_search only. Do not use tools unless needed to verify or cite.
When done, produce:
1) A concise brief (Markdown, with inline [n] markers).
2) A JSON block with fields:
   {"sources": [{"title": str, "url": str}], "confidence": float}
If fewer than 2 credible sources are found, perform one more web_search, then stop.
"""

topic = "Semiconductor investment trends in LATAM (last 12 months)"

resp1 = client.responses.create(
    model="gpt-5",
    input=[
        {"role": "developer", "content": [{"type":"input_text","text": SYSTEM}]},
        {"role": "user", "content": [{"type":"input_text","text": topic}]}
    ],
    tools=[{"type": "web_search"}],
    text={"verbosity": "low"},                 # terse final answer
    reasoning={"effort": "minimal"}            # low-latency unless more is needed
)

# Continue the thread (e.g., ask for a 3-bullet exec summary):
resp2 = client.responses.create(
    model="gpt-5",
    input="Summarize the brief into 3 bullets for an exec.",
    previous_response_id=resp1.id,
    text={"verbosity": "low"}
)
print(resp2.output_text)
```

**Why this works**
- **Hosted `web_search`** integrates citations and keeps state between turns.
- **`previous_response_id`** avoids hand‑rolled conversation stitching.
- **`minimal` reasoning + `verbosity: low`** keeps latency/cost down; escalate in later turns if needed.

> **Variation:** Add a **Structured Output** constraint for the JSON block (schema with `strict: true`).

---

### B) Multi‑Agent “Triage → Policy → Writer” (Agents SDK with handoffs, guardrails, sessions, tracing)

**Goal:** Triage a user request, route to a policy specialist or a writer, apply guardrails, and maintain session memory with tracing.

```python
# pyproject.toml:  pip install openai-agents
from agents import Agent, Runner, handoff
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from pydantic import BaseModel

# 1) Guardrail: cheap gate to block disallowed intent before costly work.
class GateResult(BaseModel):
    allowed: bool
    reason: str

gate = Agent(
    name="Gate",
    instructions="Decide if the user's ask is allowed under our policy. Respond with allowed + reason.",
    output_type=GateResult
)

# 2) Specialists
policy = Agent(
    name="Policy",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
You are a policy analyst. Cite sources. Keep final JSON summary under 200 tokens."""
)

writer = Agent(
    name="Writer",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
You are a concise writer. Produce Markdown with a 3-part structure."""
)

# 3) Triage with handoffs
triage = Agent(
    name="Triage",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
Decide whether the user's ask is a policy analysis or a writing task.
If policy, handoff to 'Policy'. If writing, handoff to 'Writer'.""",
    handoffs=[handoff(policy), handoff(writer)]
)

# 4) Orchestration: run guardrail, then triage
async def run_request(user_text: str):
    g = await Runner.run(gate, user_text)     # cheap screen
    if not g.final_output.allowed:
        return f"Blocked: {g.final_output.reason}"

    # With Sessions, you can persist cross‑turn context; see SQLiteSession in docs.
    result = await Runner.run(triage, user_text)
    return result.final_output

# Add tracing via environment or programmatically (see Tracing docs).
```

**Why this works**
- **Handoffs** expose inter‑agent delegation as tool calls with recommended prompts, letting the LLM route cleanly.  
- **Guardrails** run in parallel to agents and can *tripwire* early, saving time/cost.  
- **Sessions** and **Tracing** provide durability and observability for production.

> **Voice/Realtime:** Swap the runner with **RealtimeAgent** to add low‑latency speech and async function calls (SIP, image input, MCP).

---

## Pitfalls and Limitations

- **Custom tools are not parallelizable.** Use them where plaintext payloads shine (code, SQL, configs), but design for sequential calls—or wrap with hosted/JSON tools when you need parallel fan‑out.
- **Naming drift:** Early posts/examples used `web_search_preview`; current docs/cookbooks use `web_search`. Favor current API/cookbook examples and be prepared to update tool names as they stabilize.
- **Over‑eager agents:** GPT‑5 tends to gather context thoroughly. If latency/cost matter, *explicitly restrict actions*, specify stop conditions, and set `reasoning.effort="minimal"` for sub‑steps.
- **Injection & high‑impact actions:** Web content can carry **prompt injections**. Adopt layered mitigations: confirmations, constrained domains, content filters, and human‑in‑the‑loop for sensitive actions. Review lessons from ChatGPT Agent’s system card.
- **Schema brittleness:** For strict machine consumption, enforce **Structured Outputs** (`strict`) or grammar‑constrained custom tools instead of relying on freeform text.
- **Minimal reasoning ≠ non‑reasoning:** GPT‑5 with `minimal` effort is still a reasoning model. The separate non‑reasoning ChatGPT model is `gpt‑5‑chat‑latest`—use the right model by task.
- **Doc/SDK churn:** Tools and parameters evolve (e.g., Realtime/Agents SDK). Track changelogs/cookbooks and validate against API reference before deploys.

---

## References
- **Introducing GPT‑5 for developers** — API features (`verbosity`, `reasoning.effort: "minimal"`, custom tools + CFG): https://openai.com/index/introducing-gpt-5-for-developers/
- **GPT‑5 System Card (PDF):** https://cdn.openai.com/gpt-5-system-card.pdf
- **GPT‑5 Prompting Guide (Cookbook):** https://cookbook.openai.com/examples/gpt-5/gpt-5_prompting_guide
- **GPT‑5 New Params & Tools (Cookbook) — verbosity, custom tools, CFG, minimal reasoning:** https://cookbook.openai.com/examples/gpt-5/gpt-5_new_params_and_tools
- **New tools for building agents** — Responses API + built‑in tools; Agents SDK overview: https://openai.com/index/new-tools-for-building-agents/
- **New tools & features in the Responses API** — MCP, tool performance, reasoning summaries, encrypted reasoning items: https://openai.com/index/new-tools-and-features-in-the-responses-api/
- **Responses API — Web Search & State (Cookbook):** https://cookbook.openai.com/examples/responses_api/responses_example
- **OpenAI API — Responses API reference:** https://platform.openai.com/docs/api-reference/responses
- **Migrate to Responses (Guide):** https://platform.openai.com/docs/guides/migrate-to-responses
- **Structured Outputs (Blog):** https://openai.com/index/introducing-structured-outputs-in-the-api/
- **Structured Outputs (Cookbook intro):** https://cookbook.openai.com/examples/structured_outputs_intro
- **OpenAI Agents SDK (docs home):** https://openai.github.io/openai-agents-python/
  - **Handoffs:** https://openai.github.io/openai-agents-python/handoffs/
  - **Guardrails:** https://openai.github.io/openai-agents-python/guardrails/
  - **Sessions:** https://openai.github.io/openai-agents-python/sessions/
  - **Tracing:** https://openai.github.io/openai-agents-python/tracing/
- **Introducing gpt‑realtime (Realtime API GA; async function calling, SIP, image input, MCP):** https://openai.com/index/introducing-gpt-realtime/
- **Realtime Prompting Guide (Cookbook):** https://cookbook.openai.com/examples/realtime_prompting_guide
- **OpenAI Harmony (channels/preambles article):** https://cookbook.openai.com/articles/openai-harmony
- **ChatGPT Agent System Card (PDF):** https://cdn.openai.com/pdf/839e66fc-602c-48bf-81d3-b21eacc3459d/chatgpt_agent_system_card.pdf
- **ChatGPT Agent — product overview:** https://openai.com/index/introducing-chatgpt-agent/

---

*Validated for completeness and format: definitions, patterns, prompting, examples (code/pseudocode), pitfalls, and references included.*
