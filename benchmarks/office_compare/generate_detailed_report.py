from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"


def _percent(value: float) -> str:
    return f"{value:.2%}"


def _escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _detail(row: dict[str, Any]) -> str:
    return " | ".join(str(step.get("detail", "")) for step in row.get("steps", []))


def _failure_type(row: dict[str, Any]) -> str:
    if row.get("passed"):
        return "passed"
    detail = _detail(row).casefold()
    if "unsupported file type" in detail:
        return "unsupported_upload"
    if "missing " in detail and " artifact" in detail:
        return "missing_artifact"
    if "formula cache empty" in detail:
        return "formula_cache"
    if "golden mismatches" in detail:
        return "spreadsheet_result_mismatch"
    if "http 500" in detail or row.get("status") == "error":
        return "execution_error"
    if "missing values" in detail or "none matched" in detail:
        return "answer_mismatch"
    return "other_failure"


def _summary(rows: list[dict[str, Any]], system: str, group: str | None = None) -> dict[str, Any]:
    selected = [
        row for row in rows
        if row["system"] == system and (group is None or row["group"] == group)
    ]
    passed = sum(1 for row in selected if row.get("passed"))
    elapsed = sum(float(row.get("elapsed_seconds", 0)) for row in selected)
    return {
        "passed": passed,
        "total": len(selected),
        "rate": passed / len(selected) if selected else 0,
        "elapsed": elapsed,
        "average": elapsed / len(selected) if selected else 0,
    }


def _result_table(rows: list[dict[str, Any]], system: str) -> list[str]:
    lines = [
        "| 编号 | 任务组 | 结果 | 用时（秒） | 失败类型 | 评分详情 |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for row in sorted((item for item in rows if item["system"] == system), key=lambda item: item["task_id"]):
        detail = _detail(row)
        if len(detail) > 180:
            detail = detail[:177] + "..."
        lines.append(
            f"| {row['task_id']} | {row['group']} | {row['status']} | "
            f"{float(row.get('elapsed_seconds', 0)):.3f} | {_failure_type(row)} | {_escape(detail)} |"
        )
    return lines


def generate(source: Path = RESULTS / "latest.json", output: Path = RESULTS / "detailed-report.md") -> Path:
    payload = json.loads(source.read_text(encoding="utf-8"))
    rows = list(payload["results"])
    systems = ["longchain", "conversational-rag-chatbot"]
    groups = ["shared", "longchain_extension", "officebench_adapted", "spreadsheetbench_verified"]
    overall = {system: _summary(rows, system) for system in systems}
    shared = {system: _summary(rows, system, "shared") for system in systems}
    failure_counts = {
        system: Counter(_failure_type(row) for row in rows if row["system"] == system and not row.get("passed"))
        for system in systems
    }

    lines = [
        "# LongChain 与 conversational-rag-chatbot 完整对比实验报告",
        "",
        f"- 报告生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 原始结果文件：`{source.name}`",
        "- 生成模型：双方统一使用 DashScope `qwen-plus`。",
        "",
        "## 1. 实验目的",
        "",
        "本实验比较 LongChain 自动化办公 Agent 与开源基础项目 `conversational-rag-chatbot`。",
        "实验同时报告公平能力对比与完整覆盖率对比：",
        "",
        "1. **公平能力对比**：仅统计双方都具备的 8 条文档 RAG 任务。",
        "2. **完整覆盖率对比**：双方均尝试执行全部 55 条任务；baseline 原生不支持的文件上传或 artifact 交付按失败记录。",
        "",
        "## 2. 实验对象",
        "",
        "| 系统 | 定位 | 主要能力 |",
        "| --- | --- | --- |",
        "| LongChain | 自动化办公 Agent | 文档问答、Excel 分析和编辑、Word/Excel artifact、图表、长期记忆、LibreOffice 公式缓存重算 |",
        "| conversational-rag-chatbot | 开源基础 RAG baseline | 文档上传、向量检索、对话问答；原生上传接口仅接受 PDF、DOCX、HTML |",
        "",
        "## 3. 测试集组成",
        "",
        "| 任务组 | 数量 | 用途 |",
        "| --- | ---: | --- |",
        "| `shared` | 8 | 双方共同支持的文档 RAG 公平对比 |",
        "| `longchain_extension` | 7 | Excel、artifact、图表、长期记忆能力 |",
        "| `officebench_adapted` | 20 | 从 OfficeBench 适配到当前 HTTP 工具边界的子集 |",
        "| `spreadsheetbench_verified` | 20 | SpreadsheetBench Verified 官方工作簿与 golden 区域对比 |",
        "| **合计** | **55** | 完整覆盖率实验 |",
        "",
        "## 4. 评分方法",
        "",
        "- 文档问答任务：检查回答是否包含必要字段。",
        "- Word、Excel、图表任务：检查是否真实生成对应 artifact，并验证内容。",
        "- SpreadsheetBench Verified：比较输出工作簿与官方 golden 工作簿指定区域。",
        "- 执行异常、接口拒绝、缺失 artifact 均计为失败，不进行人工补分。",
        "",
        "## 5. 核心结果",
        "",
        "### 5.1 公平能力对比：双方共同支持的 8 条任务",
        "",
        "| 系统 | 通过数 | 总数 | 通过率 | 平均用时（秒） |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for system in systems:
        item = shared[system]
        lines.append(f"| {system} | {item['passed']} | {item['total']} | {_percent(item['rate'])} | {item['average']:.3f} |")

    lines.extend(
        [
            "",
            "### 5.2 完整覆盖率对比：双方均尝试 55 条任务",
            "",
            "| 系统 | 通过数 | 总数 | 覆盖通过率 | 总用时（秒） | 平均用时（秒） |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for system in systems:
        item = overall[system]
        lines.append(
            f"| {system} | {item['passed']} | {item['total']} | {_percent(item['rate'])} | "
            f"{item['elapsed']:.3f} | {item['average']:.3f} |"
        )

    lines.extend(
        [
            "",
            "### 5.3 分任务组结果",
            "",
            "| 系统 | 任务组 | 通过数 | 总数 | 通过率 | 平均用时（秒） |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for system in systems:
        for group in groups:
            item = _summary(rows, system, group)
            lines.append(
                f"| {system} | {group} | {item['passed']} | {item['total']} | "
                f"{_percent(item['rate'])} | {item['average']:.3f} |"
            )

    lines.extend(
        [
            "",
            "## 6. 失败原因统计",
            "",
            "| 系统 | 失败类型 | 数量 |",
            "| --- | --- | ---: |",
        ]
    )
    for system in systems:
        for failure_type, count in sorted(failure_counts[system].items()):
            lines.append(f"| {system} | `{failure_type}` | {count} |")

    lines.extend(
        [
            "",
            "失败类型说明：",
            "",
            "- `unsupported_upload`：系统上传接口不接受该文件类型。",
            "- `missing_artifact`：模型给出回答，但没有交付要求的 Word、Excel 或图表文件。",
            "- `spreadsheet_result_mismatch`：生成了 Excel，但指定区域与官方 golden 不一致。",
            "- `formula_cache`：公式存在，但公式缓存无法得到可评分值。",
            "- `answer_mismatch`：回答缺少评分要求中的必要字段。",
            "- `execution_error`：HTTP 或模型调用异常。",
            "",
            "## 7. 结果分析",
            "",
            f"- 在共同支持的 RAG 任务上，LongChain 为 **{shared['longchain']['passed']}/{shared['longchain']['total']}**，"
            f"baseline 为 **{shared['conversational-rag-chatbot']['passed']}/{shared['conversational-rag-chatbot']['total']}**。",
            f"- 在完整 55 条覆盖率实验中，LongChain 为 **{overall['longchain']['passed']}/{overall['longchain']['total']}**，"
            f"baseline 为 **{overall['conversational-rag-chatbot']['passed']}/{overall['conversational-rag-chatbot']['total']}**。",
            "- baseline 的完整覆盖率结果不能解释为模型本身的纯准确率差异；其中包含系统边界差异，例如不支持 Excel 上传和不返回办公 artifact。",
            "- LongChain 在 SpreadsheetBench Verified 上的未通过任务主要反映复杂公式生成与业务理解仍有改进空间。",
            "",
            "## 8. 实验结论",
            "",
            "本实验支持以下结论：LongChain 在保留文档 RAG 能力的同时，扩展了可验证的自动化办公执行能力。",
            "相较基础 RAG baseline，它能够处理更多文件类型，并交付可下载、可自动评分的办公 artifact。",
            "论文或答辩中应同时展示公平能力对比与完整覆盖率对比，不应只展示单一总分。",
            "",
            "## 9. 实验限制",
            "",
            "- `officebench_adapted` 是适配子集，不等同于 OfficeBench 官方 Docker 环境总分。",
            "- SpreadsheetBench Verified 使用 20 条固定子集，不代表完整 400 条数据集表现。",
            "- 两个系统统一使用 `qwen-plus`，但向量检索实现不同：baseline 使用 DashScope embedding，LongChain 使用项目内置 HashEmbedding。",
            "- 外部模型服务可能产生少量随机延迟或工具调用格式异常；原始结果保留这些异常，不进行人工修正。",
            "",
            "## 10. LongChain 逐项结果",
            "",
            *_result_table(rows, "longchain"),
            "",
            "## 11. baseline 逐项结果",
            "",
            *_result_table(rows, "conversational-rag-chatbot"),
            "",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


if __name__ == "__main__":
    print(generate())
