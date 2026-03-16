"""SQLModel table and API models."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Example(SQLModel, table=True):
    """Example table model. Replace or extend for your domain."""

    __tablename__ = "examples"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# --- Core Learnical domain tables ---


class Question(SQLModel, table=True):
    """Individual question definition."""

    __tablename__ = "questions"

    id: Optional[int] = Field(default=None, primary_key=True)

    prompt: str
    answer: str

    # Skills this question exercises (tags like "fractions", "reading_comprehension", ...)
    skills: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )

    # Vertical height band this question nominally occupies (percentage of page height)
    height: int

    # Difficulty from 1–10
    difficulty: int

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Worksheet(SQLModel, table=True):
    """Worksheet definition and metadata."""

    __tablename__ = "worksheets"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    subject: str
    image_url: Optional[str] = None

    # Ordered list of question IDs that make up this worksheet.
    # Stored as JSON array of ints in the database.
    questions: List[int] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )

    # Vertical answer regions: list of [start_pct, end_pct] (JSON arrays, not tuples)
    # Example: [[20, 30], [40, 45]] = 20–30% and 40–45% of page height
    answer_regions: List[List[int]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Student(SQLModel, table=True):
    """Student profile and learning stats."""

    __tablename__ = "students"

    id: Optional[int] = Field(default=None, primary_key=True)

    name: str

    # Example:
    # {"fractions": 72, "reading_comprehension": 88}
    learning_skills: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )

    # Example:
    # {"math": 0.83, "reading": 0.65}  # 0-1 percentiles, or 0-100 depending on your UI
    subject_percentiles: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )

    # Skills the student has fully mastered (tag names)
    mastered: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )

    # Streak of active learning days
    streak_days: int = Field(default=0)

    # Firebase UID used when auth is wired up
    firebase_uid: Optional[str] = Field(default=None, index=True, unique=True)

    # Extra bloated properties for experimentation
    grade_level: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class StudentWorksheet(SQLModel, table=True):
    """Per-student worksheet attempt and grading details."""

    __tablename__ = "student_worksheets"

    id: Optional[int] = Field(default=None, primary_key=True)

    student_id: int = Field(foreign_key="students.id", index=True)
    worksheet_id: int = Field(foreign_key="worksheets.id", index=True)

    # Per-question grading payload:
    # {
    #   "q1": {
    #       "given_answer": "...",
    #       "is_correct": true,
    #       "score": 1.0,
    #       "comment": "Great job with equivalent fractions",
    #       "focus_skill": "fractions"
    #   },
    #   ...
    # }
    marks: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )

    # Optional rollup stats
    total_score: Optional[float] = None
    max_score: Optional[float] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    graded_at: Optional[datetime] = None


# --- Non-table (API) models ---


class OCRResult(SQLModel):
    """Response model for OCR endpoint. Not a DB table."""

    text: str

