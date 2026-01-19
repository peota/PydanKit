"""CLI entry point for the weather agent example."""

import asyncio

import typer
from dotenv import load_dotenv

# Load .env file into environment (required for pydantic-ai's OpenAI client)
load_dotenv()

from .agent import run_weather_agent  # noqa: E402
from .dependencies import WeatherDeps  # noqa: E402

app = typer.Typer(help="Weather Agent - A PydanKit example")


@app.command()
def chat(prompt: str = typer.Argument(..., help="Your weather question")):
    """Ask the weather agent a question."""
    asyncio.run(_run_chat(prompt))


@app.command()
def interactive():
    """Start an interactive weather chat session."""
    asyncio.run(_run_interactive())


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    port: int = typer.Option(8001, help="Port to bind to"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
):
    """Start the FastAPI server with dashboard."""
    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn not installed. Run: pip install uvicorn")
        raise typer.Exit(1)

    print(f"Starting Weather Agent API at http://{host}:{port}")
    print("Dashboard available at the root URL")
    uvicorn.run(
        "examples.weather_agent.api:app",
        host=host,
        port=port,
        reload=reload,
    )


async def _run_chat(prompt: str) -> None:
    """Run a single weather query."""
    deps = WeatherDeps()
    try:
        result = await run_weather_agent(prompt, deps)
        print(f"\nLocation: {result.location}")
        print(f"Temperature: {result.temperature}{result.temperature_unit}")
        print(f"Conditions: {result.conditions}")
        if result.humidity is not None:
            print(f"Humidity: {result.humidity}%")
        if result.wind_speed is not None:
            print(f"Wind: {result.wind_speed} km/h")
        print(f"\n{result.summary}")
    finally:
        await deps.close()


async def _run_interactive() -> None:
    """Run interactive weather chat session."""
    deps = WeatherDeps()
    print("Weather Agent Interactive Mode")
    print("Type 'quit' or 'exit' to end the session\n")

    try:
        while True:
            try:
                prompt = input("You: ").strip()
            except EOFError:
                break

            if not prompt:
                continue
            if prompt.lower() in ("quit", "exit"):
                print("Goodbye!")
                break

            try:
                result = await run_weather_agent(prompt, deps)
                print(f"\nWeather: {result.summary}\n")
            except Exception as e:
                print(f"Error: {e}\n")
    finally:
        await deps.close()


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
