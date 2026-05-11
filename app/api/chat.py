import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter()


@router.post("", response_model=ChatResponse)
# 普通聊天接口：接收前端发来的 ChatRequest，
# 通过 FastAPI 依赖注入拿到数据库会话，
# 然后交给 ChatService 完成上下文构建、Agent 调用和响应封装。
def chat(request: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    return ChatService(db).handle_chat(request)


@router.post("/stream")
# 流式聊天接口：返回 text/event-stream，让前端可以实时收到模型输出。
# 内部会定义一个 events 生成器，逐个读取 ChatService 产生的事件，
# 再把事件包装成 SSE 格式发送给浏览器。
def stream_chat(request: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    # SSE 事件生成器。
    # 正常情况下逐条转发 token、artifact、done 等事件；
    # 如果服务层抛出异常，就把异常转成 error 事件返回给前端。
    def events() -> Iterator[str]:
        try:
            for event in ChatService(db).stream_chat(request):
                yield _sse(event)
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream")


# 把普通 Python 字典转换成 Server-Sent Events 需要的字符串格式。
# ensure_ascii=False 可以保留中文，避免中文被转义成 \uXXXX。
def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
