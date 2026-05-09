from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str = "default"
    file_ids: list[int] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    used_file_ids: list[int] = Field(default_factory=list)
    memories: list[str] = Field(default_factory=list)
    artifacts: list[dict] = Field(default_factory=list)
