from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class FileRecord(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MemoryRecord(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="chat")
    vector_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskArtifact(Base):
    __tablename__ = "task_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    file: Mapped[FileRecord | None] = relationship()
