# PydanKit

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Pydantic AI](https://img.shields.io/badge/Pydantic%20AI-powered-green.svg)](https://ai.pydantic.dev/)

A production-ready template for building AI agents with [Pydantic AI](https://ai.pydantic.dev/). Get started in minutes with conversation memory, structured outputs, and an optional REST API.

## ✨ Features

- 🤖 **Type-safe agents** with Pydantic AI
- 💬 **Built-in memory** - conversations remember context across sessions
- 🎯 **Interactive setup wizard** - customize for your use case with `/setup-agent`
- 🚀 **FastAPI dashboard** - web UI and REST API (optional)
- 🔌 **Tool framework** - easy to add custom capabilities
- 📊 **Observability** - Logfire integration included
- 🐳 **Docker ready** - deploy anywhere

## 🚀 Quick Start

### 1. Setup

```bash
# Clone and install
pip install -e ".[dev]"

# Add your OpenAI API key
cp .env.example .env
# Edit .env and add: OPENAI_API_KEY=sk-...
```

### 2. Try it out

```bash
# Single question
python -m src.main chat "What can you help me with?"

# Interactive mode (with memory!)
python -m src.main interactive

# Web dashboard
pip install -e ".[api]"
python -m src.main serve
# Open http://localhost:8000
```

That's it! The agent remembers your conversations automatically.

## 🎨 Customize Your Agent

### Using the Setup Wizard (Recommended)

If you're using [Claude Code](https://claude.ai/code):

```bash
/setup-agent
```

The wizard helps you customize with pre-built templates:
- 🏥 Health Monitoring - monitor services/APIs
- 📊 Data Processing - validate and transform data
- 🔗 API Integration - connect multiple services
- 📝 Report Generation - create insights from data

### Manual Customization

**Add a tool** (`src/tools.py`):
```python
async def my_tool(ctx: RunContext[AgentDeps], query: str) -> str:
    """Describe what this tool does."""
    return f"Result for {query}"
```

**Register it** (`src/agent.py`):
```python
agent.tool(my_tool)
```

**Change output format** (`src/models.py`):
```python
class MyResponse(BaseModel):
    answer: str
    confidence: float
    sources: list[str]
```

See [CLAUDE.md](CLAUDE.md) for complete customization guide.

## 💬 Memory System

Memory is enabled by default - your agent automatically remembers conversations.

```bash
# Interactive mode creates a session automatically
python -m src.main interactive
> My name is Alice
> What's my name?  # Agent remembers!

# Manage sessions
python -m src.main sessions --list
python -m src.main sessions --clear session-id
```

**Configure in `.env`:**
```bash
MEMORY_ENABLED=true          # Default: true
MEMORY_MAX_MESSAGES=100      # Keep last N messages
```

**API usage:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello!", "user_id": "alice"}'
```

Sessions are automatically created per `user_id`. See [CLAUDE.md](CLAUDE.md) for advanced memory features.

## 🌐 REST API & Dashboard

```bash
# Install API extras
pip install -e ".[api]"

# Start server
python -m src.main serve

# Open dashboard
open http://localhost:8000
```

**Key endpoints:**
- `POST /chat` - Send a message
- `POST /chat/stream` - Streaming responses (SSE)
- `GET /sessions` - List conversation sessions
- `GET /docs` - Full API documentation

## 📁 Project Structure

```
src/
├── agent.py         # Agent configuration
├── tools.py         # Your custom tools
├── models.py        # Output schemas
├── config.py        # Settings
├── memory/          # Memory system
└── api.py           # REST API (optional)

.claude/
└── skills/
    └── setup-agent/ # Interactive wizard
```

## 🔧 Common Tasks

**Switch LLM provider** (`.env`):
```bash
# Anthropic Claude
MODEL_NAME=anthropic:claude-3-5-sonnet-latest

# Local Ollama
MODEL_NAME=ollama:llama3.2
```

**Add dependencies** (`src/dependencies.py`):
```python
@dataclass
class AgentDeps:
    user_id: str | None = None
    db: Database = None  # Add your services here
```

**Enable observability** (`.env`):
```bash
LOGFIRE_TOKEN=your-token-from-logfire.dev
```

## 🐳 Docker

```bash
# Build
docker build -t my-agent .

# Run
docker run --env-file .env my-agent chat "Hello"

# API server
docker run --env-file .env -p 8000:8000 my-agent serve --host 0.0.0.0
```

## 📚 Documentation

- **[CLAUDE.md](CLAUDE.md)** - Complete development guide, architecture, streaming details
- **[Examples](examples/)** - Sample agents with different configurations
- **[Pydantic AI Docs](https://ai.pydantic.dev/)** - Framework documentation

## 🤝 Contributing

This is a template - customize it for your needs! Some ideas:

- Add more pre-built agent templates to the wizard
- Implement file/Redis storage backends for memory
- Create example integrations (Slack, Discord, etc.)
- Add more sophisticated tools

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

Built with:
- [Pydantic AI](https://ai.pydantic.dev/) - Agent framework
- [FastAPI](https://fastapi.tiangolo.com/) - Web API
- [Typer](https://typer.tiangolo.com/) - CLI
- [Logfire](https://logfire.pydantic.dev/) - Observability

---

**Need help?** Check [CLAUDE.md](CLAUDE.md) for detailed guides or open an issue.
