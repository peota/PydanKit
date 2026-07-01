.PHONY: install install-dev lint format test run interactive clean docker-build docker-run

# Install production dependencies
install:
	pip install -e .

# Install with development dependencies
install-dev:
	pip install -e ".[dev]"

# Run linter
lint:
	ruff check src

# Format code
format:
	ruff format src
	ruff check --fix src

# Run tests (no API key needed; uses Pydantic AI's TestModel)
test:
	pytest

# Run agent with a prompt
run:
	python -m src.main chat "Hello, how can you help me?"

# Run interactive mode
interactive:
	python -m src.main interactive

# Clean build artifacts
clean:
	rm -rf build dist *.egg-info __pycache__ .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Build Docker image
docker-build:
	docker build -t pydantic-ai-agent .

# Run with Docker Compose
docker-run:
	docker-compose up
