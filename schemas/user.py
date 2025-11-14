from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class CreateUser(BaseModel):
    name: Optional[str] = None
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str
    accept_terms: bool
    terms_version: Optional[str] = None


class LoginUser(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: str
    name: Optional[str] = None
    email: EmailStr
    role: str
    verified: bool
    created_at: datetime
    accepted_terms_version: Optional[str] = None
