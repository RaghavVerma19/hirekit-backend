from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Any, Dict, Optional
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import jwt
from app.core.config import settings

# Initialize Argon2 Password Hasher
ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

# Pre-computed dummy hash to prevent login timing attacks (email enumeration)
DUMMY_HASH = ph.hash("hirekit-dummy-password-for-timing-equalization")


def hash_password(password: str) -> str:
    """Hash password using Argon2id."""
    return ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against Argon2id hash."""
    try:
        return ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, Exception):
        return False


def create_access_token(user_id: str, role: str, extra_claims: Optional[Dict[str, Any]] = None) -> str:
    """Create a signed JWT access token (15 min default)."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    to_encode = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
    }
    if extra_claims:
        to_encode.update(extra_claims)
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub", "type"]},
        )
        if payload.get("type") != "access":
            raise jwt.InvalidTokenError("Token is not an access token")
        return payload
    except jwt.ExpiredSignatureError:
        raise jwt.ExpiredSignatureError("Access token has expired")
    except jwt.PyJWTError as e:
        raise jwt.InvalidTokenError(f"Invalid access token: {str(e)}")


def generate_random_token(bytes_length: int = 48) -> str:
    """Generate a secure cryptographically random URL-safe token."""
    return secrets.token_urlsafe(bytes_length)


def hash_token(token: str) -> str:
    """Compute SHA-256 hash of a raw token for secure database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
