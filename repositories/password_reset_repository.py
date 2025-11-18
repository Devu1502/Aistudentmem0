# Simple Mongo wrapper for password reset tokens.
from __future__ import annotations

from datetime import datetime, timedelta

from bson import ObjectId


RESET_TOKEN_EXPIRY_MINUTES = 30


class PasswordResetRepository:
    # Keep a reference to the password reset collection.
    def __init__(self, db):
        self.collection = db["password_reset_tokens"]

    # Insert a new token document with expiry metadata.
    def create_reset_token(self, user_id: str, token: str) -> bool:
        expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)
        doc = {
            "user_id": ObjectId(user_id),
            "token": token,
            "expires_at": expires_at,
            "used": False,
            "created_at": datetime.utcnow(),
        }
        self.collection.insert_one(doc)
        return True

    # Retrieve a token that has not expired or been used.
    def get_valid_token(self, token: str):
        return self.collection.find_one(
            {
                "token": token,
                "used": False,
                "expires_at": {"$gt": datetime.utcnow()},
            }
        )

    # Mark a token as consumed so it cannot be replayed.
    def mark_token_used(self, token: str) -> None:
        self.collection.update_one({"token": token}, {"$set": {"used": True}})
