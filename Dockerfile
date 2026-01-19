# Multi-stage build for Python application
FROM python:3.10-slim AS builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir build

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/
COPY static/ static/

# Build wheel
RUN python -m build --wheel


# Production image
FROM python:3.10-slim AS production

WORKDIR /app

# Create non-root user
RUN useradd --create-home --shell /bin/bash agent

# Copy built wheel from builder
COPY --from=builder /app/dist/*.whl /tmp/

# Install the application with API extras
RUN pip install --no-cache-dir /tmp/*.whl fastapi "uvicorn[standard]" && \
    rm /tmp/*.whl

# Copy static files from builder
COPY --from=builder /app/static/ /app/static/

# Switch to non-root user
USER agent

# Default command
ENTRYPOINT ["python", "-m", "src.main"]
CMD ["--help"]
