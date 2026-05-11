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
# 文件上传接口。
# 接收浏览器上传的文件，交给 DocumentService 保存到本地并抽取文本，
# 然后返回文件 ID、文件名、类型、创建时间和一小段内容预览。
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
# 文件列表接口。
# 从数据库中按创建时间倒序读取所有上传记录，
# 并把每条记录转换成前端需要的 FileInfo 结构。
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


@router.delete("/{file_id}", status_code=204)
# 删除文件接口。
# 根据文件 ID 调用 DocumentService 删除数据库记录、本地文件和向量索引。
# 成功时返回 204，没有响应体。
def delete_file(file_id: int, db: Session = Depends(get_db)) -> None:
    DocumentService(db).delete_file(file_id)


@router.post("/export", response_model=ArtifactInfo)
# 导出文件接口。
# 根据 request.kind 决定生成 Word 还是 Excel 文件，
# 生成后把文件路径保存到 TaskArtifact 表，并返回下载地址给前端。
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
# artifact 下载接口。
# 先从数据库查找导出文件记录，再检查本地文件是否存在；
# 如果都正常，就用 FileResponse 把真实文件返回给浏览器下载。
def download_artifact(artifact_id: int, db: Session = Depends(get_db)) -> FileResponse:
    artifact = db.get(TaskArtifact, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="artifact not found")
    path = Path(artifact.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact file missing")
    return FileResponse(path, filename=path.name)
