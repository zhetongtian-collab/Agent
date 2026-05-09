from datetime import datetime

from pydantic import BaseModel


class FileInfo(BaseModel):
    id: int
    filename: str
    content_type: str | None
    created_at: datetime
    preview: str

    class Config:
        from_attributes = True


class ExportRequest(BaseModel):
    kind: str
    filename: str
    content: str


class ArtifactInfo(BaseModel):
    id: int
    kind: str
    path: str
    download_url: str

    class Config:
        from_attributes = True
