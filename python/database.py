"""Database engine and session setup for SQLModel."""

from sqlmodel import Session, create_engine

from models import SQLModel

# Default to SQLite; override with DATABASE_URL for Postgres etc.
DATABASE_URL = "sqlite:///./learnical.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False,  # Set True for SQL logging
)


def get_session():
    """Dependency-friendly session generator."""
    with Session(engine) as session:
        yield session
