"""CLI entry point for the agent."""

import asyncio
import sys
from datetime import datetime
from uuid import uuid4

import typer
from dotenv import load_dotenv

# Load .env file into environment (required for pydantic-ai's OpenAI client)
load_dotenv()

# Fix Windows asyncio event loop issue with ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.agent import run_agent  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.dependencies import AgentDeps  # noqa: E402
from src.memory.manager import get_memory_manager  # noqa: E402

app = typer.Typer(
    name="agent",
    help="Pydantic AI Agent CLI",
    add_completion=False,
)


@app.command()
def chat(
    prompt: str = typer.Argument(..., help="The prompt to send to the agent"),
    user_id: str | None = typer.Option(None, "--user", "-u", help="Optional user ID"),
    session: str | None = typer.Option(
        None, "--session", "-s", help="Session ID for conversation context"
    ),
    no_memory: bool = typer.Option(False, "--no-memory", help="Disable memory for this request"),
) -> None:
    """Run the agent with a single prompt."""
    deps = AgentDeps(user_id=user_id, session_id=session, memory_enabled=not no_memory)
    result = asyncio.run(run_agent(prompt, deps))
    typer.echo(f"\n{result}")


@app.command()
def interactive(
    user_id: str | None = typer.Option(None, "--user", "-u", help="Optional user ID"),
    session: str | None = typer.Option(
        None, "--session", "-s", help="Session ID (auto-generated if not provided)"
    ),
) -> None:
    """Start an interactive chat session with in-session memory (lost on exit)."""
    # Auto-generate session_id if not provided
    if session is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        session = f"interactive-{timestamp}-{uuid4().hex[:8]}"

    deps = AgentDeps(user_id=user_id, session_id=session, memory_enabled=True)

    typer.echo(f"Interactive mode started (session: {session})")
    typer.echo("Type 'exit' or 'quit' to end.\n")

    while True:
        try:
            prompt = typer.prompt("You")
        except (KeyboardInterrupt, EOFError):
            typer.echo("\nGoodbye!")
            break

        if prompt.lower() in ("exit", "quit", "q"):
            typer.echo("Goodbye!")
            break

        try:
            result = asyncio.run(run_agent(prompt, deps))
            typer.echo(f"\nAgent: {result}\n")
        except Exception as e:
            typer.echo(f"\nError: {e}\n", err=True)


@app.command()
def sessions(
    list_sessions: bool = typer.Option(False, "--list", "-l", help="List all sessions"),
    clear: str | None = typer.Option(None, "--clear", "-c", help="Clear a specific session"),
) -> None:
    """Manage conversation sessions."""
    settings = get_settings()

    if not settings.memory_enabled:
        typer.echo("Memory is disabled. Enable it with MEMORY_ENABLED=true in .env", err=True)
        raise typer.Exit(1)

    memory_manager = get_memory_manager()

    if clear:
        # Clear specific session
        asyncio.run(memory_manager.clear_session(clear))
        typer.echo(f"Cleared session: {clear}")
        return

    if list_sessions:
        # List all sessions
        session_list = asyncio.run(memory_manager.list_sessions())
        if not session_list:
            typer.echo("No sessions found.")
            return

        typer.echo(f"\nFound {len(session_list)} session(s):\n")
        for session in session_list:
            typer.echo(f"  Session ID: {session.session_id}")
            typer.echo(f"    Messages: {session.message_count}")
            typer.echo(f"    Updated: {session.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
            if session.user_id:
                typer.echo(f"    User ID: {session.user_id}")
            typer.echo()
        return

    # If no flags provided, show help
    typer.echo("Usage: sessions --list | --clear <session_id>")
    typer.echo("Use --help for more information.")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload for development"),
) -> None:
    """Start the FastAPI server (requires 'api' extras)."""
    try:
        import uvicorn
    except ImportError:
        typer.echo("FastAPI is not installed. Install it with: pip install -e '.[api]'", err=True)
        raise typer.Exit(1)

    typer.echo(f"Starting server at http://{host}:{port}")
    typer.echo("API docs available at http://{host}:{port}/docs")
    uvicorn.run("src.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
