from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import MemoryRecord
from app.memory.store import MemoryStore
from app.schemas.memory import MemoryInfo

router = APIRouter()


@router.get("", response_model=list[MemoryInfo])
# 长期记忆列表接口。
# 从数据库读取所有 MemoryRecord，并按更新时间倒序排列，
# 让前端可以展示当前系统记住了哪些用户信息或偏好。
def list_memories(db: Session = Depends(get_db)) -> list[MemoryRecord]:
    return list(db.scalars(select(MemoryRecord).order_by(MemoryRecord.updated_at.desc())).all())


@router.delete("/{memory_id}", status_code=204)
# 删除长期记忆接口。
# 根据 memory_id 调用 MemoryStore 删除数据库中的记忆记录，
# 同时删除对应的向量索引，避免后续检索到已删除内容。
def delete_memory(memory_id: int, db: Session = Depends(get_db)) -> None:
    MemoryStore(db).delete(memory_id)
