# AGENTS.md — Building agents on PydanKit

Guidance for a coding agent (Claude Code, Cursor, Copilot, …) extending this
template. This is the **single source of truth** for *how to build here*. For
architecture and file layout, see [CLAUDE.md](CLAUDE.md); don't duplicate it.

PydanKit is a **minimal Pydantic AI skeleton**: plain-text output by default,
provider-agnostic, with in-memory conversation history and an optional API.

> **Official docs — the source of truth for APIs and best practices:**
> https://pydantic.dev/docs/ai/overview/
> Consult them before using a Pydantic AI API you're unsure about. Pydantic AI's
> APIs change across versions (this repo has already been bitten — see
> Anti-patterns), so verify current usage against the docs rather than assuming.

## The golden rule

**Make the smallest change that satisfies the request.** Do not add structured
output, guardrails, extra agents, or persistence "to be safe." Add complexity
**only** when a trigger in the decision rules below fires. When unsure, prefer the
smaller change and say what you deliberately left out.

## Decision rules (when to add complexity — not before)

- **Output type.** Keep `output_type=str` (the default) unless the output is
  consumed by *code* (parsed, branched on, stored as fields). Only then set a
  structured `output_type` — see the `AgentResponse` example in `src/models.py`.
  Never wrap a human-facing prose answer in a one-field model.
- **Tools vs. more agents.** Add a tool for each discrete capability. Stay
  **single-agent** until one agent measurably fails to follow instructions or
  picks the wrong tools; only then split into multiple agents. More agents = more
  overhead, so this is a last resort, not a default.
- **Tool approval / guardrails.** Add human-approval or risk-gating **only** for
  irreversible or high-impact tools (writes, deletes, payments, external sends).
  Read-only tools need none. Don't build a guardrail layer for a toy tool.
- **Model selection.** Prototype with a capable model to establish a baseline,
  then downshift to cheaper/faster models and confirm quality holds via evals.
- **Memory.** The default backend is in-memory and **ephemeral** (lost on restart,
  not shared across API workers). A durable **SQLite backend now ships**
  (`SqliteMemoryStorage`, `src/memory/sqlite_storage.py`); select it with
  `MEMORY_STORAGE_TYPE=sqlite` (needs the `[auth]` extra). For other backends,
  implement the `MemoryStorage` interface and select it in `get_memory_manager`.
  Do not hack persistence in elsewhere.
- **Auth.** On by default (`AUTH_ENABLED=true`; set false to run open). Identity
  (ADR 0001) comes from the credential, never the request body, and every data route
  scopes to the caller. Don't re-introduce a client-supplied `user_id`, and don't add
  a second parallel auth gate — extend the one resolver (`src/auth/dependencies.py`).
- **Providers.** The template is provider-agnostic. Switch models via `MODEL_NAME`
  (e.g. `anthropic:claude-sonnet-4-5`, `deepseek:deepseek-chat`) and the
  provider's standard env key. **Never** hard-code a provider or add a
  provider-key field to `Settings`.
- **Usage limits.** Every run is bounded by `usage_limits`. Never remove it. If a
  legitimate workflow needs more steps, raise `AGENT_REQUEST_LIMIT`.

## Definition of Done (every change must pass)

1. `ruff check src tests` and `ruff format src tests` are clean.
2. `pytest` is green (it runs offline via `TestModel` — no API key needed).
3. **Added a tool?** Add a test using `TestModel` + `capture_run_messages` that
   asserts the tool is selected and its deps are injected (see
   `tests/test_agent.py`).
4. **Changed agent behavior?** Add or update a case in the eval pattern
   (`tests/eval_example.py`), or state why an eval doesn't apply.
5. **Changed a seam or a rule here?** Update *this file* — it is the source of
   truth. Don't restate volatile facts (model names, signatures) that live in code.
6. **Used a Pydantic AI API you're not certain about?** Verify it against the
   official docs (https://pydantic.dev/docs/ai/overview/) before relying on it —
   don't code from memory of an older version.

## Commands

```bash
pip install -e ".[dev]"          # install (dev extras: pytest, ruff, evals)
ruff check src tests             # lint
ruff format src tests            # format
pytest                           # tests (offline; or: make test)
python -m tests.eval_example     # run the Pydantic Evals example
python -m src.main chat "..."    # run the agent
python -m src.main serve         # API + dashboard (needs: pip install -e ".[api]")
```

## Decision records (ADRs)

Significant, hard-to-reverse design decisions are recorded in [`docs/adr/`](docs/adr/).
Read the relevant ADR before touching the area it covers, and add a new one
(don't silently diverge) when you make a decision of similar weight.

- [ADR 0001 — Authentication & multi-user data isolation](docs/adr/0001-authentication.md)
  *(Implemented.)* Standing invariants: **the CLI (`python -m src.main`) is an
  unauthenticated, trusted admin shell by design** — do not "harden" it with a
  login; `user_id` comes from the authenticated identity, never the request body;
  and agent output must stay escaped in the dashboard (no markdown-to-HTML without
  sanitization) — that's the XSS backstop for the session cookie.
- [ADR 0002 — Admin UI for service accounts & keys](docs/adr/0002-admin-ui-service-accounts.md)
  *(Implemented; amends 0001.)* Admin-only `/admin/*` endpoints + dashboard panel to
  manage passwordless service accounts and their API keys. Invariants: **the UI never
  grants admin** (no self-propagating admin keys), first admin is **env-seeded**
  (no public setup endpoint — race-to-setup takeover), and admin secrets render via
  `textContent`, never `innerHTML`. No audit trail in v1 (documented gap).

## Anti-patterns (do NOT reintroduce these — they've all bitten this repo)

- Forcing a structured `output_type` as the default (breaks plain-text streaming;
  invites fake fields like a self-reported "confidence").
- Filtering tool-call/return messages out of saved history — it corrupts
  multi-turn reasoning and, with structured output, drops the answer entirely.
  Persist the full `result.new_messages()`.
- Advertising features that don't exist (unimplemented storage backends, config
  knobs that nothing reads). A missing feature is neutral; a lying one is a trap.
- Pinning a dependency with no upper bound (a future major breaks fresh clones).
- Reaching into private attributes (`agent._function_toolset`, etc.). Use public
  APIs; if none exists, track the data yourself (see the `TOOLS` list).
