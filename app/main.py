from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, files, memory
from app.core.config import settings
from app.db.database import init_db


# 创建并配置 FastAPI 应用。
# 这里集中完成三件事：
# 1. 创建应用对象并设置名称和版本；
# 2. 配置跨域，允许前端页面调用后端接口；
# 3. 注册 chat、files、memory 三组 API 路由。
def create_app() -> FastAPI:
    app = FastAPI(title="LongChain Office Agent", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin, "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(files.router, prefix="/api/files", tags=["files"])
    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])

    # 应用启动时执行的初始化逻辑。
    # 当前主要负责初始化数据库表，确保服务启动后接口可以正常读写数据。
    @app.on_event("startup")
    def on_startup() -> None:
        init_db()

    # 健康检查接口。
    # 常用于确认后端服务是否已经启动并能正常响应请求。
    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
