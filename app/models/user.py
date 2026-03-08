from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    screen_name: str = Field(min_length=3, max_length=40)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    birth_date: datetime | None = None


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    screen_name: str
    first_name: str
    last_name: str
    account: bool
    opt_in: bool
    created_at: datetime
