from datetime import datetime

from pydantic import BaseModel


class MemoryInfo(BaseModel):
    id: int
    content: str
    source: str
    created_at: datetime

    class Config:
        from_attributes = True
