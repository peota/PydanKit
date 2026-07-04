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


def _choose(label: str, options: list[tuple[str, str]], default: str | None = None) -> str:
    """Prompt the user to pick one numbered option; return the chosen option's key.

    Uses only Typer/click (no extra prompt dependency). ``options`` is a list of
    ``(key, description)`` pairs; ``default`` is the key selected on a bare Enter.
    """
    typer.echo(f"\n{label}")
    for i, (_key, desc) in enumerate(options, 1):
        typer.echo(f"  {i}. {desc}")
    keys = [k for k, _ in options]
    default_index = str(keys.index(default) + 1) if default in keys else "1"
    while True:
        raw = typer.prompt("Enter number", default=default_index)
        try:
            idx = int(raw)
        except ValueError:
            typer.echo("Please enter a number.", err=True)
            continue
        if 1 <= idx <= len(options):
            return keys[idx - 1]
        typer.echo(f"Please enter a number between 1 and {len(options)}.", err=True)


@app.command()
def init() -> None:
    """Interactively write a scenario-correct .env (a smart `cp .env.example .env`).

    Asks a few questions and writes every non-secret variable already correct for the
    deployment you're targeting. It never collects your API key (paste that into the
    one labelled slot yourself).
    """
    import shutil
    import subprocess
    from pathlib import Path

    from src.installer import (
        PROVIDERS,
        InstallerAnswers,
        build_env_content,
        env_is_gitignored,
        extra_install_command,
        required_extras,
    )

    project_root = Path.cwd()
    env_path = project_root / ".env"

    typer.echo("PydanKit setup - a few questions to write a correct .env for your setup.")

    # Step 0: never silently clobber an existing .env.
    if env_path.exists():
        action = _choose(
            f"A .env already exists at {env_path}. What should I do?",
            [
                ("backup", "Back it up to .env.bak, then write a new one"),
                ("overwrite", "Overwrite it (current contents are lost)"),
                ("abort", "Abort and leave it untouched"),
            ],
            default="backup",
        )
        if action == "abort":
            typer.echo("Aborted. Your .env was not changed.")
            raise typer.Exit(0)
        if action == "backup":
            shutil.copy2(env_path, project_root / ".env.bak")
            typer.echo("Backed up existing .env to .env.bak")

    agent_name = typer.prompt(
        "\nAgent name (branding shown on the dashboard and API title)", default="PydanKit"
    ).strip() or "PydanKit"

    run_mode = _choose(
        "How will you run the agent?",
        [
            ("cli", "CLI only (chat / interactive in the terminal)"),
            ("web", "Web dashboard + REST API (the `serve` command)"),
        ],
        default="cli",
    )
    provider = _choose(
        "Which model provider?",
        [(key, prov["label"]) for key, prov in PROVIDERS.items()],
        default="openai",
    )
    persistence = _choose(
        "Where should users, tokens and memory live?",
        [
            ("local", "Local SQLite file (zero-config, durable on this machine)"),
            ("postgres", "Postgres (cloud / multi-instance; I'll leave a placeholder)"),
        ],
        default="local",
    )
    auth = _choose(
        "Who can use the API?",
        [
            ("open", "Just me - no login (open API)"),
            ("multi", "Multiple users - require login"),
        ],
        default="open",
    )

    answers = InstallerAnswers(
        run_mode=run_mode,
        provider=provider,
        persistence=persistence,
        auth=auth,
        agent_name=agent_name,
    )

    # Step 4a: seed the first admin, but only for a multi-user web dashboard - and never
    # write a password into a .env that git could commit.
    if answers.needs_admin_seed:
        if not env_is_gitignored(project_root):
            typer.echo(
                "Refusing to write an admin password: .env is not covered by .gitignore.\n"
                "Add a `.env` line to .gitignore and re-run, or choose open mode.",
                err=True,
            )
            raise typer.Exit(1)
        typer.echo("\nCreate the first admin (needed to log in to the dashboard).")
        answers.admin_username = typer.prompt("Admin username")
        answers.admin_password = _read_password()

    env_path.write_text(build_env_content(answers), encoding="utf-8")
    typer.echo(f"\nWrote {env_path}")

    # Validate the file binds (parses and types check). It does NOT prove the key works -
    # we never see the key - so a clean bind is the honest definition of "done" here.
    try:
        from src.config import Settings

        Settings(_env_file=str(env_path))  # type: ignore[call-arg]
    except Exception as e:  # pragma: no cover - defensive
        typer.echo(f"Warning: the generated .env did not validate cleanly: {e}", err=True)

    # Step 5: some scenarios need extras beyond the base install (API server, DB driver).
    # Offer to install exactly the ones this choice needs and that aren't present yet -
    # never install silently. Adapt to pip vs uv (uv venvs ship without pip).
    import importlib.util
    import shutil

    has_pip = importlib.util.find_spec("pip") is not None
    has_uv = shutil.which("uv") is not None

    for extra, probe in required_extras(answers):
        if importlib.util.find_spec(probe) is not None:
            continue  # already installed
        argv, hint = extra_install_command(
            extra, python_executable=sys.executable, has_pip=has_pip, has_uv=has_uv
        )
        if argv is None:
            typer.echo(f"\nThis setup needs the [{extra}] extra. Install it with:  {hint}")
            continue
        if typer.confirm(
            f"\nThis setup needs the [{extra}] extra, which isn't installed. Install it now?",
            default=True,
        ):
            typer.echo(f"Installing ({hint}) ...")
            result = subprocess.run(argv, check=False)
            if result.returncode != 0:
                typer.echo(f"Install failed. Run it yourself when ready:  {hint}", err=True)
        else:
            typer.echo(f"Skipped. Install later with:  {hint}")

    prov = PROVIDERS[provider]
    typer.echo("\nDone. Next steps:")
    typer.echo(f"  1. Open .env and paste your {prov['label']} API key after {prov['key_var']}=")
    if answers.needs_admin_seed:
        typer.echo("  2. Rotate or clear ADMIN_PASSWORD in .env after your first login.")
    if answers.web:
        typer.echo("  -> Start the server:  python -m src.main serve")
    else:
        typer.echo('  -> Try it:  python -m src.main chat "Hello"')
    typer.echo(
        "\nNote: I can't verify your key or model access here. If the first call fails, "
        "check the key is valid and the model is available to your account."
    )


@app.command()
def users(
    add: str | None = typer.Option(None, "--add", help="Create a user with this username"),
    admin: bool = typer.Option(False, "--admin", help="Grant admin rights (with --add)"),
    list_users: bool = typer.Option(False, "--list", "-l", help="List all users"),
    disable: str | None = typer.Option(None, "--disable", help="Disable a user by username"),
    enable: str | None = typer.Option(None, "--enable", help="Re-enable a user by username"),
) -> None:
    """Manage user accounts.

    The CLI is a trusted admin shell: it needs no login. Use ``--add``
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
    if get_settings().docs_ui_enabled:
        typer.echo(f"API docs available at http://{host}:{port}/docs")
    uvicorn.run("src.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
