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

This is a Pydantic AI agent template with dependency injection and structured outputs.

**Data flow:** `main.py` (CLI) or `api.py` (REST) → `agent.py` (orchestration) → `tools.py` (actions)

**Key patterns:**
- `AgentDeps` (dependencies.py): Dataclass injected into all tool calls via `RunContext[AgentDeps]`. Add DB connections, API clients, or user context here.
- `AgentResponse` (models.py): Pydantic model for structured LLM output. The agent is constrained to return this shape.
- Tools (tools.py): Async functions registered with `agent.tool()`. First param is always `ctx: RunContext[AgentDeps]`.
- Settings (config.py): Environment-based config via pydantic-settings, loaded from `.env`.
- Lazy initialization (agent.py): Agent created via `get_agent()` on first use, not at import time. This allows CLI `--help` to work without API keys.
- REST API (api.py): Optional FastAPI server with dashboard. Install with `pip install -e ".[api]"`.
- Dashboard (static/index.html): Web UI served at `/` with status, tools list, and chat interface. Uses Tailwind CSS via CDN.
- Agent metadata (agent.py): `get_agent_info()` returns model, tools, and config for the `/info` endpoint.

**Streaming:**
- `/chat/stream` endpoint uses Server-Sent Events (SSE) for real-time streaming
- `run_agent_stream()` in agent.py uses `result.stream_output()` (not `stream_text()`) because the agent has a structured `output_type`
- The function calculates deltas to send only new text chunks to the client
- Frontend uses `ReadableStream` API to consume SSE events in real-time

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

**Streaming with Structured Outputs:**
When the agent has a structured `output_type` (like `AgentResponse`), you must use `result.stream_output()` instead of `result.stream_text()`. The `stream_output()` method:
- Returns partial validated Pydantic objects as the response builds
- Supports debouncing via `debounce_by` parameter (default 0.05s)
- Each iteration yields the full object with fields filled as they become available
- You must calculate deltas manually if you want to stream only new text

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
- In-memory storage by default (can be extended to file/Redis)

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

**Memory Tools:**

The agent has access to explicit memory tools:
- `save_fact(key, value)`: Save a fact for later retrieval (e.g., "favorite_color", "birthday")
- `retrieve_facts()`: Retrieve all saved facts

These tools complement automatic conversation history by allowing the agent to save specific information that should persist across sessions.

**Configuration:**

```bash
# .env
MEMORY_ENABLED=true                    # Enable/disable memory (default: true)
MEMORY_STORAGE_TYPE=memory             # Storage backend: memory, file, redis
MEMORY_MAX_MESSAGES=100                # Max messages per session
MEMORY_MAX_TOKENS=                     # Optional token limit (rough estimate)
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

To add file or Redis storage:
1. Implement `MemoryStorage` interface in `memory/storage.py`
2. Update `get_memory_manager()` in `memory/manager.py` to create the new backend
3. Set `MEMORY_STORAGE_TYPE=file` or `redis` in `.env`
