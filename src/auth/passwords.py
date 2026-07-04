"""Password hashing with bcrypt.

bcrypt operates on the first 72 bytes of its input and ignores the rest. We
truncate explicitly so a long passphrase can't create a false sense of extra
strength (and so hashing/verifying agree on the exact bytes).
"""

import bcrypt

# bcrypt's hard limit. Truncating on a byte boundary may split a multibyte UTF-8
# character, but bcrypt hashes bytes, so hashing and verification stay consistent.
_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    return password.encode("utf-8")[:_MAX_BYTES]


def hash_password(password: str) -> str:
    """Return a bcrypt hash suitable for storing in the users table."""
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode("utf-8"))
    except ValueError:
        # Malformed/blank hash on record — treat as a failed match, never raise.
        return False
