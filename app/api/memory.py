from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import MemoryRecord
from app.schemas.memory import MemoryInfo

router = APIRouter()


@router.get("", response_model=list[MemoryInfo])
def list_memories(db: Session = Depends(get_db)) -> list[MemoryRecord]:
    return list(db.scalars(select(MemoryRecord).order_by(MemoryRecord.updated_at.desc())).all())
