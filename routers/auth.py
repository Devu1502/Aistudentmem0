from __future__ import annotations

# Authentication router covering signup, login, and password management.
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status, UploadFile, File
from pydantic import BaseModel, EmailStr
from bson import ObjectId

from auth_config import auth_config
from repositories.user_repository import UserRepository
from schemas.user import CreateUser, LoginUser
from services.auth_service import (
    create_access_token,
    hash_password,
    protect,
    validate_password_strength,
    verify_password,
)
from services.password_reset_service import PasswordResetService


router = APIRouter(prefix="/auth", tags=["auth"])


# Response schema returned to clients on successful login.
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Payload for requesting a password reset email.
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


# Input needed to confirm a password reset.
class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_password: str


# Simple profile update payload for PATCH /me.
class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None


@router.post("/signup", status_code=status.HTTP_201_CREATED)
# Create a new user after validating passwords and terms.
def signup(payload: CreateUser, request: Request):
    db = request.app.state.mongo_db
    user_repo = UserRepository(db)

    if not payload.accept_terms:
        raise HTTPException(status_code=400, detail="You must accept the Terms & Conditions to sign up.")

    desired_terms_version = payload.terms_version or auth_config.terms_version
    if desired_terms_version != auth_config.terms_version:
        raise HTTPException(
            status_code=400,
            detail=f"Please accept the latest Terms & Conditions (version {auth_config.terms_version}).",
        )

    if payload.password != payload.password_confirm:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    existing_user = user_repo.get_user_by_email(payload.email.lower())
    if existing_user:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    validate_password_strength(payload.password)

    user_document = {
        "name": payload.name,
        "email": payload.email.lower(),
        "password": hash_password(payload.password),
        "role": "user",
        "created_at": datetime.utcnow(),
        "verified": False,
        "accepted_terms_version": desired_terms_version,
    }

    created = user_repo.create_user(user_document)
    sanitized = user_repo.serialize_user(created)
    return {"message": "Signup successful.", "user": sanitized}


@router.post("/login", response_model=TokenResponse)
# Validate credentials and issue a JWT.
def login(payload: LoginUser, request: Request):
    db = request.app.state.mongo_db
    user_repo = UserRepository(db)
    user = user_repo.get_user_by_email(payload.email.lower())
    if not user or not verify_password(payload.password, user.get("password", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    token = create_access_token(str(user["_id"]))
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
# Show the current authenticated user.
def get_me(current_user: dict = Depends(protect)):
    return {"user": current_user}


@router.patch("/me")
# Allow users to update simple profile fields.
def update_me(payload: UpdateProfileRequest, request: Request, current_user: dict = Depends(protect)):
    db = request.app.state.mongo_db
    user_repo = UserRepository(db)
    update_fields = {}
    if payload.name:
        update_fields["name"] = payload.name

    if not update_fields:
        return {"user": current_user}

    updated = user_repo.update_user(current_user["id"], update_fields)
    return {"user": user_repo.serialize_user(updated)}


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
# Permanently delete the authenticated account.
def delete_me(request: Request, current_user: dict = Depends(protect)):
    db = request.app.state.mongo_db
    user_repo = UserRepository(db)
    user_repo.delete_user(current_user["id"])
    return None


@router.post("/forgot-password")
# Trigger a password-reset email if the user exists.
def forgot_password(payload: ForgotPasswordRequest, request: Request):
    service = PasswordResetService(request.app.state.mongo_db)
    service.request_reset(payload.email.lower())
    return {"message": "If the account exists, a reset link has been sent."}


@router.post("/reset-password")
# Finalize a password reset using the emailed token.
def reset_password(payload: ResetPasswordRequest, request: Request):
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    validate_password_strength(payload.new_password)
    service = PasswordResetService(request.app.state.mongo_db)
    ok = service.reset_password(payload.token, payload.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid or expired token.")
    return {"message": "Password reset successful."}
# Store an uploaded avatar blob directly in Mongo.
@router.post("/avatar")
async def upload_avatar(request: Request, file: UploadFile = File(...), current_user: dict = Depends(protect)):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file provided.")
    db = request.app.state.mongo_db
    db["users"].update_one(
        {"_id": ObjectId(current_user["id"])},
        {"$set": {"avatar": contents, "avatar_content_type": file.content_type}},
    )
    return {"message": "Avatar updated."}
