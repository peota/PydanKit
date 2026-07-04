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


def _auth_store():
    """Load the auth store, or exit with a friendly hint if extras are missing."""
    try:
        from src.auth.dependencies import get_auth_store
    except ImportError:
        typer.echo("Auth extras not installed. Run: pip install -e '.[auth]'", err=True)
        raise typer.Exit(1)
    return get_auth_store()


def _read_password() -> str:
    """Prompt for a password on a TTY (hidden, confirmed); else read one line of stdin.

    The stdin fallback makes the command scriptable (Docker/CI bootstrap) without a
    ``--password`` flag that would leak into shell history and process listings.
    """
    if sys.stdin.isatty():
        return typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    password = sys.stdin.readline().strip()
    if not password:
        typer.echo("No password provided on stdin", err=True)
        raise typer.Exit(1)
    return password


@app.command()
def users(
    add: str | None = typer.Option(None, "--add", help="Create a user with this username"),
    admin: bool = typer.Option(False, "--admin", help="Grant admin rights (with --add)"),
    list_users: bool = typer.Option(False, "--list", "-l", help="List all users"),
    disable: str | None = typer.Option(None, "--disable", help="Disable a user by username"),
    enable: str | None = typer.Option(None, "--enable", help="Re-enable a user by username"),
) -> None:
    """Manage user accounts.

    The CLI is a trusted admin shell (ADR 0001): it needs no login. Use ``--add``
    to bootstrap the first admin on a fresh database.
    """
    from src.auth.db import InvalidUsernameError, UsernameTakenError

    store = _auth_store()

    if add:
        password = _read_password()
        try:
            user = asyncio.run(store.create_user(add, password, is_admin=admin))
        except UsernameTakenError:
            typer.echo(f"User already exists: {add}", err=True)
            raise typer.Exit(1)
        except InvalidUsernameError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(1)
        typer.echo(f"Created user '{user.username}'" + (" (admin)" if user.is_admin else ""))
        return

    if disable or enable:
        username = disable or enable
        user = asyncio.run(store.get_user_by_username(username))
        if user is None:
            typer.echo(f"No such user: {username}", err=True)
            raise typer.Exit(1)
        asyncio.run(store.set_disabled(user.id, disabled=bool(disable)))
        typer.echo(f"{'Disabled' if disable else 'Enabled'} user '{username}'")
        return

    if list_users:
        all_users = asyncio.run(store.list_users())
        if not all_users:
            typer.echo("No users. Create the first admin with: users --add <name> --admin")
            return
        typer.echo(f"\nFound {len(all_users)} user(s):\n")
        for u in all_users:
            flags = []
            if u.is_admin:
                flags.append("admin")
            if u.disabled:
                flags.append("disabled")
            suffix = f" [{', '.join(flags)}]" if flags else ""
            typer.echo(f"  {u.username}{suffix}")
        typer.echo()
        return

    typer.echo("Usage: users --add <name> [--admin] | --list | --disable <name> | --enable <name>")


@app.command()
def apikey(
    issue: str | None = typer.Option(None, "--issue", help="Issue an API key for this username"),
    name: str = typer.Option("cli", "--name", help="Label to record for the key"),
) -> None:
    """Issue a per-user API key for programmatic access (shown once)."""
    if not issue:
        typer.echo("Usage: apikey --issue <username>", err=True)
        raise typer.Exit(1)

    store = _auth_store()
    user = asyncio.run(store.get_user_by_username(issue))
    if user is None:
        typer.echo(f"No such user: {issue}", err=True)
        raise typer.Exit(1)

    key = asyncio.run(store.issue_token(user.id, "api_key", name=name))
    typer.echo(f"API key for '{issue}' (store it now - it will not be shown again):")
    typer.echo(key)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(
        8000, "--port", "-p", envvar="PORT", help="Port to bind to (reads $PORT if set)"
    ),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload for development"),
) -> None:
    """Start the FastAPI server (requires 'api' extras).

    Binds ``$PORT`` when set — cloud hosts (Railway, Cloud Run, ...) inject it — and
    falls back to ``--port``/8000 otherwise. Host defaults to 0.0.0.0 for containers.
    """
    try:
        import uvicorn
    except ImportError:
        typer.echo("FastAPI is not installed. Install it with: pip install -e '.[api]'", err=True)
        raise typer.Exit(1)

    typer.echo(f"Starting server at http://{host}:{port}")
    typer.echo(f"API docs available at http://{host}:{port}/docs")
    uvicorn.run("src.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
