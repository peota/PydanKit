# PydanKit

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Pydantic AI](https://img.shields.io/badge/Pydantic%20AI-powered-green.svg)](https://ai.pydantic.dev/)

A minimal, well-structured skeleton for building AI agents with [Pydantic AI](https://ai.pydantic.dev/). Returns plain text by default (structured output is an opt-in example), with conversation memory and an optional REST API. Bring your own opinions.

## ✨ Features

- 🤖 **Type-safe agents** with Pydantic AI (plain-text output by default; structured output opt-in)
- 💬 **Conversation memory** - context within a run (in-memory; ephemeral, lost on restart)
- 🎯 **Interactive setup wizard** - customize for your use case with `/setup-agent`
- 🚀 **FastAPI dashboard** - web UI and REST API (optional)
- 🔌 **Tool framework** - easy to add custom capabilities
- 🧪 **Tests + evals** - offline `TestModel` tests and a Pydantic Evals example (`make test`)
- 📊 **Observability** - Logfire integration included
- 🐳 **Docker ready** - deploy anywhere

## 🚀 Quick Start

### 1. Setup

```bash
# Clone and install
pip install -e ".[dev]"

# Add your provider API key (any provider works)
cp .env.example .env
# Edit .env: set MODEL_NAME and the matching key, e.g.
#   MODEL_NAME=openai:gpt-4o     + OPENAI_API_KEY=sk-...
#   MODEL_NAME=anthropic:claude-sonnet-4-5 + ANTHROPIC_API_KEY=...
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

**Switch LLM provider** (`.env`) — provider-agnostic; set `MODEL_NAME` and that provider's key:
```bash
# OpenAI          -> OPENAI_API_KEY
MODEL_NAME=openai:gpt-4o
# Anthropic Claude -> ANTHROPIC_API_KEY
MODEL_NAME=anthropic:claude-sonnet-4-5
# Groq            -> GROQ_API_KEY
MODEL_NAME=groq:llama-3.3-70b-versatile
# DeepSeek        -> DEEPSEEK_API_KEY
MODEL_NAME=deepseek:deepseek-chat
# Google Gemini   -> GEMINI_API_KEY
MODEL_NAME=google:gemini-2.0-flash
```
All provider SDKs ship with the `pydantic-ai` dependency, so no extra install is needed to switch.

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

- **[AGENTS.md](AGENTS.md)** - How to build agents on PydanKit (decision rules + definition of done); read by coding agents like Claude Code, Cursor, Copilot
- **[CLAUDE.md](CLAUDE.md)** - Architecture, streaming details, file layout
- **[tests/eval_example.py](tests/eval_example.py)** - Runnable Pydantic Evals pattern to copy
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
