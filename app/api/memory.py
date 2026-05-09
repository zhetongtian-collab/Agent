from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import MemoryRecord
from app.memory.store import MemoryStore
from app.schemas.memory import MemoryInfo

router = APIRouter()


@router.get("", response_model=list[MemoryInfo])
def list_memories(db: Session = Depends(get_db)) -> list[MemoryRecord]:
    return list(db.scalars(select(MemoryRecord).order_by(MemoryRecord.updated_at.desc())).all())


@router.delete("/{memory_id}", status_code=204)
def delete_memory(memory_id: int, db: Session = Depends(get_db)) -> None:
    MemoryStore(db).delete(memory_id)
