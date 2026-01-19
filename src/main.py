"""CLI entry point for the agent."""

import asyncio
import sys

import typer
from dotenv import load_dotenv

# Load .env file into environment (required for pydantic-ai's OpenAI client)
load_dotenv()

# Fix Windows asyncio event loop issue with ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.agent import run_agent  # noqa: E402
from src.dependencies import AgentDeps  # noqa: E402

app = typer.Typer(
    name="agent",
    help="Pydantic AI Agent CLI",
    add_completion=False,
)


@app.command()
def chat(
    prompt: str = typer.Argument(..., help="The prompt to send to the agent"),
    user_id: str | None = typer.Option(None, "--user", "-u", help="Optional user ID"),
) -> None:
    """Run the agent with a single prompt."""
    deps = AgentDeps(user_id=user_id)
    result = asyncio.run(run_agent(prompt, deps))
    typer.echo(f"\n{result.content}")
    if result.confidence is not None:
        typer.echo(f"\n(Confidence: {result.confidence:.0%})")


@app.command()
def interactive(
    user_id: str | None = typer.Option(None, "--user", "-u", help="Optional user ID"),
) -> None:
    """Start an interactive chat session."""
    deps = AgentDeps(user_id=user_id)
    typer.echo("Interactive mode started. Type 'exit' or 'quit' to end.\n")

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
            typer.echo(f"\nAgent: {result.content}\n")
        except Exception as e:
            typer.echo(f"\nError: {e}\n", err=True)


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
