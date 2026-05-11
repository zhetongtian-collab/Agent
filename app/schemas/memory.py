from datetime import datetime

from pydantic import BaseModel


# 长期记忆信息响应结构。
# 用于记忆列表接口，向前端展示每条记忆的 ID、内容、来源和创建时间。
# 它只描述接口返回的数据形状，不负责真正的数据库读写。
class MemoryInfo(BaseModel):
    id: int
    content: str
    source: str
    created_at: datetime

    # Pydantic 配置类。
    # from_attributes=True 允许直接把 SQLAlchemy 的 MemoryRecord 转成 MemoryInfo。
    class Config:
        from_attributes = True
