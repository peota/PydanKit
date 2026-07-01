# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

# Run agent
python -m src.main chat "Your prompt here"
python -m src.main interactive

# Install and run API server (optional)
pip install -e ".[api]"
python -m src.main serve --port 8000
# Dashboard available at http://localhost:8000/

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

**Streaming:**
- `/chat/stream` endpoint uses Server-Sent Events (SSE) for real-time streaming
- `run_agent_stream()` in agent.py uses `result.stream_text(delta=True)` and yields each new text chunk directly (the default output is plain text)
- Frontend uses `ReadableStream` API to consume SSE events in real-time
- Note: if you switch `output_type` to a structured model, `stream_text()` no longer applies — use `result.stream_output()` and derive your own deltas

**Testing:**
- `pytest` (in the `dev` extra); run with `make test`
- Tests use Pydantic AI's `TestModel` / `capture_run_messages`, so they run offline with no API key
- `tests/eval_example.py` is a runnable Pydantic Evals pattern (not collected by pytest) — copy it to build a real baseline

**API security defaults:**
- CORS defaults to a localhost allowlist via `CORS_ORIGINS` (not `*`)
- Optional API-key gate: set `API_KEY` to require an `X-API-Key` header on protected endpoints (`require_api_key` in api.py) — a seam, not full auth

## Extending

Add a tool:
1. Define async function in `tools.py` with `RunContext[AgentDeps]` as first param
2. Register with `agent.tool(my_tool)` in `agent.py`

Change output structure:
1. Define new Pydantic model in `models.py`
2. Update `output_type=` in agent definition

Dynamic system prompt:
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
- Static files are in `static/` at the project root (not `src/static/`)
- `STATIC_DIR = Path(__file__).parent / "static"` in api.py
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

**Limitation:** the only backend that ships is in-memory (`InMemoryStorage`). History is
**process-local and lost on restart**, and is **not shared across API worker processes**.
For durable memory, implement the `MemoryStorage` interface (see "Extending Storage").

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

No durable backend ships today (in-memory only). To add file or Redis storage:
1. Implement the `MemoryStorage` interface in `memory/storage.py`
2. Instantiate your backend in `get_memory_manager()` (memory/manager.py)
3. Add a config knob to select it, and update the `memory_storage_type` Literal in config.py / models.py
