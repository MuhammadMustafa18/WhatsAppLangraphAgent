"""Security utilities — password hashing, JWT tokens, encryption.

Phase 6: password hashing.
Phase 7: JWT tokens will be added here.
Phase 35: Fernet encryption will be added here.
"""

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plain-text password. Returns bcrypt hash."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return pwd_context.verify(plain, hashed)
