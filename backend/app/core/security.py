"""
Security utilities — password hashing, JWT tokens, and Fernet encryption.

This module provides three independent capabilities:

1. **Password Hashing** (bcrypt directly)
   - `hash_password(plain)` → hashed string
   - `verify_password(plain, hashed)` → bool

2. **JWT Access Tokens** (python-jose)
   - `create_access_token(data, expires_delta?)` → encoded JWT string

3. **Symmetric Encryption** (Fernet via cryptography)
   - `encrypt_token(plain_text)` → encrypted string
   - `decrypt_token(cipher_text)` → decrypted string
   Used to encrypt Google OAuth tokens before storing them in PostgreSQL.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt
from cryptography.fernet import Fernet

from app.core.config import settings

# ═══════════════════════════════════════════════════════════════════════
# 1. Password Hashing (bcrypt)
# ═══════════════════════════════════════════════════════════════════════
#
# Using bcrypt directly instead of Passlib because Passlib's bcrypt
# backend is broken with bcrypt>=4.1 (AttributeError on __about__).
# The bcrypt library itself is stable and well-maintained.
# ═══════════════════════════════════════════════════════════════════════


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt.

    Args:
        plain_password: The raw password from the registration form.

    Returns:
        A bcrypt hash string (e.g. "$2b$12$...") safe to store in the DB.
    """
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash.

    Args:
        plain_password: The raw password from the login form.
        hashed_password: The hash stored in the `users.hashed_password` column.

    Returns:
        True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ═══════════════════════════════════════════════════════════════════════
# 2. JWT Access Tokens
# ═══════════════════════════════════════════════════════════════════════


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token.

    The token payload includes whatever `data` dict is passed in (typically
    `{"sub": user_id, "role": role}`) plus an `exp` expiration claim.

    Args:
        data: Claims to encode in the JWT payload.
        expires_delta: Optional custom lifetime. Defaults to the value
                       from settings.ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns:
        An encoded JWT string.
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT refresh token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # Default to 7 days
        expire = datetime.now(timezone.utc) + timedelta(days=7)
    
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# ═══════════════════════════════════════════════════════════════════════
# 3. Fernet Symmetric Encryption (for Google OAuth tokens)
# ═══════════════════════════════════════════════════════════════════════
#
# Google access/refresh tokens are sensitive credentials. We encrypt them
# with Fernet (AES-128-CBC + HMAC) before writing to PostgreSQL, and
# decrypt on read. The ENCRYPTION_KEY in .env must be a valid Fernet key.
#
# If ENCRYPTION_KEY is not configured (empty string), the encrypt/decrypt
# functions will raise a clear error — this is intentional so Google
# features fail loudly rather than silently storing tokens in plaintext.
# ═══════════════════════════════════════════════════════════════════════


def _get_fernet() -> Fernet:
    """Get a Fernet instance, raising a clear error if the key is missing."""
    if not settings.ENCRYPTION_KEY:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set in .env. "
            "Generate one with: python -c "
            '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt_token(plain_text: str) -> str:
    """Encrypt a plaintext string (e.g. a Google access token).

    Args:
        plain_text: The raw token string from Google OAuth.

    Returns:
        A Fernet-encrypted string safe to store in the database.
    """
    f = _get_fernet()
    return f.encrypt(plain_text.encode()).decode()


def decrypt_token(cipher_text: str) -> str:
    """Decrypt a Fernet-encrypted string back to plaintext.

    Args:
        cipher_text: The encrypted token string from the database.

    Returns:
        The original plaintext token.
    """
    f = _get_fernet()
    return f.decrypt(cipher_text.encode()).decode()
