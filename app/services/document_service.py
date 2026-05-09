from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import FileRecord
from app.memory.vector_store import VectorStore
from app.tools.file_reader import extract_text


class DocumentService:
    def __init__(self, db: Session):
        self.db = db

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
