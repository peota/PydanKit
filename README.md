# PydanKit

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Pydantic AI](https://img.shields.io/badge/Pydantic%20AI-powered-green.svg)](https://ai.pydantic.dev/)

A minimal, well-structured skeleton for building AI agents with [Pydantic AI](https://ai.pydantic.dev/), with conversation memory and an optional REST API + dashboard.

- 🤖 **Type-safe agents** — plain text by default, structured output opt-in
- 💬 **Conversation memory** — in-memory, or durable SQLite/Postgres
- 🔐 **Optional per-user auth** — login + API keys, data isolation
- 🚀 **FastAPI dashboard + REST API** (optional)
- 🧪 **Offline tests** (`TestModel`) + a Pydantic Evals example
- 🐳 **Docker** — ready to build and run

## Quick start

Two commands. `init` asks a few questions and writes a correct `.env` for your setup, so you never hand-edit config:

```bash
uv run python -m src.main init
# paste your API key into the slot .env marks, then:
uv run python -m src.main chat "What can you help me with?"
```

`init` creates the venv, installs, and walks you through naming your agent and picking provider / storage / auth — then offers to install whatever extras that choice needs.

No [uv](https://docs.astral.sh/uv/)? Use the standard flow — everything after is identical:

```bash
python -m venv .venv && . .venv/bin/activate    # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -U pip                     # 3.10/3.11 venvs ship pip too old for editable installs
pip install -e .
python -m src.main init
```

Then explore:

```bash
python -m src.main interactive     # chat with memory
python -m src.main serve           # web dashboard on :8000
```

## Customize your agent

`init` sets up the **runtime**. To build the agent's **logic** (tools, output, prompts):

- **In [Claude Code](https://claude.ai/code):** run `/setup-agent` — a wizard with pre-built templates.
- **By hand:** add an `async def` in `src/tools.py`, register it in `src/agent.py`. Full guide in [AGENTS.md](AGENTS.md) and [CLAUDE.md](CLAUDE.md).

```python
# src/tools.py
async def my_tool(ctx: RunContext[AgentDeps], query: str) -> str:
    """Describe what this tool does."""
    return f"Result for {query}"
```

## Configuration

`init` writes these for you; edit `.env` to change them later.

| Variable | What it does |
|----------|--------------|
| `AGENT_NAME` | Branding shown on the dashboard, browser tab, and API title |
| `MODEL_NAME` + provider key | e.g. `openai:gpt-4o` + `OPENAI_API_KEY`. Any provider works (`anthropic:` / `groq:` / `deepseek:` / `google:`); all SDKs ship with pydantic-ai |
| `AUTH_ENABLED` | Per-user login for the API (default `true`; `false` runs open) |
| `DATABASE_URL` | SQLite (default) or Postgres — also makes memory durable |
| `MEMORY_ENABLED` / `MEMORY_MAX_MESSAGES` | Conversation memory (default on, last 100) |
| `LOGFIRE_TOKEN` | Optional [Logfire](https://logfire.pydantic.dev/) observability |

## Authentication

On by default. Create the first admin (there's no self-signup), then sign in on the dashboard:

```bash
python -m src.main users --add alice --admin
python -m src.main apikey --issue alice          # per-user API key, shown once
```

The CLI is a trusted admin shell — it needs no login. Service accounts, admin panel, and shell-less bootstrap are covered in [CLAUDE.md](CLAUDE.md). CLI `chat`/`interactive` are local and unauthenticated by design; auth protects the API.

## REST API

```bash
python -m src.main serve      # dashboard + API at http://localhost:8000
```

Key endpoints: `POST /chat`, `POST /chat/stream` (SSE), `GET /sessions`, `GET /docs`. With auth on, pass your API key — identity comes from the credential, not the request body:

```bash
curl -X POST http://localhost:8000/chat -H "X-API-Key: <key>" \
  -H "Content-Type: application/json" -d '{"prompt": "Hello!"}'
```

## Docker

```bash
docker build -t my-agent .
docker run --env-file .env my-agent chat "Hello"
docker run --env-file .env -p 8000:8000 my-agent serve --host 0.0.0.0
```

## Before you deploy

A few things the template intentionally leaves to you — quick to set, easy to forget:

- **Cap your spend at the provider.** The agent's only built-in guardrail is
  `AGENT_REQUEST_LIMIT` (tool-calls per run) — there is **no token budget or per-user rate
  limit** on `/chat/stream`. For a shared API key, set a hard monthly spend limit in your
  OpenAI/Anthropic dashboard. It's the backstop for a leaked key or a runaway client loop,
  neither of which "trusting your team" covers.
- **Turn on TLS + secure cookies.** Behind HTTPS, set `SESSION_COOKIE_SECURE=true` and set
  `CORS_ORIGINS` to your real origin (never `*` — credentials are on).
- **Schema changes aren't auto-migrated.** Tables are created on demand; there are no
  migrations by design. Pulling a
  template version that changes the auth/memory schema will **not** migrate your existing
  SQLite/Postgres data — back up your database before upgrading, or expect to recreate
  accounts and conversation memory. Adopt Alembic if you need durable, evolving schemas.

## Docs

- **[AGENTS.md](AGENTS.md)** — how to build on PydanKit (decision rules, definition of done); read by coding agents
- **[CLAUDE.md](CLAUDE.md)** — architecture, streaming, memory, and auth internals
- **[Pydantic AI](https://ai.pydantic.dev/)** — framework docs

MIT License — see [LICENSE](LICENSE).
