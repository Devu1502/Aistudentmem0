# Mongo-backed repository for managing user records.
from __future__ import annotations

from typing import Any, Dict, Optional

from bson import ObjectId


class UserRepository:
    # Maintain a handle to the users collection.
    def __init__(self, db):
        self.collection = db["users"]

    # Create a new user document and return it.
    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        result = self.collection.insert_one(user_data)
        return self.collection.find_one({"_id": result.inserted_id})

    # Look up a user by their e-mail address.
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return self.collection.find_one({"email": email})

    # Fetch by Mongo id (string or ObjectId).
    def find_by_id(self, user_id: str | ObjectId) -> Optional[Dict[str, Any]]:
        oid = ObjectId(user_id) if isinstance(user_id, str) else user_id
        return self.collection.find_one({"_id": oid})

    # Apply field updates and return the latest record.
    def update_user(self, user_id: str | ObjectId, update_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        oid = ObjectId(user_id) if isinstance(user_id, str) else user_id
        self.collection.update_one({"_id": oid}, {"$set": update_fields})
        return self.find_by_id(oid)

    # Remove a user entirely.
    def delete_user(self, user_id: str | ObjectId) -> None:
        oid = ObjectId(user_id) if isinstance(user_id, str) else user_id
        self.collection.delete_one({"_id": oid})

    # Update the stored credential hash for password resets.
    def update_user_password(self, user_id: ObjectId, new_hashed_password: str) -> None:
        self.collection.update_one({"_id": user_id}, {"$set": {"password": new_hashed_password}})

    @staticmethod
    # Convert a Mongo document into an API-friendly dict.
    def serialize_user(doc: Dict[str, Any]) -> Dict[str, Any]:
        if not doc:
            return {}
        return {
            "id": str(doc.get("_id")),
            "name": doc.get("name"),
            "email": doc.get("email"),
            "role": doc.get("role", "user"),
            "verified": bool(doc.get("verified", False)),
            "created_at": doc.get("created_at"),
            "accepted_terms_version": doc.get("accepted_terms_version"),
        }
