from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MemoryRecord
from app.memory.vector_store import VectorStore


class MemoryStore:
    def __init__(self, db: Session, vector_store: VectorStore | None = None):
        self.db = db
        self.vector_store = vector_store or VectorStore()

    def search(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        vector_hits = self.vector_store.search_memories(query, limit=limit)
        if vector_hits:
            ids = [int(hit["memory_id"]) for hit in vector_hits if hit.get("memory_id")]
            records = list(self.db.scalars(select(MemoryRecord).where(MemoryRecord.id.in_(ids))).all())
            by_id = {record.id: record for record in records}
            ordered = [by_id[memory_id] for memory_id in ids if memory_id in by_id]
            if ordered:
                return ordered
        return list(self.db.scalars(select(MemoryRecord).order_by(MemoryRecord.updated_at.desc()).limit(limit)).all())

    def add(self, content: str, source: str = "chat") -> MemoryRecord:
        normalized = content.strip()
        existing = self.db.scalar(select(MemoryRecord).where(MemoryRecord.content == normalized))
        if existing:
            return existing
        vector_id = uuid4().hex
        record = MemoryRecord(content=normalized, source=source, vector_id=vector_id)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        self.vector_store.upsert_memory(record.id, vector_id, normalized)
        return record

    def maybe_update_from_conversation(self, user_message: str, answer: str) -> None:
        markers = ["我叫", "我是", "我的", "公司", "项目", "偏好", "以后", "记住"]
        if any(marker in user_message for marker in markers):
            self.add(f"用户信息：{user_message[:500]}", source="chat")
