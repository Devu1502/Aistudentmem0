from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import jwt
from jwt import ExpiredSignatureError, PyJWTError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext

from auth_config import auth_config
from repositories.user_repository import UserRepository

pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto"
)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    # bcrypt requires <= 72 bytes
    password_bytes = password.encode("utf-8")[:72]
    return pwd_context.hash(password_bytes)


def verify_password(password: str, hashed_password: str) -> bool:
    # bcrypt verification must use same truncation
    password_bytes = password.encode("utf-8")[:72]
    return pwd_context.verify(password_bytes, hashed_password)


def validate_password_strength(password: str) -> None:
    if len(password) < auth_config.password_min_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {auth_config.password_min_length} characters long.",
        )
    if not re.search(r"[A-Z]", password):
        raise HTTPException(status_code=400, detail="Password must include at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise HTTPException(status_code=400, detail="Password must include at least one lowercase letter.")
    if not re.search(r"\d", password):
        raise HTTPException(status_code=400, detail="Password must include at least one number.")
    if not re.search(r"[^\w\s]", password):
        raise HTTPException(status_code=400, detail="Password must include at least one special character.")


def create_access_token(subject: str, additional_claims: Optional[Dict[str, Any]] = None) -> str:
    expire = datetime.utcnow() + timedelta(minutes=auth_config.jwt_expiry_minutes)
    payload: Dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    if additional_claims:
        payload.update(additional_claims)
    return jwt.encode(payload, auth_config.jwt_secret_key, algorithm=auth_config.jwt_algorithm)


def verify_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, auth_config.jwt_secret_key, algorithms=[auth_config.jwt_algorithm])
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from exc
    except PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


async def protect(request: Request, token: str = Depends(oauth2_scheme)):
    payload = verify_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user_repo = UserRepository(request.app.state.mongo_db)
    user = user_repo.find_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")

    sanitized = user_repo.serialize_user(user)
    request.state.user = sanitized
    return sanitized


def restrict_to(allowed_roles: List[str]):
    async def dependency(current_user: Dict[str, Any] = Depends(protect)):
        role = current_user.get("role", "user")
        if role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return dependency
