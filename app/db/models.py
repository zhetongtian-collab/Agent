from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


# 上传文件记录表对应的 ORM 模型。
# 每上传一个文件，数据库里就会有一条 FileRecord：
# 保存原始文件名、本地磁盘路径、文件类型、抽取出的文本内容和上传时间。
# 后续聊天、文件列表、文件读取和向量检索都会用到这张表。
class FileRecord(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# 长期记忆记录表对应的 ORM 模型。
# 用来保存系统需要长期记住的信息，例如用户偏好、身份信息、项目背景等。
# vector_id 用来关联向量库中的同一条记忆，方便语义搜索时从向量结果回到数据库记录。
class MemoryRecord(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="chat")
    vector_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# 任务生成物记录表对应的 ORM 模型。
# 当系统生成 Word 或 Excel 文件时，会把生成文件的类型和路径记录在这里。
# 前端下载 artifact 时，会先根据这张表找到真实文件路径，再返回文件内容。
class TaskArtifact(Base):
    __tablename__ = "task_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    file: Mapped[FileRecord | None] = relationship()
