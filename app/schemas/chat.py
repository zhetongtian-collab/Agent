from pydantic import BaseModel, Field


# 聊天请求的数据结构。
# 前端调用聊天接口时会提交这个类对应的 JSON：
# message 是用户输入，session_id 用来区分会话，file_ids 表示本轮选择参与分析的文件。
class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str = "default"
    file_ids: list[int] = Field(default_factory=list)


# 聊天响应的数据结构。
# 后端处理完聊天后，会用这个结构返回答案、会话 ID、
# 本轮使用的文件 ID、命中的长期记忆，以及可能生成的 Word/Excel artifact 信息。
class ChatResponse(BaseModel):
    answer: str
    session_id: str
    used_file_ids: list[int] = Field(default_factory=list)
    memories: list[str] = Field(default_factory=list)
    artifacts: list[dict] = Field(default_factory=list)
