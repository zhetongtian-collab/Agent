from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


# 确保 SQLite 数据库文件所在的目录已经存在。
# 如果 DATABASE_URL 使用 sqlite:/// 开头，就从 URL 里取出文件路径，
# 然后创建父目录，避免 create_engine 或建表时因为目录不存在而失败。
def _ensure_sqlite_parent() -> None:
    if settings.database_url.startswith("sqlite:///"):
        db_path = Path(settings.database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_parent()
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# 初始化数据库表结构。
# 先导入 models，让 SQLAlchemy 知道有哪些模型类，
# 再根据 Base.metadata 在数据库中创建尚不存在的表。
def init_db() -> None:
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


# FastAPI 的数据库会话依赖。
# 每次请求进来时创建一个 Session，把它 yield 给接口使用；
# 请求结束后无论成功失败都会关闭 Session，释放数据库连接。
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
