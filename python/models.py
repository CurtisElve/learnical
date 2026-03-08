"""SQLModel table and API models."""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Example(SQLModel, table=True):
    """Example table model. Replace or extend for your domain."""

    __tablename__ = "examples"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# --- Non-table (API) models ---


class OCRResult(SQLModel):
    """Response model for OCR endpoint. Not a DB table."""

    text: str


# Add more table models below, e.g.:
# class User(SQLModel, table=True):
#     __tablename__ = "users"
#     id: Optional[int] = Field(default=None, primary_key=True)
#     email: str = Field(unique=True)
#     ...
