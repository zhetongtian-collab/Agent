import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, ToolMessage


StepStatus = Literal["preparing", "running", "success", "failed"]


TOOL_TITLES = {
    "list_uploaded_files": "查看已上传文件",
    "read_file": "读取文件内容",
    "search_uploaded_files": "检索已上传文件",
    "analyze_excel": "分析 Excel 表结构",
    "generate_excel_chart": "生成 Excel 图表",
    "read_excel_range": "读取 Excel 数据区域",
    "calculate_excel_sum": "计算 Excel 汇总数据",
    "lookup_excel": "查询 Excel 数据",
    "filter_excel": "筛选 Excel 数据",
    "write_uploaded_excel_range": "写入 Excel 数据区域",
    "fill_uploaded_excel_formula": "填充 Excel 公式",
    "edit_uploaded_excel_cells": "修改 Excel 单元格",
    "list_pdf_tables": "定位 PDF 表格",
    "read_pdf_table": "读取 PDF 表格数据",
    "search_memory": "检索长期记忆",
    "save_memory": "保存长期记忆",
    "generate_word_report": "生成 Word 报告",
    "generate_excel_table": "生成 Excel 表格",
    "send_email": "发送邮件",
    "fetch_unread_emails": "拉取未读邮件",
}


@dataclass
class TaskStep:
    id: str
    title: str
    status: StepStatus = "preparing"
    tool_name: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, str]:
        payload = {"id": self.id, "title": self.title, "status": self.status}
        if self.tool_name:
            payload["tool_name"] = self.tool_name
        if self.detail:
            payload["detail"] = self.detail
        return payload


class TaskPlanTracker:
    def __init__(self, user_message: str):
        self.steps = build_task_plan(user_message)
        self._tool_call_steps: dict[str, str] = {}
        self._finished_tool_calls: set[str] = set()

    def plan_event(self) -> dict[str, Any]:
        return {"type": "plan", "steps": [step.to_dict() for step in self.steps]}

    def observe_message(self, message: BaseMessage) -> list[dict[str, Any]]:
        if isinstance(message, ToolMessage):
            return self._observe_tool_result(message)
        if isinstance(message, AIMessage) and not isinstance(message, AIMessageChunk):
            return self._observe_tool_calls(message)
        return []

    def finish_events(self) -> list[dict[str, Any]]:
        events = []
        for step in self.steps:
            if step.tool_name is None and step.status == "preparing":
                events.append(self._update_step(step, "success", "已完成"))
            elif step.status == "running":
                events.append(self._update_step(step, "failed", "工具调用未返回结果"))
        return events

    def fail_active_events(self, error: str) -> list[dict[str, Any]]:
        return [
            self._update_step(step, "failed", error)
            for step in self.steps
            if step.status == "running"
        ]

    def _observe_tool_calls(self, message: AIMessage) -> list[dict[str, Any]]:
        events = []
        for call in getattr(message, "tool_calls", []) or []:
            if not isinstance(call, dict):
                continue
            tool_name = str(call.get("name") or "").strip()
            call_id = str(call.get("id") or "").strip()
            if not tool_name or not call_id or call_id in self._tool_call_steps:
                continue
            step = self._find_or_add_tool_step(tool_name)
            events.extend(self._complete_prior_reasoning_steps(step))
            self._tool_call_steps[call_id] = step.id
            if step.status != "running":
                events.append(self._update_step(step, "running", f"正在执行：{step.title}"))
        return events

    def _observe_tool_result(self, message: ToolMessage) -> list[dict[str, Any]]:
        call_id = str(getattr(message, "tool_call_id", "") or "")
        if not call_id or call_id in self._finished_tool_calls:
            return []
        self._finished_tool_calls.add(call_id)

        step_id = self._tool_call_steps.get(call_id)
        tool_name = str(getattr(message, "name", "") or "")
        step = self._step_by_id(step_id) if step_id else None
        if step is None:
            step = self._find_or_add_tool_step(tool_name or "tool")
        success, detail = _tool_result_status(message.content)
        return [self._update_step(step, "success" if success else "failed", detail)]

    def _find_or_add_tool_step(self, tool_name: str) -> TaskStep:
        for step in self.steps:
            if step.tool_name == tool_name and step.status == "preparing":
                return step
        title = TOOL_TITLES.get(tool_name, f"执行工具：{tool_name}")
        step = TaskStep(id=f"step-{len(self.steps) + 1}", title=title, tool_name=tool_name)
        self.steps.append(step)
        return step

    def _complete_prior_reasoning_steps(self, target: TaskStep) -> list[dict[str, Any]]:
        events = []
        target_index = self.steps.index(target)
        for step in self.steps[:target_index]:
            if step.tool_name is None and step.status == "preparing":
                events.append(self._update_step(step, "success", "已完成"))
        return events

    def _step_by_id(self, step_id: str | None) -> TaskStep | None:
        return next((step for step in self.steps if step.id == step_id), None)

    @staticmethod
    def _update_step(step: TaskStep, status: StepStatus, detail: str) -> dict[str, Any]:
        step.status = status
        step.detail = detail
        return {"type": "step", "step": step.to_dict()}


def build_task_plan(user_message: str) -> list[TaskStep]:
    text = user_message.casefold()
    steps: list[TaskStep] = []

    def add(title: str, tool_name: str | None = None) -> None:
        if not any(step.title == title and step.tool_name == tool_name for step in steps):
            steps.append(TaskStep(id=f"step-{len(steps) + 1}", title=title, tool_name=tool_name))

    receives_email = any(marker in text for marker in ("收邮件", "未读邮件", "查看邮件", "读取邮件", "拉取邮件"))
    mentions_feedback = any(marker in text for marker in ("客户反馈", "客户意见", "客户建议", "反馈邮件"))
    needs_word = "word" in text or any(marker in text for marker in ("报告", "汇报", "文档"))
    sends_email = bool(re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", text)) or any(
        marker in text for marker in ("发送邮件", "发邮件", "邮件发给", "发给我")
    )

    if receives_email:
        add("拉取未读邮件", "fetch_unread_emails")
    if mentions_feedback:
        add("筛选客户反馈邮件")
    if receives_email:
        add("提取邮件正文和附件内容")
    if "pdf" in text and any(marker in text for marker in ("表格", "table", "数据")):
        add("定位 PDF 表格", "list_pdf_tables")
        add("读取 PDF 表格数据", "read_pdf_table")
    if "excel" in text and any(marker in text for marker in ("分析", "结构", "表头")):
        add("分析 Excel 表结构", "analyze_excel")
    if "excel" in text and any(marker in text for marker in ("图表", "折线图", "柱状图", "趋势图")):
        add("生成 Excel 图表", "generate_excel_chart")
    if needs_word:
        add("生成 Word 报告", "generate_word_report")
    if "excel" in text and any(marker in text for marker in ("生成", "导出", "表格")):
        add("生成 Excel 表格", "generate_excel_table")
    if sends_email:
        add("发送邮件", "send_email")
    if not steps:
        add("理解任务并组织执行方案")
    return steps


def _tool_result_status(content: Any) -> tuple[bool, str]:
    if not isinstance(content, str):
        return True, "已完成"
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return True, "已完成"
    if isinstance(payload, dict) and payload.get("ok") is False:
        return False, str(payload.get("error") or "工具执行失败")
    return True, "已完成"
