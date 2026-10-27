from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Result(Base):
    __tablename__ = "results"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # "extract" | "match"
    # job status tracking for async queue
    status: Mapped[str] = mapped_column(String(16), default="completed")  # "pending" | "processing" | "completed" | "failed"
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON blob
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
