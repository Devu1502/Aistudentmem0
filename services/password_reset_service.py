from __future__ import annotations

import secrets

from config.settings import settings
from repositories.password_reset_repository import PasswordResetRepository
from repositories.user_repository import UserRepository
from services.auth_service import hash_password


class PasswordResetService:
    def __init__(self, db):
        self.user_repo = UserRepository(db)
        self.reset_repo = PasswordResetRepository(db)

    def request_reset(self, email: str) -> bool:
        user = self.user_repo.get_user_by_email(email)
        if not user:
            return True

        token = secrets.token_urlsafe(32)
        self.reset_repo.create_reset_token(str(user["_id"]), token)
        reset_link = f"{settings.frontend_url.rstrip('/')}/reset-password?token={token}"
        print(f"[PasswordReset] Send reset link to {email}: {reset_link}")
        return True

    def reset_password(self, token: str, new_password: str) -> bool:
        record = self.reset_repo.get_valid_token(token)
        if not record:
            return False

        hashed = hash_password(new_password)
        self.user_repo.update_user_password(record["user_id"], hashed)
        self.reset_repo.mark_token_used(token)
        return True
