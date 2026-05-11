from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import FileRecord
from app.memory.vector_store import VectorStore
from app.tools.file_reader import extract_text


class DocumentService:
    # 初始化文档服务。
    # db 是当前请求的数据库会话，后续保存和删除文件记录都通过它完成。
    def __init__(self, db: Session):
        self.db = db

    # 保存用户上传的文件。
    # 主要步骤：
    # 1. 确保上传目录存在，并用 uuid 生成安全的本地文件名；
    # 2. 把上传内容写入磁盘；
    # 3. 抽取文件文本，保存 FileRecord 到数据库；
    # 4. 把文本切块后写入向量库，方便以后按语义搜索文件内容。
    async def save_upload(self, upload: UploadFile) -> FileRecord:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(upload.filename or "").suffix
        safe_name = f"{uuid4().hex}{suffix}"
        target = settings.upload_dir / safe_name
        data = await upload.read()
        target.write_bytes(data)

        text = extract_text(target)
        record = FileRecord(
            filename=upload.filename or safe_name,
            path=str(target),
            content_type=upload.content_type,
            extracted_text=text,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        chunks = _chunk_text(text)
        VectorStore().upsert_document_chunks(record.id, record.filename, chunks)
        return record

    # 删除一个上传文件。
    # 会先查数据库记录，不存在则抛出 404；
    # 然后删除本地磁盘文件、删除向量库中的文档片段，最后删除数据库记录。
    def delete_file(self, file_id: int) -> None:
        record = self.db.get(FileRecord, file_id)
        if not record:
            raise HTTPException(status_code=404, detail="file not found")

        path = Path(record.path)
        if path.exists() and path.is_file():
            path.unlink()

        VectorStore().delete_document_chunks(file_id)
        self.db.delete(record)
        self.db.commit()


# 把长文本切成适合向量检索的小片段。
# size 表示每块最大长度，overlap 表示相邻块保留多少重叠内容；
# 重叠可以减少关键信息刚好落在切分边界时丢失上下文的问题。
def _chunk_text(text: str, size: int = 1200, overlap: int = 150) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    chunks = []
    start = 0
    while start < len(cleaned):
        end = min(start + size, len(cleaned))
        chunks.append(cleaned[start:end])
        if end == len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks
