# PydanKit

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Pydantic AI](https://img.shields.io/badge/Pydantic%20AI-powered-green.svg)](https://ai.pydantic.dev/)

A minimal, well-structured skeleton for building AI agents with [Pydantic AI](https://ai.pydantic.dev/). Returns plain text by default (structured output is an opt-in example), with conversation memory and an optional REST API. Bring your own opinions.

## ✨ Features

- 🤖 **Type-safe agents** with Pydantic AI (plain-text output by default; structured output opt-in)
- 💬 **Conversation memory** - in-memory by default, or durable SQLite (shared across workers)
- 🔐 **Authentication** - optional per-user auth with data isolation (SQLite; login + API keys)
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

**Authentication is on by default.** The dashboard shows a login screen, so create
an account before signing in (the login page also shows this command):

```bash
python -m src.main users --add <name> --admin   # you'll be prompted for a password
```

Prefer to run open (no login)? Set `AUTH_ENABLED=false` in `.env`. See
[Authentication](#-authentication) below.

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

**API usage** (with auth enabled, pass a per-user API key — identity comes from the
credential, not the request body):
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <key from: python -m src.main apikey --issue alice>" \
  -d '{"prompt": "Hello!"}'
```

With `AUTH_ENABLED=false`, drop the key and pass a `session_id` for continuity.
Each authenticated user gets their own session. See [CLAUDE.md](CLAUDE.md) for advanced memory features.

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

## 🔐 Authentication

Per-user auth with a local SQLite store ([ADR 0001](docs/adr/0001-authentication.md)).
Humans sign in on the dashboard (HttpOnly session cookie); programs send a per-user
API key. Each user only sees their own conversations.

**Create the first user** (there is no self-signup — accounts are admin-created):

```bash
python -m src.main users --add alice --admin   # prompts for a password
python -m src.main users --list
python -m src.main users --disable alice        # or --enable
python -m src.main apikey --issue alice          # per-user API key (shown once)
```

The CLI is a trusted admin shell — it needs no login. Use it to bootstrap the first
account, then sign in on the dashboard.

**Admin panel (no shell needed in prod).** Signed-in admins get a **Manage users & keys**
panel in the dashboard ([ADR 0002](docs/adr/0002-admin-ui-service-accounts.md)) to
create **service accounts** (passwordless, API-only) and issue/list/revoke their API
keys — so you can provision credentials on a cloud host without CLI access. Admin
rights are never granted from the UI (only via env-seed/CLI).

**Bootstrap without a shell.** For cloud deploys where the CLI isn't reachable, seed
the first admin from the environment — created on startup if no admin exists:
```bash
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me-then-rotate
```

**Configure in `.env`:**
```bash
AUTH_ENABLED=true              # default: true. Set false to run open (no login)
DATABASE_PATH=pydankit.db      # users, tokens, and (optional) durable memory
SESSION_TTL_DAYS=7             # dashboard session lifetime (sliding)
SESSION_COOKIE_SECURE=false    # set true when served over HTTPS
LOGIN_MAX_ATTEMPTS=5           # brute-force lockout threshold (per username)
ADMIN_USERNAME=               # optional: env-seed the first admin on boot
ADMIN_PASSWORD=               # (rotate/clear after first login)
```

> **Note:** the CLI `chat`/`interactive` commands run locally and are **not**
> authenticated by design (whoever runs them owns the box). Auth protects the API.

## 📁 Project Structure

```
src/
├── agent.py         # Agent configuration
├── tools.py         # Your custom tools
├── models.py        # Output schemas
├── config.py        # Settings
├── memory/          # Memory system (in-memory + SQLite backends)
├── auth/            # Authentication (users, tokens, resolver)
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
