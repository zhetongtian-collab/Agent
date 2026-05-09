from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FileRecord
from app.memory.store import MemoryStore
from app.memory.vector_store import VectorStore


class SearchInput(BaseModel):
    query: str = Field(description="用户问题或检索关键词")
    limit: int = Field(default=5, ge=1, le=10)


class SaveMemoryInput(BaseModel):
    content: str = Field(description="需要长期保存的用户偏好、背景或事实")


def build_office_tools(db: Session) -> list[StructuredTool]:
    memory = MemoryStore(db)
    vectors = VectorStore()

    def search_memory(query: str, limit: int = 5) -> str:
        results = memory.search(query, limit=limit)
        return "\n".join(item.content for item in results)

    def save_memory(content: str) -> str:
        record = memory.add(content, source="tool")
        return f"已保存记忆 {record.id}"

    def search_uploaded_files(query: str, limit: int = 5) -> str:
        results = vectors.search_documents(query, limit=limit)
        return "\n\n".join(
            f"文件ID {item.get('file_id')}，文件名：{item.get('filename')}\n{item.get('content')}"
            for item in results
        )

    def list_uploaded_files(query: str = "", limit: int = 20) -> str:
        records = db.scalars(select(FileRecord).order_by(FileRecord.created_at.desc()).limit(limit)).all()
        return "\n".join(f"{record.id}: {record.filename}" for record in records)

    return [
        StructuredTool.from_function(
            name="search_memory",
            description="检索长期记忆。",
            func=search_memory,
            args_schema=SearchInput,
        ),
        StructuredTool.from_function(
            name="save_memory",
            description="保存长期记忆。",
            func=save_memory,
            args_schema=SaveMemoryInput,
        ),
        StructuredTool.from_function(
            name="search_uploaded_files",
            description="从已上传办公文件中检索相关内容。",
            func=search_uploaded_files,
            args_schema=SearchInput,
        ),
        StructuredTool.from_function(
            name="list_uploaded_files",
            description="列出用户已上传的文件。",
            func=list_uploaded_files,
        ),
    ]
