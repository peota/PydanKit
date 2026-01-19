# PydanKit

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Pydantic AI](https://img.shields.io/badge/Pydantic%20AI-powered-green.svg)](https://ai.pydantic.dev/)

A minimal, well-structured infrastructure template for building AI Agents with [Pydantic AI](https://ai.pydantic.dev/).

## Features

- **Pydantic AI** - Type-safe agent framework with structured outputs
- **OpenAI GPT-4o** - Default LLM (easily switchable)
- **Logfire** - Built-in observability support
- **Typer CLI** - Command-line interface with interactive mode
- **FastAPI** - Optional REST API server with dashboard
- **Docker** - Container-ready deployment

## Quick Start

### Prerequisites

- Python 3.10+
- pip 21.3+ (for editable installs with pyproject.toml)

To upgrade pip if needed:
```bash
python -m pip install --upgrade pip
```

### 1. Install Dependencies

**Linux/macOS:**
```bash
make install-dev
```

**Windows (PowerShell):**
```powershell
pip install -e ".[dev]"
```

### 2. Configure Environment

**Linux/macOS:**
```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### 3. Run the Agent

**Linux/macOS:**
```bash
# Single prompt
make run

# Or with custom prompt
python -m src.main chat "What time is it?"

# Interactive mode
make interactive

# REST API with dashboard (requires: pip install -e ".[api]")
python -m src.main serve
# Open http://localhost:8000 in your browser
```

**Windows (PowerShell):**
```powershell
# Single prompt
python -m src.main chat "Hello, how can you help me?"

# Interactive mode
python -m src.main interactive

# REST API with dashboard (requires: pip install -e ".[api]")
python -m src.main serve
# Open http://localhost:8000 in your browser
```

## Project Structure

```
├── src/
│   ├── __init__.py
│   ├── main.py          # CLI entry point
│   ├── agent.py         # Agent definition
│   ├── api.py           # FastAPI server (optional)
│   ├── tools.py         # Tool definitions
│   ├── models.py        # Output models
│   ├── dependencies.py  # Dependency injection
│   ├── config.py        # Settings
│   └── static/          # Dashboard assets
│       ├── index.html
│       ├── assets/
│       └── js/
├── examples/
│   └── weather_agent/   # Example agent with API + dashboard
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── Makefile
```

## Customization Guide

### Adding a New Tool

Edit `src/tools.py`:

```python
from pydantic_ai import RunContext
from src.dependencies import AgentDeps

async def my_tool(ctx: RunContext[AgentDeps], param: str) -> str:
    """Tool description for the LLM to understand when to use it."""
    # Access dependencies via ctx.deps
    return f"Processed: {param}"
```

Register in `src/agent.py`:

```python
from src.tools import my_tool
agent.tool(my_tool)
```

### Adding Dependencies

Edit `src/dependencies.py`:

```python
from dataclasses import dataclass

@dataclass
class AgentDeps:
    user_id: str | None = None
    db: Database = None  # Add your dependencies
    api_client: APIClient = None
```

### Custom Output Models

Edit `src/models.py`:

```python
from pydantic import BaseModel
from typing import Literal

class AnalysisResponse(BaseModel):
    summary: str
    sentiment: Literal["positive", "negative", "neutral"]
    key_points: list[str]
```

Update agent in `src/agent.py`:

```python
agent = Agent(
    settings.model_name,
    deps_type=AgentDeps,
    output_type=AnalysisResponse,  # Use your model
)
```

### Dynamic System Prompt

```python
from pydantic_ai import RunContext

@agent.instructions
def dynamic_instructions(ctx: RunContext[AgentDeps]) -> str:
    return f"""You are helping user {ctx.deps.user_id}.
    Current context: {ctx.deps.metadata}
    """
```

### Switching LLM Provider

Update `.env`:

```bash
# For Anthropic Claude
MODEL_NAME=anthropic:claude-3-5-sonnet-latest

# For local Ollama
MODEL_NAME=ollama:llama3.2
```

## Commands

### Linux/macOS (Makefile)

| Command | Description |
|---------|-------------|
| `make install` | Install production dependencies |
| `make install-dev` | Install with dev dependencies |
| `make lint` | Run linter |
| `make format` | Format code |
| `make run` | Run with example prompt |
| `make interactive` | Start interactive mode |
| `make docker-build` | Build Docker image |
| `make docker-run` | Run with Docker Compose |

### Windows (PowerShell)

| Command | Description |
|---------|-------------|
| `pip install -e .` | Install production dependencies |
| `pip install -e ".[dev]"` | Install with dev dependencies |
| `ruff check src` | Run linter |
| `ruff format src` | Format code |
| `python -m src.main chat "Hello"` | Run with example prompt |
| `python -m src.main interactive` | Start interactive mode |
| `docker build -t pydantic-ai-agent .` | Build Docker image |
| `docker-compose up` | Run with Docker Compose |

## Docker

Build and run:

**Build the image:**
```bash
docker build -t pydantic-ai-agent .
```

**Run with .env file (recommended):**
```bash
# Single prompt
docker run --rm --env-file .env pydantic-ai-agent chat "Hello"

# Interactive mode
docker run -it --rm --env-file .env pydantic-ai-agent interactive
```

**Run with explicit environment variable:**

Linux/macOS:
```bash
docker run --rm -e OPENAI_API_KEY=$OPENAI_API_KEY pydantic-ai-agent chat "Hello"
```

Windows (PowerShell):
```powershell
docker run --rm -e OPENAI_API_KEY=$env:OPENAI_API_KEY pydantic-ai-agent chat "Hello"
```

**Using docker-compose:**
```bash
docker-compose run --rm agent chat "Hello"
```

## REST API (Optional)

The agent can be exposed as a REST API using FastAPI, including a web-based dashboard.

**Install API dependencies:**
```bash
pip install -e ".[api]"
```

**Start the server:**
```bash
python -m src.main serve
```

### Dashboard

The API server includes a dashboard at the root URL (`/`) that provides:

- **Status Panel**: Health status indicator with color coding, model name display
- **Configuration**: Debug mode and Logfire status
- **Tools List**: Dynamically loaded list of registered tools
- **Chat Interface**: Interactive chat to test the agent

Open `http://localhost:8000/` in your browser after starting the server.

**Options:**
```bash
python -m src.main serve --host 0.0.0.0 --port 8000 --reload
```

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Dashboard UI |
| GET | `/health` | Health check |
| GET | `/info` | Agent configuration and metadata |
| POST | `/chat` | Send a prompt to the agent |
| POST | `/chat/stream` | Send a prompt and receive streaming response (SSE) |
| GET | `/docs` | OpenAPI documentation |

**Example request:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello!", "user_id": "user-123"}'
```

### Streaming with Server-Sent Events (SSE)

The `/chat/stream` endpoint provides real-time streaming responses using Server-Sent Events.

**curl example:**
```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Tell me a story"}'
```

**JavaScript example:**
```javascript
async function streamChat(prompt) {
  const response = await fetch('http://localhost:8000/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const text = decoder.decode(value);
    const lines = text.split('\n');

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6);
        if (data === '[DONE]') {
          console.log('Stream complete');
        } else {
          console.log('Received:', data);
        }
      }
    }
  }
}
```

**Run with Docker:**
```bash
docker run --rm --env-file .env -p 8000:8000 pydantic-ai-agent serve --host 0.0.0.0
```

## Observability with Logfire

1. Get a token from [Logfire](https://logfire.pydantic.dev/)
2. Add to `.env`:
   ```
   LOGFIRE_TOKEN=your-token-here
   ```
3. View traces in the Logfire dashboard

## Troubleshooting

### "OPENAI_API_KEY not set" error
Ensure your `.env` file exists and contains a valid API key:
```bash
echo "OPENAI_API_KEY=sk-..." > .env
```

### "FastAPI is not installed" error
Install API dependencies:
```bash
pip install -e ".[api]"
```

### "pip install -e" fails on older pip
Upgrade pip to 21.3+:
```bash
python -m pip install --upgrade pip
```

### Agent returns empty or unexpected responses
1. Check your `MODEL_NAME` in `.env` is valid
2. Ensure your API key has access to the specified model
3. Try enabling debug mode: `DEBUG=true` in `.env`

### Streaming endpoint hangs or disconnects
1. Ensure your client supports SSE (Server-Sent Events)
2. Check for proxy/firewall issues that may buffer or timeout streams
3. Try the non-streaming `/chat` endpoint to verify the agent works

### Docker container can't access API key
Use `--env-file` or `-e` flags:
```bash
docker run --rm --env-file .env pydantic-ai-agent chat "Hello"
```

## Acknowledgments

Built with these excellent open-source projects:

- [Pydantic AI](https://ai.pydantic.dev/) - Type-safe AI agent framework
- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework for APIs
- [Typer](https://typer.tiangolo.com/) - CLI builder
- [Logfire](https://logfire.pydantic.dev/) - Observability platform

## License

MIT
