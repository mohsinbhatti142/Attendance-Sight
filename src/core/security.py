"""JWT token utilities and password hashing for authentication."""

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import os

from jose import JWTError, jwt

from src.core.config import get_settings

settings = get_settings()

ALGORITHM = "HS256"
SESSION_EXPIRE_DAYS = 5

PBKDF2_ITERATIONS = 310_000


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token.

    Args:
        data: Payload data to encode in the token.
        expires_delta: Optional custom expiration timedelta.
            Defaults to SESSION_EXPIRE_DAYS.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(days=SESSION_EXPIRE_DAYS)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    """Decode and verify a JWT access token.

    Args:
        token: The JWT string to verify.

    Returns:
        The decoded token payload as a dict.

    Raises:
        JWTError: If the token is invalid or expired.
    """
    try:
        payload: dict = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
        )
        return payload
    except JWTError:
        raise


def get_password_hash(password: str) -> str:
    """Hash a plain-text password using bcrypt.

    Args:
        password: The plain-text password to hash.

    Returns:
        The bcrypt-hashed password string.
    """
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "$".join(("pbkdf2_sha256", str(PBKDF2_ITERATIONS),
                     base64.urlsafe_b64encode(salt).decode("ascii"),
                     base64.urlsafe_b64encode(digest).decode("ascii")))


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a hashed password.

    Args:
        plain: The plain-text password.
        hashed: The bcrypt-hashed password to compare against.

    Returns:
        True if the password matches, False otherwise.
    """
    if hashed.startswith("pbkdf2_sha256$"):
        try:
            scheme, rounds, salt_b64, digest_b64 = hashed.split("$", 3)
            if scheme != "pbkdf2_sha256":
                return False
            salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
            expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
            actual = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, int(rounds))
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False
    if hashed.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            import bcrypt
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
        except (ImportError, ValueError):
            return False
    return False
