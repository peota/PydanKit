"""Opaque token generation and hashing.

Session cookies and per-user API keys are the same primitive: a high-entropy
random string handed to the client, stored only as its SHA-256 hash. Because the
value is high-entropy, a fast hash is sufficient (unlike passwords, which need
bcrypt). We never store the plaintext, so a DB leak doesn't expose live tokens.
"""

import hashlib
import secrets

# 32 bytes -> 256 bits of entropy, url-safe base64 (~43 chars).
_TOKEN_BYTES = 32


def generate_token() -> str:
    """Return a fresh, url-safe opaque token to hand to a client."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest stored in the tokens table."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
