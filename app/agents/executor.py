import json
from collections.abc import Iterator
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import wrap_model_call
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver

from app.db.models import FileRecord


AGENT_SYSTEM_PROMPT = """你是一个可以自主调用工具的智能办公 Agent。
你可以处理 Word、Excel、PDF、TXT、CSV 等办公文件。
工作规则：
1. 需要了解已上传文件时，先调用 list_uploaded_files。
2. 需要读取指定文件内容时，调用 read_file。
3. 需要从历史上传文件中查找内容时，调用 search_uploaded_files。
4. 需要分析 Excel 表结构时，调用 analyze_excel。
5. 需要生成 Word 文件时，必须调用 generate_word_report，不要假装已经生成。
6. 需要生成 Excel 文件时，必须调用 generate_excel_table，不要假装已经生成。
7. 需要根据 Excel 生成可视化图表图片、折线图、柱状图或趋势图时，必须调用 generate_excel_chart，不要回答“不支持生成图表”。
8. 发现用户明确要求保存长期偏好、身份、项目背景时，调用 save_memory。
9. 用户明确要求给某个邮箱发送邮件时，必须调用 send_email；如果本轮临时上下文里有用户选中的文件，把对应文件 ID 放入 send_email 的 file_ids 作为附件发送；只有 send_email 返回 ok=true 后，才能说邮件已发送。
10. 用户要求收邮件、查看未读邮件或读取邮件时，必须调用 fetch_unread_emails；默认 mark_read=true，让成功拉取的未读邮件变成已读，避免下次重复拉取；工具返回 ok=true 后，把未读邮件的发件人、主题、正文和文本附件内容展示给用户。
11. 工具返回 download_url 时，最终回答必须把下载链接告诉用户。
12. 不要编造文件中不存在的数据。信息不足时说明缺口，并提出下一步。"""


AGENT_SYSTEM_PROMPT += """

PDF 表格规则：
1. 用户要求读取 PDF 论文中的 Table 1、表 1、某个具体表格数据时，必须优先调用 list_pdf_tables 和 read_pdf_table。
2. 只有 read_pdf_table 返回 ok=true 且包含 rows 时，才能复述表格数据；回答必须包含文件名、页码、表格编号或标题。
3. 如果 read_pdf_table 返回失败、没有 rows，或只检索到零散正文片段，必须明确说明未定位到结构化表格，不要猜测、补全或编造任何数值。

Excel 样式规则：
1. 用户要求生成 Excel 并把超过、大于、高于某个阈值的数据或行标红时，调用 generate_excel_table，并设置 highlight_gt 为该阈值。
2. 用户要求生成 Excel 并把小于、低于、少于某个阈值的数据或行标红时，调用 generate_excel_table，并设置 highlight_lt 为该阈值，不要使用 highlight_gt。
3. 用户明确指定列名时，例如“销售额小于 1000 的行标红”，必须设置 highlight_column 为该列名，例如“销售额”；不要用其他列的数值触发行标红。
4. 用户说“行标红”或未说明范围时，highlight_scope 使用 row；用户明确只标红单元格时，highlight_scope 使用 cell。

Excel 图表规则：
1. 用户要求对选中的 Excel 数据生成可视化图表、折线图、柱状图、趋势图时，调用 generate_excel_chart。
2. 如果本轮只选择了一个 Excel 文件，直接使用该文件 ID；如果选择了多个 Excel 文件且目标不明确，先询问用户要使用哪个文件。
3. 折线图或趋势图使用 chart_type="line"，柱状图使用 chart_type="bar"。只有工具返回图表 artifact 后，才能说明图表已生成。
4. 系统已经支持生成图表图片并在对话窗口直接展示；不要说只能读取 Excel、生成 Word/Excel 或让用户本地绘图。

Excel 单元格编辑规则：
1. 用户要求修改现有 Excel、补公式、修复单元格或填充指定区域时，必须调用 edit_uploaded_excel_cells。
2. 使用用户本轮选中的 Excel 文件 ID，并在 updates 中逐项填写 cell、value；需要指定工作表时填写 sheet_name。
3. 如果任务要求填写计算结果，可以直接把计算后的值写入单元格；如果用户明确要求公式，则把以 = 开头的 Excel 公式写入 value。
4. 只有工具返回 Excel artifact 后，才能说明修改后的工作簿已经生成。
"""


AGENT_SYSTEM_PROMPT += """

Excel artifact delivery rules:
1. For exact Excel work, use read_excel_range, calculate_excel_sum, lookup_excel, or filter_excel when they reduce manual reasoning.
2. For contiguous result regions, prefer write_uploaded_excel_range. For translated formulas across a region, prefer fill_uploaded_excel_formula. Use edit_uploaded_excel_cells for scattered cells.
3. Any request to modify an uploaded Excel workbook is complete only after an Excel artifact tool returns an artifact. Do not stop after analysis or arithmetic.
"""


EXCEL_ARTIFACT_RETRY_PROMPT = """The requested Excel workbook has not been delivered yet.
Continue the task now. Use an Excel artifact-producing tool such as write_uploaded_excel_range,
fill_uploaded_excel_formula, edit_uploaded_excel_cells, or generate_excel_table. Return the modified
Excel artifact before finishing. Do not stop after explaining the result."""


CHECKPOINTER = InMemorySaver()


@wrap_model_call
# 这个函数是 LangChain Agent 的模型调用中间件。
# 每次 Agent 准备调用大模型前，都会先经过这里：
# 1. 从 request.runtime.context 里取出本轮临时上下文；
# 2. 如果有文件内容、记忆或检索片段，就把它们插入到最后一条用户消息前面；
# 3. 最后再把处理后的请求交给原来的 handler 继续调用模型。
def inject_runtime_context(request: Any, handler: Any) -> Any:
    context = getattr(request.runtime, "context", None) or {}
    extra_context = str(context.get("extra_context") or "").strip()
    if extra_context:
        request = request.override(messages=_inject_context_message(request.messages, extra_context))
    return handler(request)


# 同步运行办公 Agent，并一次性拿到完整结果。
# 调用方需要传入大模型、可用工具、对话消息和 session_id。
# 函数内部会创建 Agent、执行 invoke，然后从 Agent 返回的消息里提取：
# 1. 最终回答文本；
# 2. 工具生成的文件 artifact 信息；
# 3. 完整消息列表，方便后续调试或继续对话。
def run_office_agent(
    model: Any,
    tools: list[BaseTool],
    messages: list[BaseMessage],
    session_id: str,
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=AGENT_SYSTEM_PROMPT,
        middleware=[inject_runtime_context],
        checkpointer=CHECKPOINTER,
    )
    config = {"configurable": {"thread_id": session_id}}
    result = agent.invoke(
        {"messages": messages},
        config=config,
        context=runtime_context or {},
    )
    output_messages = result.get("messages", []) if isinstance(result, dict) else []
    if _requires_excel_artifact(messages) and not _has_excel_artifact(output_messages):
        result = agent.invoke(
            {"messages": [HumanMessage(content=EXCEL_ARTIFACT_RETRY_PROMPT)]},
            config=config,
            context=runtime_context or {},
        )
        output_messages = result.get("messages", []) if isinstance(result, dict) else []
    answer = _last_ai_text(output_messages)
    artifacts = _extract_artifacts(output_messages)
    return {"answer": answer, "artifacts": artifacts, "messages": output_messages}


# 流式运行办公 Agent，适合前端边生成边展示。
# 它会监听 Agent 的 stream 事件：
# 1. 遇到 AIMessageChunk 时，把增量文本 token 逐段 yield 出去；
# 2. 遇到工具消息时，尝试解析是否生成了可下载文件；
# 3. 流结束后再汇总完整答案和所有 artifact，发送 done 事件。
def stream_office_agent(
    model: Any,
    tools: list[BaseTool],
    messages: list[BaseMessage],
    session_id: str,
    runtime_context: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=AGENT_SYSTEM_PROMPT,
        middleware=[inject_runtime_context],
        checkpointer=CHECKPOINTER,
    )
    collected_messages: list[BaseMessage] = []
    answer_parts: list[str] = []

    for event in agent.stream(
        {"messages": messages},
        config={"configurable": {"thread_id": session_id}},
        context=runtime_context or {},
        stream_mode=["messages", "updates"],
    ):
        mode, payload = _normalize_stream_event(event)
        if mode == "messages":
            message = _message_from_payload(payload)
            if message is None:
                continue
            if isinstance(message, AIMessageChunk):
                token = _content_to_text(message.content)
                if token:
                    answer_parts.append(token)
                    yield {"type": "token", "content": token}
            elif isinstance(message, ToolMessage):
                collected_messages.append(message)
                artifact = _extract_artifact_from_text(_content_to_text(message.content))
                if artifact:
                    yield {"type": "artifact", "artifact": artifact}
            elif isinstance(message, BaseMessage):
                collected_messages.append(message)
        elif mode == "updates":
            collected_messages.extend(_messages_from_update(payload))

    artifacts = _extract_artifacts(collected_messages)
    retry_answer = ""
    if _requires_excel_artifact(messages) and not _has_excel_artifact(collected_messages):
        retry_result = agent.invoke(
            {"messages": [HumanMessage(content=EXCEL_ARTIFACT_RETRY_PROMPT)]},
            config={"configurable": {"thread_id": session_id}},
            context=runtime_context or {},
        )
        retry_messages = retry_result.get("messages", []) if isinstance(retry_result, dict) else []
        collected_messages.extend(retry_messages)
        retry_answer = _last_ai_text(retry_messages)
        artifacts = _extract_artifacts(collected_messages)
        for artifact in artifacts:
            yield {"type": "artifact", "artifact": artifact}
    answer = retry_answer or "".join(answer_parts).strip() or _last_ai_text(collected_messages)
    yield {"type": "done", "answer": answer, "artifacts": artifacts}


# 把普通字符串形式的用户输入包装成 LangChain 需要的消息对象。
# 目前只生成一条 HumanMessage，后续如果要加入历史消息，也可以从这里扩展。
def build_agent_messages(user_message: str) -> list[BaseMessage]:
    return [HumanMessage(content=user_message)]


# 构造 Agent 运行时上下文。
# memories 是长期记忆，selected_files 是用户本轮指定的文件，
# retrieved_documents 是向量检索出来的相关文档片段。
# 这些内容会合并成 extra_context，之后由中间件注入到模型输入中。
def build_runtime_context(
    memories: list[str],
    selected_files: list[FileRecord],
    retrieved_documents: list[dict],
) -> dict[str, str]:
    return {"extra_context": _build_context(memories, selected_files, retrieved_documents)}


# 把记忆、选中文件和检索片段拼成一段给模型看的上下文文本。
# 这里不会调用模型，只负责组织提示信息：
# 1. 长期记忆用列表展示；
# 2. 选中文件带上文件 ID、文件名和内容预览；
# 3. 检索片段带上来源文件和相关内容。
def _build_context(memories: list[str], selected_files: list[FileRecord], retrieved_documents: list[dict]) -> str:
    parts = []
    if memories:
        parts.append("相关长期记忆：\n" + "\n".join(f"- {item}" for item in memories))
    if selected_files:
        chunks = ["用户本次选择的文件："]
        for file in selected_files:
            chunks.append(f"文件ID {file.id}，文件名：{file.filename}\n内容预览：{file.extracted_text[:4000]}")
        parts.append("\n\n".join(chunks))
    if retrieved_documents:
        chunks = ["从已上传文件中检索到的相关片段："]
        for item in retrieved_documents:
            chunks.append(f"文件ID {item.get('file_id')}，文件名：{item.get('filename')}\n{item.get('content', '')[:1200]}")
        parts.append("\n\n".join(chunks))
    return "\n\n".join(parts)


# 把额外上下文真正插入到消息列表里。
# 优先找到最后一条 HumanMessage，把上下文放在用户当前任务前面；
# 如果消息列表里没有用户消息，就新建一条 HumanMessage 放到最前面。
def _inject_context_message(messages: list[BaseMessage], extra_context: str) -> list[BaseMessage]:
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            original = _content_to_text(messages[index].content)
            current_message = HumanMessage(
                content=f"本轮临时上下文：\n{extra_context}\n\n用户当前任务：\n{original}"
            )
            return [*messages[:index], current_message, *messages[index + 1 :]]
    return [HumanMessage(content=f"本轮临时上下文：\n{extra_context}"), *messages]


# 从一组消息中倒序查找最后一条 AIMessage，并转成纯文本。
# Agent 返回的 messages 里可能包含工具消息、用户消息和 AI 消息，
# 最后一条有内容的 AI 消息通常就是最终回答。
def _last_ai_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content:
            return _content_to_text(message.content)
    return ""


# 把 LangChain 消息里的 content 统一转换为字符串。
# content 有时是普通字符串，有时是包含 text 字段的列表结构；
# 统一处理后，其他函数就不用关心 content 的具体格式。
def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


# 从所有消息里提取工具生成的 artifact 信息。
# 工具返回内容可能是 JSON 字符串，如果其中包含 artifact 字段，
# 就收集起来，并避免重复添加同一个 artifact。
def _requires_excel_artifact(messages: list[BaseMessage]) -> bool:
    text = "\n".join(
        _content_to_text(message.content)
        for message in messages
        if isinstance(message, HumanMessage)
    ).casefold()
    excel_markers = (
        "excel artifact",
        "edit_uploaded_excel_cells",
        "write_uploaded_excel_range",
        "fill_uploaded_excel_formula",
        "生成 excel",
        "修改选中的 excel",
        "修改当前 excel",
        "修改现有 excel",
        "补公式",
        "填充指定区域",
    )
    return "excel" in text and any(marker in text for marker in excel_markers)


def _has_excel_artifact(messages: list[BaseMessage]) -> bool:
    return any(artifact.get("kind") == "excel" for artifact in _extract_artifacts(messages))


def _extract_artifacts(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for message in messages:
        text = _content_to_text(getattr(message, "content", ""))
        artifact = _extract_artifact_from_text(text)
        if artifact and artifact not in artifacts:
            artifacts.append(artifact)
    return artifacts


# 尝试从一段文本中解析单个 artifact。
# 只有文本是合法 JSON，并且 JSON 顶层包含 artifact 字典时才返回结果；
# 如果不是工具结果或 JSON 格式错误，就返回 None。
def _extract_artifact_from_text(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and isinstance(data.get("artifact"), dict):
        return data["artifact"]
    return None


# 兼容不同 LangChain/LangGraph stream 事件格式。
# 有些事件是 ("messages", payload)，有些是 dict 更新，
# 这个函数把它们统一成 (mode, payload)，方便主循环判断。
def _normalize_stream_event(event: Any) -> tuple[str, Any]:
    if isinstance(event, tuple) and len(event) == 2:
        first, second = event
        if first in {"messages", "updates"}:
            return str(first), second
        if isinstance(first, BaseMessage):
            return "messages", first
    if isinstance(event, dict):
        return "updates", event
    return "unknown", event


# 从 stream 的 payload 中取出真正的 BaseMessage。
# payload 可能直接就是消息，也可能是一个 tuple，消息在第一个元素里。
# 如果取不到合法消息，就返回 None，让调用方跳过。
def _message_from_payload(payload: Any) -> BaseMessage | None:
    if isinstance(payload, tuple) and payload:
        candidate = payload[0]
        return candidate if isinstance(candidate, BaseMessage) else None
    return payload if isinstance(payload, BaseMessage) else None


# 从 updates 类型的 payload 中收集消息列表。
# LangGraph 的更新事件可能按节点名包一层 dict，
# 这里会遍历每个 value，把里面的 BaseMessage 统一拿出来。
def _messages_from_update(payload: Any) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    if not isinstance(payload, dict):
        return messages
    for value in payload.values():
        if isinstance(value, dict) and isinstance(value.get("messages"), list):
            messages.extend(item for item in value["messages"] if isinstance(item, BaseMessage))
        elif isinstance(value, list):
            messages.extend(item for item in value if isinstance(item, BaseMessage))
    return messages
