"""SQLAlchemy 2.0 declarative base with shared mixins.

Models are declared with ``Mapped``/``mapped_column`` so both type checkers
and IDEs can reason about column types. ``TimestampMixin`` supplies the
``created_at``/``updated_at`` columns used across every table.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base database model. Every ORM model inherits from this."""



class TimestampMixin:
    """Abstract mixin adding automatic created/updated timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=True,
    )