from datetime import datetime

from pydantic import BaseModel


# 文件信息响应结构。
# 用于上传成功和文件列表接口，告诉前端文件 ID、文件名、类型、
# 创建时间以及抽取文本的预览内容。
class FileInfo(BaseModel):
    id: int
    filename: str
    content_type: str | None
    created_at: datetime
    preview: str

    # Pydantic 配置类。
    # from_attributes=True 表示可以直接从 SQLAlchemy ORM 对象读取字段，
    # 不需要手动先把 ORM 对象转换成普通字典。
    class Config:
        from_attributes = True


# 导出文件请求结构。
# 前端请求后端生成文件时使用：
# kind 表示生成 word 还是 excel，filename 是期望文件名，content 是要写入文件的内容。
class ExportRequest(BaseModel):
    kind: str
    filename: str
    content: str


# 生成物信息响应结构。
# 用于返回系统生成的 Word/Excel 文件信息，
# 包括 artifact ID、类型、本地路径和前端可访问的下载地址。
class ArtifactInfo(BaseModel):
    id: int
    kind: str
    path: str
    download_url: str

    # Pydantic 配置类。
    # 允许响应模型直接读取 ORM 对象属性，
    # 这样接口返回数据库模型时也能自动按字段序列化。
    class Config:
        from_attributes = True
