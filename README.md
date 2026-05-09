# LongChain Office Agent

基于 FastAPI、LangChain 和阿里通义千问的智能办公 Agent。

## 当前能力

- ChatGPT 式前端对话页面
- 上传并读取 Word、Excel、PDF、TXT、CSV 文件
- SQLite 保存文件、会话、长期记忆和生成文件记录
- Chroma 保存文件片段和长期记忆索引
- 接入阿里千问兼容 OpenAI API
- LangChain `create_agent` 自主调用工具
- 可生成 Word / Excel 文件，并返回下载链接

## 配置

```powershell
copy .env.example .env
```

然后填写：

```env
DASHSCOPE_API_KEY=你的阿里千问APIKey
```

## 后端启动

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

健康检查：

```text
http://localhost:8000/health
```

## 前端启动

```powershell
cd frontend
npm install --cache ..\.npm-cache
npm run dev -- --port 5173
```

浏览器打开：

```text
http://localhost:5173
```

## 智能体示例

上传 Excel 后可以说：

```text
分析这个 Excel 的表结构，告诉我有哪些工作表和字段。
```

上传文件后生成 Word：

```text
读取我选择的文件，整理成一份 Word 分析报告，并给我下载链接。
```

保存长期记忆：

```text
请记住，以后报告都用条目式结构输出。
```

## 测试

后端测试：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

前端构建：

```powershell
cd frontend
npm run build
```

## 说明文档

面向初学者的当前系统说明在：

```text
docs/current-system-guide.md
```
