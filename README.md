# PydanKit

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Pydantic AI](https://img.shields.io/badge/Pydantic%20AI-powered-green.svg)](https://ai.pydantic.dev/)

A minimal, well-structured skeleton for building AI agents with [Pydantic AI](https://ai.pydantic.dev/). Plain-text output by default (structured output is an opt-in example), with conversation memory and an optional REST API + dashboard.

- 🤖 **Type-safe agents** — plain text by default, structured output opt-in
- 💬 **Conversation memory** — in-memory, or durable SQLite/Postgres
- 🔐 **Optional per-user auth** — login + API keys, data isolation
- 🚀 **FastAPI dashboard + REST API** (optional)
- 🧪 **Offline tests** (`TestModel`) + a Pydantic Evals example
- 🐳 **Docker** + a [verified deploy guide](docs/deployment.md)

## Quick start

Two commands. `init` asks a few questions and writes a correct `.env` for your setup, so you never hand-edit config:

```bash
uv run python -m src.main init      # creates the venv, installs, runs the setup wizard
#   → name your agent; pick provider / storage / auth; it offers to install any extras
# open .env and paste your API key into the one labeled slot, then:
uv run python -m src.main chat "What can you help me with?"
```

No [uv](https://docs.astral.sh/uv/)? Use the standard flow — everything after is identical:

```bash
python -m venv .venv && . .venv/bin/activate    # Windows: .\.venv\Scripts\Activate.ps1
pip install -e .
python -m src.main init
```

Then explore:

```bash
python -m src.main interactive     # chat with memory across turns
python -m src.main serve           # dashboard at http://localhost:8000 (pick "web" in init, or: pip install -e .[api])
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
python -m src.main users --add alice --admin   # prompts for a password
python -m src.main apikey --issue alice          # per-user API key (shown once)
```

The CLI is a trusted admin shell — it needs no login. Service accounts, admin panel, and shell-less bootstrap are covered in [CLAUDE.md](CLAUDE.md) / [ADR 0001](docs/adr/0001-authentication.md). CLI `chat`/`interactive` are local and unauthenticated by design; auth protects the API.

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

## Docs

- **[AGENTS.md](AGENTS.md)** — how to build on PydanKit (decision rules, definition of done); read by coding agents
- **[CLAUDE.md](CLAUDE.md)** — architecture, streaming, memory, and auth internals
- **[docs/deployment.md](docs/deployment.md)** — verified cloud deploy guide
- **[Pydantic AI](https://ai.pydantic.dev/)** — framework docs

MIT License — see [LICENSE](LICENSE).
