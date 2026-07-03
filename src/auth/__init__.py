"""Authentication package (ADR 0001).

Opt-in per-user auth backed by SQLite. Only imported when AUTH_ENABLED=true or
memory_storage_type="sqlite"; requires the ``[auth]`` extra (aiosqlite, bcrypt).
"""
