"""Database engine and session setup for SQLModel."""

import os

from sqlmodel import Session, create_engine

from models import SQLModel

# Postgres in any shared/deployed environment, e.g.:
#   DATABASE_URL=postgresql+psycopg2://learnical:secret@localhost:5432/learnical
# SQLite fallback keeps single-machine dev zero-setup.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./learnical.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=not DATABASE_URL.startswith("sqlite"),
    echo=False,  # Set True for SQL logging
)


def get_session():
    """Dependency-friendly session generator."""
    with Session(engine) as session:
        yield session
