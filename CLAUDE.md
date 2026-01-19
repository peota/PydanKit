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
