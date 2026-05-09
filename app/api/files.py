from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import FileRecord, TaskArtifact
from app.schemas.files import ArtifactInfo, ExportRequest, FileInfo
from app.services.document_service import DocumentService
from app.tools.output_tools import generate_excel, generate_word

router = APIRouter()


@router.post("/upload", response_model=FileInfo)
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)) -> FileInfo:
    record = await DocumentService(db).save_upload(file)
    return FileInfo(
        id=record.id,
        filename=record.filename,
        content_type=record.content_type,
        created_at=record.created_at,
        preview=record.extracted_text[:600],
    )


@router.get("", response_model=list[FileInfo])
def list_files(db: Session = Depends(get_db)) -> list[FileInfo]:
    records = db.scalars(select(FileRecord).order_by(FileRecord.created_at.desc())).all()
    return [
        FileInfo(
            id=record.id,
            filename=record.filename,
            content_type=record.content_type,
            created_at=record.created_at,
            preview=record.extracted_text[:600],
        )
        for record in records
    ]


@router.post("/export", response_model=ArtifactInfo)
def export_file(request: ExportRequest, db: Session = Depends(get_db)) -> ArtifactInfo:
    if request.kind == "word":
        path = generate_word(request.filename, request.content)
    elif request.kind == "excel":
        path = generate_excel(request.filename, request.content)
    else:
        raise HTTPException(status_code=400, detail="kind must be word or excel")

    artifact = TaskArtifact(kind=request.kind, path=str(path))
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return ArtifactInfo(
        id=artifact.id,
        kind=artifact.kind,
        path=artifact.path,
        download_url=f"/api/files/artifacts/{artifact.id}/download",
    )


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: int, db: Session = Depends(get_db)) -> FileResponse:
    artifact = db.get(TaskArtifact, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="artifact not found")
    path = Path(artifact.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact file missing")
    return FileResponse(path, filename=path.name)
