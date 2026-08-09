"""Phase 1 SQLAlchemy models for the Astitva foundation."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="USER")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    profile: Mapped["UserProfile | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    roadmaps: Mapped[list["Roadmap"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserProfile(Base, TimestampMixin):
    __tablename__ = "user_profiles"
    __table_args__ = (Index("ix_user_profiles_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    onboarding_data: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user: Mapped["User"] = relationship(back_populates="profile")


class Scheme(Base, TimestampMixin):
    __tablename__ = "schemes"
    __table_args__ = (
        Index("ix_schemes_category", "category"),
        Index("ix_schemes_state", "state"),
        Index("ix_schemes_target_group", "target_group"),
        Index("ix_schemes_active_status", "active_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scheme_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    scheme_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    min_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    income_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eligibility: Mapped[str | None] = mapped_column(Text, nullable=True)
    age_criteria: Mapped[str | None] = mapped_column(String(255), nullable=True)
    income_criteria: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_group: Mapped[str | None] = mapped_column(String(255), nullable=True)
    benefits: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_documents: Mapped[list[str]] = mapped_column(JSON, default=list)
    application_process: Mapped[str | None] = mapped_column(Text, nullable=True)
    official_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_verified: Mapped[str | None] = mapped_column(String(50), nullable=True)
    active_status: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def name(self) -> str:
        return self.scheme_name

    @name.setter
    def name(self, value: str) -> None:
        self.scheme_name = value


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_user_id", "user_id"),
        Index("ix_documents_status", "status"),
        Index("ix_documents_document_type", "document_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    document_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    user: Mapped["User"] = relationship()


class Roadmap(Base, TimestampMixin):
    __tablename__ = "roadmaps"
    __table_args__ = (
        Index("ix_roadmaps_user_id", "user_id"),
        Index("ix_roadmaps_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255), default="Personalized Roadmap")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="DRAFT")
    user: Mapped["User"] = relationship(back_populates="roadmaps")
    tasks: Mapped[list["RoadmapTask"]] = relationship(
        back_populates="roadmap",
        cascade="all, delete-orphan",
        order_by="RoadmapTask.id",
    )
    progress_entries: Mapped[list["Progress"]] = relationship(
        back_populates="roadmap",
        cascade="all, delete-orphan",
        order_by="Progress.id",
    )


class RoadmapTask(Base, TimestampMixin):
    __tablename__ = "roadmap_tasks"
    __table_args__ = (
        Index("ix_roadmap_tasks_roadmap_id", "roadmap_id"),
        Index("ix_roadmap_tasks_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    roadmap_id: Mapped[int] = mapped_column(ForeignKey("roadmaps.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    priority: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    roadmap: Mapped["Roadmap"] = relationship(back_populates="tasks")


class Progress(Base, TimestampMixin):
    __tablename__ = "progress"
    __table_args__ = (
        Index("ix_progress_roadmap_id", "roadmap_id"),
        Index("ix_progress_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    roadmap_id: Mapped[int] = mapped_column(ForeignKey("roadmaps.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE")
    completed_milestones: Mapped[int] = mapped_column(Integer, default=0)
    missed_milestones: Mapped[int] = mapped_column(Integer, default=0)
    overdue_tasks: Mapped[int] = mapped_column(Integer, default=0)
    engagement_history: Mapped[list[str]] = mapped_column(JSON, default=list)
    roadmap: Mapped["Roadmap"] = relationship(back_populates="progress_entries")
