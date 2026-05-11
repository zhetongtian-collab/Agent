from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MemoryRecord
from app.memory.vector_store import VectorStore


# 长期记忆业务类。
# 它把“数据库记录”和“向量检索”封装到一起：
# 数据库存真实内容，向量库存可搜索的语义向量。
# 聊天服务和工具层通过这个类来搜索、添加、删除和自动更新用户记忆。
class MemoryStore:
    # 初始化长期记忆存储对象。
    # db 是当前请求使用的数据库会话；
    # vector_store 可以外部传入，默认会新建一个 VectorStore 用于相似度检索。
    def __init__(self, db: Session, vector_store: VectorStore | None = None):
        self.db = db
        self.vector_store = vector_store or VectorStore()

    # 根据用户问题搜索相关长期记忆。
    # 优先使用向量库做语义检索，并按向量检索返回的顺序排序；
    # 如果向量库没有结果，就退回到数据库中最近更新的记忆记录。
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

    # 新增一条长期记忆。
    # 会先去掉首尾空白并检查数据库里是否已有完全相同的内容；
    # 如果没有重复，就写入数据库，同时把内容写入向量库，方便之后语义搜索。
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

    # 删除一条长期记忆。
    # 先根据 ID 查数据库；如果不存在就返回 404。
    # 如果这条记忆有向量 ID，也会同步删除向量库里的对应数据。
    def delete(self, memory_id: int) -> None:
        record = self.db.get(MemoryRecord, memory_id)
        if not record:
            raise HTTPException(status_code=404, detail="memory not found")
        if record.vector_id:
            self.vector_store.delete_memory(record.vector_id)
        self.db.delete(record)
        self.db.commit()

    # 根据一轮对话判断是否需要自动保存长期记忆。
    # 目前用简单关键词判断用户是否提到了姓名、公司、项目、偏好等长期有效信息；
    # 命中后会把用户原话的一部分保存为记忆，供后续对话检索使用。
    def maybe_update_from_conversation(self, user_message: str, answer: str) -> None:
        markers = ["我叫", "我是", "我的", "公司", "项目", "偏好", "以后", "记住"]
        if any(marker in user_message for marker in markers):
            self.add(f"用户信息：{user_message[:500]}", source="chat")
