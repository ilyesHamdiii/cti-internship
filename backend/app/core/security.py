from datetime import UTC, datetime, timedelta
from typing import Any, cast

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return cast(str, pwd_context.hash(password))


def verify_password(password: str, hashed: str) -> bool:
    return cast(bool, pwd_context.verify(password, hashed))


def create_token(subject: str, role: str, minutes: int, token_type: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return cast(
        str,
        jwt.encode(
            payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
        ),
    )


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return cast(
            dict[str, Any],
            jwt.decode(
                token, settings.jwt_secret.get_secret_value(), algorithms=[settings.jwt_algorithm]
            ),
        )
    except JWTError as exc:
        raise ValueError("invalid_token") from exc
