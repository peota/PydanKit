# Multi-stage build for Python application
FROM python:3.10-slim AS builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir build

# Copy project files (static assets live under src/ and are bundled into the wheel)
COPY pyproject.toml README.md ./
COPY src/ src/

# Build wheel
RUN python -m build --wheel


# Production image
FROM python:3.10-slim AS production

WORKDIR /app

# Create non-root user
RUN useradd --create-home --shell /bin/bash agent

# Copy built wheel from builder
COPY --from=builder /app/dist/*.whl /tmp/

# Install the app + its API/auth runtime deps. Auth is ON by default and api.py
# imports the SQLAlchemy-backed store at load time, so SQLAlchemy + aiosqlite + bcrypt
# must be present or `serve` crashes on import. asyncpg ships too so a Postgres
# DATABASE_URL works out of the box. Bounds mirror the [api] + [postgres] extras.
RUN pip install --no-cache-dir /tmp/*.whl fastapi "uvicorn[standard]" \
    "sqlalchemy[asyncio]>=2.0,<3.0" "aiosqlite>=0.19,<1.0" "bcrypt>=4.0,<5.0" \
    "asyncpg>=0.29,<1.0" && \
    rm /tmp/*.whl

# Switch to non-root user
USER agent

# Default to serving the API + dashboard: cloud hosts run the bare image and expect
# an HTTP server. `serve` reads $PORT (injected by Railway/Cloud Run/...) and binds
# 0.0.0.0. Override for other modes, e.g. `docker run <img> chat "hi"` or `interactive`.
ENTRYPOINT ["python", "-m", "src.main"]
CMD ["serve"]
