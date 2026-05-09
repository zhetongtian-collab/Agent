from pathlib import Path

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FileRecord, TaskArtifact
from app.memory.store import MemoryStore
from app.memory.vector_store import VectorStore
from app.tools.excel_tools import analyze_excel_file
from app.tools.json_utils import fail, ok
from app.tools.output_tools import generate_excel, generate_word


class SearchInput(BaseModel):
    query: str = Field(description="用户问题或检索关键词")
    limit: int = Field(default=5, ge=1, le=10)


class SearchFilesInput(BaseModel):
    query: str = Field(description="用户问题或检索关键词")
    limit: int = Field(default=5, ge=1, le=10)
    file_ids: list[int] = Field(default_factory=list, description="如果只想检索指定文件，传入文件 ID 列表")


class SaveMemoryInput(BaseModel):
    content: str = Field(description="需要长期保存的用户偏好、业务背景或事实")


class ReadFileInput(BaseModel):
    file_id: int = Field(description="上传文件的 ID")
    max_chars: int = Field(default=12000, ge=500, le=30000, description="最多返回多少字符")


class AnalyzeExcelInput(BaseModel):
    file_id: int = Field(description="Excel 文件 ID")


class GenerateWordInput(BaseModel):
    title: str = Field(description="报告标题或文件名")
    content: str = Field(description="Word 正文内容")


class GenerateExcelInput(BaseModel):
    filename: str = Field(description="Excel 文件名")
    content: str = Field(description="表格内容，支持逗号、制表符或竖线分隔")


def build_office_tools(db: Session, public_base_url: str = "") -> list[StructuredTool]:
    memory = MemoryStore(db)
    vectors = VectorStore()

    def list_uploaded_files(query: str = "", limit: int = 20) -> str:
        records = db.scalars(select(FileRecord).order_by(FileRecord.created_at.desc()).limit(limit)).all()
        return ok(
            {
                "files": [
                    {
                        "id": record.id,
                        "filename": record.filename,
                        "content_type": record.content_type,
                        "preview": record.extracted_text[:300],
                    }
                    for record in records
                ]
            }
        )

    def read_file(file_id: int, max_chars: int = 12000) -> str:
        record = db.get(FileRecord, file_id)
        if not record:
            return fail("file not found", file_id=file_id)
        return ok(
            {
                "file": {
                    "id": record.id,
                    "filename": record.filename,
                    "content_type": record.content_type,
                    "content": record.extracted_text[:max_chars],
                }
            }
        )

    def search_uploaded_files(query: str, limit: int = 5, file_ids: list[int] | None = None) -> str:
        results = vectors.search_documents(query, limit=limit, file_ids=file_ids or None)
        return ok({"matches": results})

    def analyze_excel(file_id: int) -> str:
        record = db.get(FileRecord, file_id)
        if not record:
            return fail("file not found", file_id=file_id)
        suffix = Path(record.path).suffix.lower()
        if suffix not in {".xlsx", ".xlsm"}:
            return fail("file is not an Excel workbook", file_id=file_id, suffix=suffix)
        return ok({"file_id": file_id, "filename": record.filename, "analysis": analyze_excel_file(record.path)})

    def search_memory(query: str, limit: int = 5) -> str:
        results = memory.search(query, limit=limit)
        return ok({"memories": [{"id": item.id, "content": item.content, "source": item.source} for item in results]})

    def save_memory(content: str) -> str:
        record = memory.add(content, source="tool")
        return ok({"memory": {"id": record.id, "content": record.content}})

    def generate_word_report(title: str, content: str) -> str:
        path = generate_word(title, content)
        artifact = TaskArtifact(kind="word", path=str(path))
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        return _artifact_result(artifact, public_base_url)

    def generate_excel_table(filename: str, content: str) -> str:
        path = generate_excel(filename, content)
        artifact = TaskArtifact(kind="excel", path=str(path))
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        return _artifact_result(artifact, public_base_url)

    return [
        StructuredTool.from_function(
            name="list_uploaded_files",
            description="列出用户已经上传的办公文件，返回文件 ID、文件名和内容预览。",
            func=list_uploaded_files,
        ),
        StructuredTool.from_function(
            name="read_file",
            description="根据文件 ID 读取完整或部分文件文本内容。需要分析指定文件时先调用这个工具。",
            func=read_file,
            args_schema=ReadFileInput,
        ),
        StructuredTool.from_function(
            name="search_uploaded_files",
            description="从已上传文件的向量索引中检索与问题相关的内容片段。",
            func=search_uploaded_files,
            args_schema=SearchFilesInput,
        ),
        StructuredTool.from_function(
            name="analyze_excel",
            description="分析 Excel 文件结构，返回工作表、表头、行数、列数和样例行。",
            func=analyze_excel,
            args_schema=AnalyzeExcelInput,
        ),
        StructuredTool.from_function(
            name="search_memory",
            description="检索用户长期记忆，例如用户偏好、项目背景、常用输出格式。",
            func=search_memory,
            args_schema=SearchInput,
        ),
        StructuredTool.from_function(
            name="save_memory",
            description="保存长期记忆。只有用户偏好、身份信息、项目背景等长期有效事实才需要保存。",
            func=save_memory,
            args_schema=SaveMemoryInput,
        ),
        StructuredTool.from_function(
            name="generate_word_report",
            description="生成 Word 报告，并返回真实下载链接。需要交付 Word 文件时必须调用这个工具。",
            func=generate_word_report,
            args_schema=GenerateWordInput,
        ),
        StructuredTool.from_function(
            name="generate_excel_table",
            description="生成 Excel 表格，并返回真实下载链接。需要交付 Excel 文件时必须调用这个工具。",
            func=generate_excel_table,
            args_schema=GenerateExcelInput,
        ),
    ]


def _artifact_result(artifact: TaskArtifact, public_base_url: str) -> str:
    download_url = f"/api/files/artifacts/{artifact.id}/download"
    absolute_url = f"{public_base_url.rstrip('/')}{download_url}" if public_base_url else download_url
    return ok(
        {
            "artifact": {
                "id": artifact.id,
                "kind": artifact.kind,
                "path": artifact.path,
                "download_url": download_url,
                "absolute_download_url": absolute_url,
            }
        }
    )
