from langchain_openai import ChatOpenAI

from app.core.config import settings


def get_qwen_chat_model(temperature: float = 0.2) -> ChatOpenAI:
    if not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not configured.")

    return ChatOpenAI(
        model=settings.qwen_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.qwen_base_url,
        temperature=temperature,
    )
