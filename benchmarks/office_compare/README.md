# LongChain 与基础 RAG 办公实验

本目录用于比较 LongChain 和开源基础项目
[`aryanmahawar205/conversational-rag-chatbot`](https://github.com/aryanmahawar205/conversational-rag-chatbot)。

## 实验设计

- `cases/shared_tasks.json`：8 个双方都能执行的文档问答任务。
- `cases/longchain_tasks.json`：7 个 LongChain 办公 Agent 扩展任务。
- `cases/officebench_subset.json`：20 个 OfficeBench 官方任务 ID，适配到 LongChain HTTP 工具边界。
- `cases/spreadsheetbench_verified_subset.json`：20 个 SpreadsheetBench Verified 官方任务 ID。
- 双方统一使用 DashScope `qwen-plus` 作为生成模型。
- baseline 使用 DashScope `text-embedding-v4`，LongChain 保持项目内置 HashEmbedding。
- 扩展能力与基础问答分开统计，避免把 baseline 不支持的能力计入基础准确率。
- LongChain 默认执行 55 条任务：自建 15 条、OfficeBench 适配子集 20 条、SpreadsheetBench Verified 子集 20 条。

## 公开测试集说明

OfficeBench 原生依赖 Docker 办公环境。当前项目会保留官方源任务 ID、输入文件和关键词评分，
但把文件系统交付改为 LongChain 可下载 artifact。这一组属于 `officebench_adapted`，不是 OfficeBench 官方总分。

SpreadsheetBench Verified 使用官方 `*_init.xlsx` 和 `*_golden.xlsx`。当前项目上传初始工作簿，
要求 Agent 调用 `write_uploaded_excel_range`、`fill_uploaded_excel_formula` 或 `edit_uploaded_excel_cells`
返回修改后的工作簿，并比较 golden 指定区域。

## 准备 baseline

```powershell
git clone https://github.com/aryanmahawar205/conversational-rag-chatbot.git D:\tmp\conversational-rag-chatbot-baseline
cd D:\tmp\LongChain-Project
.\.venv\Scripts\python.exe -m benchmarks.office_compare.configure_baseline D:\tmp\conversational-rag-chatbot-baseline
cd D:\tmp\conversational-rag-chatbot-baseline
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r D:\tmp\LongChain-Project\benchmarks\office_compare\baseline_requirements.txt
```

为 baseline 新建 `.env`：

```env
OPENAI_API_KEY=你的百炼 API Key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
LANGCHAIN_TRACING_V2=false
```

## 启动

LongChain：

```powershell
cd D:\tmp\LongChain-Project
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

baseline：

```powershell
cd D:\tmp\conversational-rag-chatbot-baseline\api
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001
```

## 运行

```powershell
cd D:\tmp\LongChain-Project
.\.venv\Scripts\python.exe -m benchmarks.office_compare.run_benchmark
```

结果会写入 `benchmarks/office_compare/results/`：

- `latest.json`：完整结果和模型回答。
- `latest.csv`：便于导入 Excel 的逐项结果。
- `latest.md`：可直接整理进论文或答辩材料的汇总表。

首次运行会自动将官方公开数据下载到系统临时目录。已有本地数据时，也可以显式指定：

```powershell
.\.venv\Scripts\python.exe -m benchmarks.office_compare.run_benchmark `
  --officebench-root D:\tmp\OfficeBench-main `
  --spreadsheetbench-root D:\tmp\spreadsheetbench_verified_400\spreadsheetbench_verified_400
```

只运行原有 15 条自建任务时：

```powershell
.\.venv\Scripts\python.exe -m benchmarks.office_compare.run_benchmark --skip-public
```

外部模型连接短暂失败时，可以只重跑指定任务并合并回最近报告：

```powershell
.\.venv\Scripts\python.exe -m benchmarks.office_compare.run_benchmark `
  --officebench-root D:\tmp\OfficeBench-main `
  --spreadsheetbench-root D:\tmp\spreadsheetbench_verified_400\spreadsheetbench_verified_400 `
  --task-ids O19,P17 `
  --skip-baseline `
  --resume-latest
```

SpreadsheetBench 中若 Agent 写入 Excel 公式，保存后会自动调用本机 LibreOffice headless Calc 重算公式缓存。
当前评分器会将公式缓存为空的单元格保留为未通过，并在 `latest.json` 中写明原因。
