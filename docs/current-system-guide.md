# 当前项目说明：LongChain 智能办公助手 MVP

这份文档用尽量直白的方式说明当前项目能做什么、整体流程怎么跑、每个主要代码文件负责什么。

## 1. 当前系统是什么

当前项目是一个“智能办公助手 MVP”。

它现在具备这些能力：

- 有一个类似 ChatGPT 的网页聊天界面。
- 可以上传 Word、Excel、PDF、TXT、CSV 等文件。
- 后端会读取文件内容，并把内容保存到数据库。
- 文件内容会进入 Chroma 向量库，后续提问时可以被检索出来。
- 可以接入阿里千问大模型 API。
- 可以保存一部分用户长期记忆，例如用户偏好、项目背景。
- 可以通过后端接口生成 Word 或 Excel 文件。

但当前版本还不是完整自主智能体。它现在主要是：

```text
用户提问
  -> 后端提前找出相关文件、记忆、历史对话
  -> 把这些上下文交给千问
  -> 千问生成回答
```

真正的自主智能体会是：

```text
用户提出目标
  -> 大模型自己判断要调用哪个工具
  -> 工具执行
  -> 大模型观察工具结果
  -> 继续调用工具或输出最终结果
```

后续升级就是要把项目从“文件问答助手”升级成“能自主调用工具的办公智能体”。

## 2. 项目目录结构

核心目录如下：

```text
app/                  后端代码
  main.py             FastAPI 应用入口
  api/                后端 API 路由
  core/               配置和千问模型初始化
  db/                 数据库连接和数据表模型
  services/           业务逻辑
  tools/              文件读取、文件生成、办公工具
  memory/             长期记忆和向量检索
  agents/             智能体提示词和消息组织
  schemas/            API 请求和响应的数据格式

frontend/             前端 React 页面
  src/App.tsx         主页面
  src/api.ts          调后端接口的方法
  src/styles.css      页面样式

tests/                后端测试
storage/              运行时生成的数据，通常不提交到 Git
```

## 3. 用户使用时的整体流程

### 3.1 启动系统

后端启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

前端启动：

```powershell
cd frontend
npm run dev -- --port 5173
```

浏览器打开：

```text
http://localhost:5173
```

### 3.2 上传文件流程

用户在前端上传文件后，流程是：

```text
前端 App.tsx
  -> 调用 frontend/src/api.ts 里的 uploadFile
  -> 请求后端 POST /api/files/upload
  -> app/api/files.py 接收文件
  -> app/services/document_service.py 保存文件
  -> app/tools/file_reader.py 读取文件内容
  -> FileRecord 写入 SQLite
  -> 文件内容切块后写入 Chroma 向量库
  -> 返回文件 ID、文件名、内容预览
```

简单说：上传文件后，系统会把文件保存起来、解析成文本、存数据库、建立检索索引。

### 3.3 聊天提问流程

用户输入问题后，流程是：

```text
前端 App.tsx
  -> 调用 frontend/src/api.ts 里的 sendChat
  -> 请求后端 POST /api/chat
  -> app/api/chat.py 接收请求
  -> app/services/chat_service.py 处理聊天
  -> 检索用户选择的文件
  -> 检索长期记忆
  -> 检索 Chroma 中相关文件片段
  -> 读取最近聊天历史
  -> app/agents/office_agent.py 组装提示词
  -> app/core/qwen_llm.py 创建千问模型
  -> 调用千问 API
  -> 保存用户消息和助手回复
  -> 必要时更新长期记忆
  -> 返回回答给前端
```

简单说：现在是后端先准备上下文，再让大模型回答。

### 3.4 记忆流程

记忆分两部分：

```text
SQLite：保存记忆原文
Chroma：保存记忆向量，方便语义检索
```

如果用户说了类似：

```text
我叫张三
我以后喜欢用表格输出
我的项目叫客户分析平台
```

系统会尝试把这类信息保存为长期记忆。后续聊天时，会先根据用户问题检索相关记忆，再放进大模型上下文里。

### 3.5 生成 Word / Excel 流程

当前后端已经有生成文件能力：

```text
POST /api/files/export
```

流程是：

```text
用户或程序传入 kind、filename、content
  -> app/api/files.py 接收请求
  -> app/tools/output_tools.py 生成 Word 或 Excel
  -> TaskArtifact 写入数据库
  -> 返回 download_url
```

目前这个能力还没有接入前端按钮，也还没有接入 Agent 自动调用。

## 4. 后端代码说明

### app/main.py

FastAPI 应用入口。

它负责：

- 创建 FastAPI 应用。
- 配置跨域，让前端可以访问后端。
- 注册三个 API 模块：
  - `/api/chat`
  - `/api/files`
  - `/api/memory`
- 启动时初始化数据库表。
- 提供 `/health` 健康检查接口。

### app/core/config.py

读取配置。

主要配置包括：

- `DASHSCOPE_API_KEY`：阿里千问 API Key。
- `QWEN_MODEL`：默认模型，例如 `qwen-plus`。
- `QWEN_BASE_URL`：千问兼容 OpenAI 的接口地址。
- `DATABASE_URL`：SQLite 数据库地址。
- `UPLOAD_DIR`：上传文件保存目录。
- `VECTOR_DIR`：Chroma 向量库目录。
- `ARTIFACT_DIR`：生成 Word / Excel 文件的目录。

### app/core/qwen_llm.py

创建千问聊天模型。

项目使用 `langchain-openai` 里的 `ChatOpenAI`，但把 `base_url` 指向阿里千问兼容 OpenAI 的地址。

这样 LangChain 就可以像调用 OpenAI 模型一样调用千问。

### app/db/database.py

数据库基础设施。

它负责：

- 创建 SQLAlchemy Engine。
- 创建数据库 Session。
- 提供 `get_db()` 给 API 使用。
- 提供 `init_db()` 创建数据表。

### app/db/models.py

数据库表定义。

当前主要有：

- `FileRecord`：上传文件记录。
- `ChatMessage`：聊天记录。
- `MemoryRecord`：长期记忆。
- `TaskArtifact`：生成的 Word / Excel 文件记录。

### app/api/chat.py

聊天接口。

接口：

```text
POST /api/chat
```

它只负责接收请求，然后交给 `ChatService` 处理。

### app/api/files.py

文件接口。

主要接口：

- `POST /api/files/upload`：上传文件。
- `GET /api/files`：查看已上传文件。
- `POST /api/files/export`：生成 Word / Excel。
- `GET /api/files/artifacts/{id}/download`：下载生成文件。

### app/api/memory.py

记忆接口。

主要接口：

```text
GET /api/memory
```

用于查看当前系统保存的长期记忆。

### app/schemas/chat.py

聊天接口的数据格式。

`ChatRequest` 表示前端发给后端的数据：

- `message`：用户输入。
- `session_id`：会话 ID。
- `file_ids`：用户选择的文件 ID。

`ChatResponse` 表示后端返回给前端的数据：

- `answer`：模型回答。
- `session_id`：会话 ID。
- `used_file_ids`：本次使用的文件 ID。
- `memories`：检索到的记忆。

### app/schemas/files.py

文件相关接口的数据格式。

包括：

- `FileInfo`：文件信息。
- `ExportRequest`：生成文件请求。
- `ArtifactInfo`：生成文件结果。

### app/services/document_service.py

处理上传文件。

它负责：

- 保存上传文件到 `storage/uploads`。
- 调用 `file_reader.py` 提取文本。
- 把文件记录写入 SQLite。
- 把文本切块后写入 Chroma，方便后续检索。

### app/services/chat_service.py

当前聊天核心逻辑。

它负责：

- 根据 `file_ids` 查用户选择的文件。
- 根据用户问题检索长期记忆。
- 根据用户问题检索已上传文件片段。
- 读取最近聊天历史。
- 调用 `office_agent.py` 组装提示词。
- 调用千问模型。
- 保存聊天记录。
- 尝试更新长期记忆。

这是后续升级的重点文件。升级后，它会从“直接调用 LLM”变成“调用 AgentExecutor”。

### app/tools/file_reader.py

读取不同格式文件。

支持：

- `.txt`
- `.md`
- `.csv`
- `.xlsx`
- `.xlsm`
- `.docx`
- `.pdf`

它会把这些文件尽量转成纯文本，方便大模型理解。

### app/tools/output_tools.py

生成办公文件。

当前支持：

- `generate_word()`：根据文本生成 Word。
- `generate_excel()`：根据文本生成 Excel。

生成的文件会放到 `storage/artifacts`。

### app/tools/office_tools.py

LangChain 工具定义。

当前已经有一些工具雏形：

- 搜索长期记忆。
- 保存长期记忆。
- 搜索已上传文件。
- 列出已上传文件。

但是这些工具目前还没有真正接入 AgentExecutor，所以大模型还不能自主调用它们。

### app/memory/store.py

长期记忆管理。

它负责：

- 新增记忆。
- 搜索记忆。
- 从用户对话中简单判断是否要保存记忆。

### app/memory/vector_store.py

Chroma 向量库管理。

它负责：

- 初始化 Chroma。
- 把长期记忆写入向量库。
- 把文件内容块写入向量库。
- 根据用户问题检索相关记忆或文件片段。

当前使用的是一个简单的 `HashEmbedding`，优点是本地可跑、不依赖额外模型；缺点是语义理解能力不如真正的 embedding 模型。

### app/agents/office_agent.py

当前只是“提示词和消息组装器”。

它负责把这些内容拼成给大模型看的消息：

- 系统提示词。
- 相关长期记忆。
- 用户选择的文件内容。
- 检索到的文件片段。
- 最近聊天历史。
- 当前用户问题。

后续升级后，这里会改成真正的 Agent Prompt。

## 5. 前端代码说明

### frontend/src/main.tsx

React 应用入口。

它把 `App` 组件挂载到网页上的 `root` 节点。

### frontend/src/App.tsx

主页面。

它负责：

- 展示聊天消息。
- 输入用户问题。
- 上传文件。
- 展示已上传文件列表。
- 选择本次要使用的文件。
- 展示长期记忆列表。
- 调用后端聊天接口。

### frontend/src/api.ts

前端请求后端的封装。

包括：

- `sendChat()`：发送聊天消息。
- `uploadFile()`：上传文件。
- `listFiles()`：获取文件列表。
- `listMemories()`：获取记忆列表。

### frontend/src/styles.css

页面样式。

它定义了：

- 左侧文件栏。
- 记忆栏。
- 中间聊天区。
- 底部输入框。
- 移动端适配。

## 6. 测试说明

当前测试在 `tests/` 目录。

### tests/test_file_reader.py

测试文件读取能力：

- TXT 读取。
- Word 读取。
- Excel 读取。

### tests/test_memory_store.py

测试长期记忆和 Chroma 检索：

- 添加记忆。
- 搜索记忆。
- 写入和检索文件片段。

### tests/test_chat_service.py

测试聊天服务会把文件内容交给大模型。

这里使用了假的 LLM，不会真实调用千问 API。

### tests/test_output_tools.py

测试 Word 和 Excel 生成功能。

## 7. 当前系统的主要不足

当前系统还不是完整自主智能体，主要差距是：

- 大模型不能自己决定调用哪个工具。
- 生成 Word / Excel 的能力还没有接入对话流程。
- 前端还不能直接展示生成文件下载按钮。
- Excel 分析能力还比较基础。
- 没有记录每次 Agent 调用了哪些工具。

下一步升级目标就是补齐这些能力。

## 8. 升级后的目标效果

升级后，希望用户可以直接说：

```text
读取我上传的销售表，找出销售额下降最大的 3 个区域，生成一份 Word 分析报告。
```

系统会自动：

```text
1. 查找已上传文件
2. 读取文件内容
3. 分析 Excel
4. 生成报告内容
5. 调用工具生成 Word
6. 返回下载链接
```

这才是更接近“智能体自动办公”的形态。
