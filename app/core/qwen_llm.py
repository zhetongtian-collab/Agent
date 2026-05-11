from langchain_openai import ChatOpenAI

from app.core.config import settings


# 创建并返回通义千问兼容 OpenAI 接口的聊天模型对象。
# temperature 控制回答随机性，值越低越稳定。
# 如果没有配置 DASHSCOPE_API_KEY，就直接抛错，避免后面调用模型时才失败。
def get_qwen_chat_model(temperature: float = 0.2) -> ChatOpenAI:
    if not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not configured.")

    return ChatOpenAI(
        model=settings.qwen_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.qwen_base_url,
        temperature=temperature,
    )
