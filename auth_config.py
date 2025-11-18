# Small helper to gather authentication-related environment settings.
from __future__ import annotations

import os
from dataclasses import dataclass


# Frozen dataclass ensures auth defaults stay immutable at runtime.
@dataclass(frozen=True)
class AuthConfig:
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "change-me")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expiry_minutes: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    terms_version: str = os.getenv("TERMS_VERSION", "v1")
    password_min_length: int = int(os.getenv("PASSWORD_MIN_LENGTH", "8"))


# Instantiate once so other modules can import a shared config.
auth_config = AuthConfig()
