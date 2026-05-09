from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter()


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    return ChatService(db).handle_chat(request)
