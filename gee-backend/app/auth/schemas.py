"""User schemas for registration, update, and read."""

import uuid
from typing import Optional

from fastapi_users import schemas
from pydantic import Field

from app.auth.models import UserRole


class UserRead(schemas.BaseUser[uuid.UUID]):
    nombre: str = ""
    apellido: str = ""
    telefono: str = ""
    role: UserRole = UserRole.CIUDADANO


class UserCreate(schemas.BaseUserCreate):
    nombre: str = Field(default="", max_length=200)
    apellido: str = Field(default="", max_length=200)
    telefono: str = Field(default="", max_length=50)


class UserUpdate(schemas.BaseUserUpdate):
    nombre: Optional[str] = Field(default=None, max_length=200)
    apellido: Optional[str] = Field(default=None, max_length=200)
    telefono: Optional[str] = Field(default=None, max_length=50)
