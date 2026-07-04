# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Building or extending an agent? Read [AGENTS.md](AGENTS.md) first** — it holds the decision rules, definition of done, and anti-patterns for working in this template. This file covers architecture and mechanics.

## Commands

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Lint
ruff check src

# Format
ruff format src

# Test (offline; uses Pydantic AI TestModel, no API key needed)
pytest
# or: make test

# First-time setup: interactively write a scenario-correct .env (a smart cp of
# .env.example). Asks for AGENT_NAME + run mode / provider / storage / auth, then
# offers to install the extras that choice needs (pip- and uv-aware). See src/installer.py.
python -m src.main init

# Run agent
python -m src.main chat "Your prompt here"
python -m src.main interactive

# Install and run API server (optional; [api] bundles the auth deps)
pip install -e ".[api]"
python -m src.main serve --port 8000
# Dashboard available at http://localhost:8000/

# Authentication (on by default; see the Authentication section)
python -m src.main users --add alice --admin   # create the first admin (trusted CLI)
python -m src.main apikey --issue alice         # issue a per-user API key

# Docker (includes API extras)
docker build -t pydantic-ai-agent .
docker run --rm --env-file .env pydantic-ai-agent chat "Hello"
docker run --rm --env-file .env -p 8000:8000 pydantic-ai-agent serve --host 0.0.0.0
```

## Architecture

This is a minimal Pydantic AI agent skeleton with dependency injection. The agent
returns **plain text by default**; structured output is an opt-in example.

**Data flow:** `main.py` (CLI) or `api.py` (REST) → `agent.py` (orchestration) → `tools.py` (actions)

**Key patterns:**
- `AgentDeps` (dependencies.py): Dataclass injected into all tool calls via `RunContext[AgentDeps]`. Add DB connections, API clients, or user context here.
- Output type (agent.py): `output_type=str` by default. `AgentResponse` (models.py) is a commented example showing structured output (enum + list); set `output_type=AgentResponse` to opt in.
- Usage limits (agent.py): every run passes `UsageLimits(request_limit=...)` so a misbehaving tool can't loop forever. Configure via `AGENT_REQUEST_LIMIT`.
- Tools (tools.py): Async functions registered with `agent.tool()`. First param is always `ctx: RunContext[AgentDeps]`.
- Settings (config.py): Environment-based config via pydantic-settings, loaded from `.env`.
- Provider-agnostic (config.py): `config.py` calls `load_dotenv()` so provider SDKs read their own keys from the environment on any entry point. Set `MODEL_NAME` to any supported model (`openai:...`, `anthropic:...`, `groq:...`, `deepseek:...`, `google:...`) and supply that provider's key (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.). No provider key is modeled in `Settings` — do not re-add one.
- Lazy initialization (agent.py): Agent created via `get_agent()` on first use, not at import time. This allows CLI `--help` to work without API keys.
- REST API (api.py): Optional FastAPI server with dashboard. Install with `pip install -e ".[api]"`.
- Dashboard (static/index.html): Web UI served at `/` with status, tools list, and chat interface. Uses Tailwind CSS via CDN.
- Agent metadata (agent.py): `get_agent_info()` returns model, tools, and config for the `/info` endpoint.
- Branding (config.py): `AGENT_NAME` (default `PydanKit`) sets the API/Swagger title and is surfaced on the public `/health` payload; the dashboard reads it from `/health` to brand the header, browser tab, and System Status (so it shows pre-login).

**Streaming:**
- `/chat/stream` endpoint uses Server-Sent Events (SSE) for real-time streaming
- `run_agent_stream()` in agent.py uses `result.stream_text(delta=True)` and yields each new text chunk directly (the default output is plain text)
- Frontend uses `ReadableStream` API to consume SSE events in real-time
- **Wire format:** each delta is sent as `data: {json.dumps(chunk)}` (a JSON-encoded string), so chunks containing newlines stay one SSE line; the client buffers frames and `JSON.parse`s each payload. Keep both sides in sync — sending a raw chunk again would let a newline split the frame and the client would drop the continuation.
- The dashboard renders agent replies as **sanitized markdown** (`marked` + `DOMPurify` via CDN in `index.html`); `renderMarkdown()` in `dashboard.js` falls back to plain text if the libs fail to load. User messages stay literal text.
- Note: if you switch `output_type` to a structured model, `stream_text()` no longer applies — use `result.stream_output()` and derive your own deltas

**Testing:**
- `pytest` (in the `dev` extra); run with `make test`
- Tests use Pydantic AI's `TestModel` / `capture_run_messages`, so they run offline with no API key
- `tests/eval_example.py` is a runnable Pydantic Evals pattern (not collected by pytest) — copy it to build a real baseline

**API security defaults:**
- CORS defaults to a localhost allowlist via `CORS_ORIGINS` (not `*`). With auth on, `allow_credentials=True`, so `CORS_ORIGINS` must never be `*`.
- Interactive docs (`/docs`, `/redoc`, `/openapi.json`) are **off in production by default**: `DOCS_ENABLED` unset follows `DEBUG` (on in dev, off in prod); set it `true`/`false` to force. Resolved by `Settings.docs_ui_enabled`.
- Per-user authentication is **on by default** (`AUTH_ENABLED=true`); set it `false` to run open. See "Authentication" below.
- Legacy `API_KEY` gate: when `AUTH_ENABLED=false`, setting `API_KEY` still requires a matching `X-API-Key` header (now enforced inside `get_current_user`, `src/auth/dependencies.py`). When auth is on, per-user credentials replace it.

## Extending

**How and when to build on this template lives in [AGENTS.md](AGENTS.md)** — the
single source of truth (decision rules, definition of done, anti-patterns). Read
it before adding tools, changing the output type, or adding agents.

Quick reference for the mechanics:
- **Add a tool:** define an `async def` in `tools.py` with `RunContext[AgentDeps]`
  as the first param, then add it to the `TOOLS` list in `agent.py`.
- **Change output structure:** define a model in `models.py` and set `output_type=`
  in `get_agent()` (default is `str` — see AGENTS.md for when to do this).
- **Dynamic system prompt:**
  ```python
  @agent.instructions
  def dynamic_instructions(ctx: RunContext[AgentDeps]) -> str:
      return f"Context: {ctx.deps.user_id}"
  ```

## Important Implementation Details

**Streaming with Structured Outputs (only if you opt into `output_type`):**
The default output is `str`, so `run_agent_stream()` uses `result.stream_text(delta=True)`. If you change `output_type` to a structured model, plain-text streaming no longer applies and you must switch to `result.stream_output()`, which:
- Returns partial validated Pydantic objects as the response builds
- Supports debouncing via `debounce_by` parameter (default 0.05s)
- Each iteration yields the full object with fields filled as they become available
- Requires you to calculate deltas manually if you want to stream only new text

**Dashboard Static Assets:**
- Static files are in `src/static/` (next to `api.py`), not the project root
- `STATIC_DIR = Path(__file__).parent / "static"` in api.py — `api.py` lives in `src/`, so this resolves to `src/static/`
- Dashboard uses Tailwind CSS CDN (no build step required)
- Logo SVG files: `static/assets/logo.svg` (black) and `static/assets/logo-white.svg` (white for favicon)
- JavaScript: `static/js/dashboard.js` handles SSE streaming, theme toggle, and chat UI

**Error Handling in API:**
- `sanitize_error()` helper in api.py logs full errors but returns safe messages to clients
- In debug mode (`DEBUG=true`), full error details are returned
- In production, generic messages prevent information leakage

## Memory System

The template includes a built-in conversation memory system that keeps context across sessions.

**How It Works:**
- Uses Pydantic AI's native `message_history` parameter in `agent.run()`
- Automatically loads and saves conversation history for each session
- Enabled by default (opt-out via `MEMORY_ENABLED=false` or per-request flag)
- Stores the full turn (tool calls included) — do **not** filter tool messages; that corrupts history

**Backends:** `InMemoryStorage` (process-local — lost on restart, not shared across
workers) and the durable **`SqlMemoryStorage`** (`src/memory/sql_storage.py`) on the
`DATABASE_URL` engine (SQLite or Postgres). `MEMORY_STORAGE_TYPE` selects: **`auto`**
(default) uses `sql` when `DATABASE_URL` is set, else `memory`; `sql`/`memory` force it
(`sqlite` = legacy alias for `sql`), resolved by `Settings.effective_memory_backend`.
For other stores (Redis, etc.), implement `MemoryStorage` (see "Extending Storage").

**Key Components:**
- `MemoryManager` (memory/manager.py): Orchestrates history loading/saving
- `MemoryStorage` (memory/storage.py): Abstract interface for storage backends
- `InMemoryStorage`: Default implementation using dict
- `SessionMetadata`: Tracks session info (created_at, message_count, user_id)

**Session Management:**
- Each conversation has a `session_id` (unique identifier)
- Auto-session: If `user_id` provided without `session_id`, creates `session_id = f"user:{user_id}"`
- History is loaded before agent runs, saved after completion
- Context limits: Respects `MEMORY_MAX_MESSAGES` (default: 100)

**CLI Usage:**

```bash
# Interactive mode - auto-generates session_id and maintains context
python -m src.main interactive

# Chat with explicit session
python -m src.main chat "What's my name?" --session user:alice

# Disable memory for a request
python -m src.main chat "Hello" --no-memory

# List all sessions
python -m src.main sessions --list

# Clear a specific session
python -m src.main sessions --clear user:alice
```

**API Usage:**

```python
# Request with session_id (maintains context)
{
  "prompt": "My name is Alice",
  "user_id": "alice",
  "session_id": "user:alice",
  "memory_enabled": true  # default
}

# Auto-session by user_id (session_id = "user:alice")
{
  "prompt": "What's my name?",
  "user_id": "alice"
}

# Disable memory per-request
{
  "prompt": "Hello",
  "memory_enabled": false
}
```

**API Endpoints:**

```bash
# List sessions
GET /sessions
→ {"sessions": [{"session_id": "...", "message_count": 10, ...}]}

# Get session details
GET /sessions/{session_id}
→ {"session": {"session_id": "...", "created_at": "...", ...}}

# Clear session
DELETE /sessions/{session_id}
→ {"status": "cleared", "session_id": "..."}

# Memory stats
GET /memory/stats
→ {"enabled": true, "storage_type": "memory", "total_sessions": 5, ...}
```

**Configuration:**

```bash
# .env
MEMORY_ENABLED=true                    # Enable/disable memory (default: true)
MEMORY_MAX_MESSAGES=100                # Max messages per session
MEMORY_AUTO_SESSION=true               # Auto-generate session_id from user_id
```

**Disabling Memory:**

```bash
# Globally (in .env)
MEMORY_ENABLED=false

# Per-request (CLI)
python -m src.main chat "Hello" --no-memory

# Per-request (API)
{"prompt": "Hello", "memory_enabled": false}
```

**Extending Storage:**

Two backends ship: `InMemoryStorage` (default) and `SqlMemoryStorage`
(`MEMORY_STORAGE_TYPE=sql`, on the `DATABASE_URL` engine). To add another (e.g. Redis):
1. Implement the `MemoryStorage` interface (follow `sql_storage.py` as a model)
2. Select it in `get_memory_manager()` (memory/manager.py), imported lazily
3. Extend the `memory_storage_type` Literal in config.py / models.py

## Authentication

Per-user auth with SQLite. **On by default** — a fresh clone shows a login
screen, so create a user first (set `AUTH_ENABLED=false` to run open instead).

```bash
pip install -e ".[auth]"                        # aiosqlite + bcrypt (bundled with [api])

# Enable in .env: AUTH_ENABLED=true  (and DATABASE_PATH, SESSION_TTL_DAYS, ... as needed)
python -m src.main users --add alice --admin    # create the first admin (trusted CLI)
python -m src.main users --list
python -m src.main apikey --issue alice          # per-user API key for programs
```

- **One store, two doors:** an opaque token in an HttpOnly cookie (dashboard login)
  or an `Authorization: Bearer` / `X-API-Key` header (programs), resolved by
  `get_current_user` (`src/auth/dependencies.py`). Revoke = delete the row.
- **Isolation:** `user_id` is *not* in the request body; identity comes from the
  credential, and every data route scopes to the caller. The CLI is a trusted,
  unauthenticated admin shell **by design** — do not add a login to it.
- **Admin panel:** admins get
  `/admin/*` routes (behind `require_admin`, 404 when auth is off) and a dashboard panel
  to create **passwordless service accounts** and issue/list/revoke their API keys.
  UI-created accounts are **never admin**; admin accounts can't be managed from the UI.
- **Bootstrap without a shell:** set `ADMIN_USERNAME`/`ADMIN_PASSWORD` to env-seed the
  first admin on startup (FastAPI lifespan in `api.py`) when no admin exists.
- **Config:** `AUTH_ENABLED`, `DATABASE_PATH`, `SESSION_TTL_DAYS`,
  `SESSION_COOKIE_SECURE` (set true behind TLS), `LOGIN_MAX_ATTEMPTS`,
  `LOGIN_LOCKOUT_SECONDS`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`.
