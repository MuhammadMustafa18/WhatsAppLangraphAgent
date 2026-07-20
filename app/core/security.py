"""Security utilities — password hashing, JWT tokens, encryption.

Phase 6: password hashing.
Phase 7: JWT tokens.
Phase 12: Fernet encryption for at-rest secrets (Provider.api_key, etc.).
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- Password hashing ---

def hash_password(password: str) -> str:
    """Hash a plain-text password. Returns bcrypt hash."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return pwd_context.verify(plain, hashed)


# --- JWT tokens ---

ALGORITHM = "HS256"


def create_access_token(user_id: str) -> str:
    """Create a short-lived access token (default 15 min)."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived refresh token (default 7 days)."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    payload = {"sub": user_id, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Decode and validate a JWT. Returns payload dict or None if invalid."""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return None


# --- At-rest encryption (Fernet) ---
#
# Used for secrets stored in the database: Provider.api_key, Connection.config
# secrets, etc. Protects against someone copying data/app.sqlite and reading
# it offline. Does NOT protect against an attacker running this app — at
# runtime the key is in memory and the app decrypts everything it reads.
#
# Key lifecycle:
#   - On first encrypt_value() call, if ENCRYPTION_KEY is empty we generate
#     a fresh Fernet key, persist it to .env, and use it.
#   - The .env file is what we're using for ALL config; the key lives there
#     alongside JWT_SECRET. Treat .env as a secret.
#   - Rotation is intentionally out of scope (single key per deployment).

def _load_or_create_key() -> bytes:
    """Return the Fernet key, generating + persisting one if absent."""
    settings = get_settings()
    if settings.ENCRYPTION_KEY:
        return settings.ENCRYPTION_KEY.encode()

    new_key = Fernet.generate_key()
    _persist_key(new_key.decode())
    # Re-read settings so subsequent calls see the persisted key.
    get_settings.cache_clear()
    return new_key


def _persist_key(key: str) -> None:
    """Write ENCRYPTION_KEY=value to the .env file the app was loaded from.

    Uses APP_DATA_DIR (same as _persist_env_var) so the bundled EXE writes
    to the correct per-user data directory instead of CWD.
    Updates the file in place if the key already exists, otherwise appends.
    Bypasses pydantic-settings so we don't need a Settings reload signal.
    """
    _settings = get_settings()
    if _settings.APP_DATA_DIR:
        env_path = Path(_settings.APP_DATA_DIR) / ".env"
    else:
        env_path = Path(".env")
    line = f"ENCRYPTION_KEY={key}"
    if env_path.exists():
        text = env_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        replaced = False
        for i, ln in enumerate(lines):
            if ln.strip().startswith("ENCRYPTION_KEY="):
                lines[i] = line
                replaced = True
                break
        if not replaced:
            lines.append(line)
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        env_path.write_text(line + "\n", encoding="utf-8")
    # Match file permissions to typical .env (owner read/write only).
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        # Windows doesn't honor POSIX bits — best-effort only.
        pass


def _fernet() -> Fernet:
    return Fernet(_load_or_create_key())


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string for storage. Returns a url-safe base64 token."""
    if plaintext is None:
        return None  # type: ignore[return-value]
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_value(token: str) -> str:
    """Decrypt a Fernet token back to the original plaintext.

    Raises InvalidToken if the token is malformed, tampered with, or was
    encrypted with a different key. We don't catch it here — the caller
    decides whether bad data is a bug or a soft-fail condition.
    """
    if token is None:
        return None  # type: ignore[return-value]
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
