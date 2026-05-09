from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, files, memory
from app.core.config import settings
from app.db.database import init_db


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

    @app.on_event("startup")
    def on_startup() -> None:
        init_db()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
