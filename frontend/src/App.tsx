import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  FileText,
  Loader2,
  MessageSquare,
  Paperclip,
  Plus,
  RefreshCw,
  Send,
  Trash2,
  Upload
} from "lucide-react";
import {
  ArtifactInfo,
  FileInfo,
  MemoryInfo,
  deleteFile,
  deleteMemory,
  listFiles,
  listMemories,
  streamChat,
  uploadFile
} from "./api";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  artifacts?: ArtifactInfo[];
};

type Conversation = {
  id: string;
  title: string;
  messages: Message[];
  selectedFileIds: number[];
  draft: string;
  createdAt: string;
  updatedAt: string;
};

type ConversationState = {
  conversations: Conversation[];
  activeConversationId: string;
};

const STORAGE_KEY = "longchain.conversations.v1";
const ACTIVE_STORAGE_KEY = "longchain.activeConversationId.v1";
const UNTITLED_TITLE = "新对话";
const WELCOME_TEXT = "请输入任务，或先上传 Word、Excel、PDF、TXT、CSV 文件。";

export function App() {
  const [conversationState, setConversationState] = useState<ConversationState>(() => loadConversationState());
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [memories, setMemories] = useState<MemoryInfo[]>([]);
  const [busyConversationIds, setBusyConversationIds] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const messageEndRef = useRef<HTMLDivElement | null>(null);

  const { conversations, activeConversationId } = conversationState;
  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === activeConversationId) ?? conversations[0],
    [activeConversationId, conversations]
  );
  const selectedFileIds = activeConversation?.selectedFileIds ?? [];
  const selectedFiles = useMemo(
    () => files.filter((file) => selectedFileIds.includes(file.id)),
    [files, selectedFileIds]
  );
  const activeBusy = activeConversation ? busyConversationIds.includes(activeConversation.id) : false;

  useEffect(() => {
    refreshSidebars();
  }, []);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
    window.localStorage.setItem(ACTIVE_STORAGE_KEY, activeConversationId);
  }, [activeConversationId, conversations]);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeConversationId, activeConversation?.messages]);

  async function refreshSidebars() {
    const [nextFiles, nextMemories] = await Promise.all([listFiles(), listMemories()]);
    setFiles(nextFiles);
    setMemories(nextMemories);
  }

  function createNewConversation() {
    const conversation = createConversation();
    setConversationState((current) => ({
      conversations: [conversation, ...current.conversations],
      activeConversationId: conversation.id
    }));
  }

  function switchConversation(conversationId: string) {
    setConversationState((current) => ({ ...current, activeConversationId: conversationId }));
  }

  function deleteConversation(conversationId: string) {
    setBusyConversationIds((current) => current.filter((id) => id !== conversationId));
    setConversationState((current) => {
      const remaining = current.conversations.filter((conversation) => conversation.id !== conversationId);
      if (!remaining.length) {
        const conversation = createConversation();
        return { conversations: [conversation], activeConversationId: conversation.id };
      }
      return {
        conversations: remaining,
        activeConversationId:
          current.activeConversationId === conversationId ? remaining[0].id : current.activeConversationId
      };
    });
  }

  function updateActiveDraft(value: string) {
    const conversationId = activeConversation?.id;
    if (!conversationId) return;
    updateConversation(conversationId, (conversation) => ({ ...conversation, draft: value }));
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void submitMessage();
  }

  async function submitMessage() {
    if (!activeConversation) return;

    const conversationId = activeConversation.id;
    const message = activeConversation.draft.trim();
    const fileIds = [...activeConversation.selectedFileIds];
    if (!message || busyConversationIds.includes(conversationId)) return;

    const assistantId = crypto.randomUUID();
    setBusyConversationIds((current) => [...new Set([...current, conversationId])]);
    updateConversation(conversationId, (conversation) => {
      const hasUserMessage = conversation.messages.some((item) => item.role === "user");
      return {
        ...conversation,
        title: hasUserMessage ? conversation.title : buildConversationTitle(message),
        draft: "",
        updatedAt: new Date().toISOString(),
        messages: [
          ...conversation.messages,
          { id: crypto.randomUUID(), role: "user", content: message },
          { id: assistantId, role: "assistant", content: "" }
        ]
      };
    });

    try {
      await streamChat(
        message,
        fileIds,
        (event) => {
          if (event.type === "token") {
            updateAssistantMessage(conversationId, assistantId, (item) => ({
              ...item,
              content: item.content + event.content
            }));
          } else if (event.type === "artifact") {
            updateAssistantMessage(conversationId, assistantId, (item) => ({
              ...item,
              artifacts: appendArtifact(item.artifacts, event.artifact)
            }));
          } else if (event.type === "done") {
            updateAssistantMessage(conversationId, assistantId, (item) => ({
              ...item,
              content: event.answer || item.content,
              artifacts: mergeArtifacts(item.artifacts, event.artifacts)
            }));
          } else if (event.type === "error") {
            updateAssistantMessage(conversationId, assistantId, (item) => ({
              ...item,
              content: item.content || `请求失败：${event.message}`
            }));
          }
        },
        conversationId
      );
      await refreshSidebars();
    } catch (error) {
      updateAssistantMessage(conversationId, assistantId, (item) => ({
        ...item,
        content: item.content || `请求失败：${String(error)}`
      }));
    } finally {
      setBusyConversationIds((current) => current.filter((id) => id !== conversationId));
    }
  }

  function updateConversation(conversationId: string, updater: (conversation: Conversation) => Conversation) {
    setConversationState((current) => ({
      ...current,
      conversations: current.conversations.map((conversation) =>
        conversation.id === conversationId ? updater(conversation) : conversation
      )
    }));
  }

  function updateAssistantMessage(
    conversationId: string,
    messageId: string,
    updater: (message: Message) => Message
  ) {
    updateConversation(conversationId, (conversation) => ({
      ...conversation,
      updatedAt: new Date().toISOString(),
      messages: conversation.messages.map((message) => (message.id === messageId ? updater(message) : message))
    }));
  }

  async function handleUpload(fileList: FileList | null) {
    const file = fileList?.[0];
    const conversationId = activeConversation?.id;
    if (!file || !conversationId) return;
    setUploading(true);
    try {
      const uploaded = await uploadFile(file);
      setFiles((current) => [uploaded, ...current]);
      updateConversation(conversationId, (conversation) => ({
        ...conversation,
        selectedFileIds: [...new Set([...conversation.selectedFileIds, uploaded.id])],
        updatedAt: new Date().toISOString()
      }));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDeleteFile(fileId: number) {
    await deleteFile(fileId);
    setFiles((current) => current.filter((file) => file.id !== fileId));
    setConversationState((current) => ({
      ...current,
      conversations: current.conversations.map((conversation) => ({
        ...conversation,
        selectedFileIds: conversation.selectedFileIds.filter((id) => id !== fileId)
      }))
    }));
  }

  async function handleDeleteMemory(memoryId: number) {
    await deleteMemory(memoryId);
    setMemories((current) => current.filter((memory) => memory.id !== memoryId));
  }

  function toggleFile(id: number) {
    const conversationId = activeConversation?.id;
    if (!conversationId) return;
    updateConversation(conversationId, (conversation) => ({
      ...conversation,
      selectedFileIds: conversation.selectedFileIds.includes(id)
        ? conversation.selectedFileIds.filter((item) => item !== id)
        : [...conversation.selectedFileIds, id],
      updatedAt: new Date().toISOString()
    }));
  }

  return (
    <main className="workspace">
      <aside className="sidebar">
        <div className="brand">
          <MessageSquare size={22} />
          <span>LongChain Office</span>
        </div>

        <section className="panel conversation-panel">
          <div className="panel-title">
            <span>对话</span>
            <button className="icon-button" onClick={createNewConversation} title="新建对话">
              <Plus size={18} />
            </button>
          </div>
          <div className="conversation-list">
            {conversations.map((conversation) => (
              <div
                key={conversation.id}
                className={`conversation-row ${conversation.id === activeConversation?.id ? "selected" : ""}`}
              >
                <button
                  className="conversation-select"
                  onClick={() => switchConversation(conversation.id)}
                  title={conversation.title}
                >
                  <MessageSquare size={16} />
                  <span>{conversation.title}</span>
                  {busyConversationIds.includes(conversation.id) ? <Loader2 className="spin" size={15} /> : null}
                </button>
                <button
                  className="conversation-delete"
                  onClick={() => deleteConversation(conversation.id)}
                  title="删除对话"
                  aria-label={`删除 ${conversation.title}`}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-title">
            <span>文件</span>
            <button className="icon-button" onClick={() => fileInputRef.current?.click()} title="上传文件">
              {uploading ? <Loader2 className="spin" size={18} /> : <Upload size={18} />}
            </button>
          </div>
          <input
            ref={fileInputRef}
            className="hidden"
            type="file"
            accept=".docx,.xlsx,.xlsm,.pdf,.txt,.md,.csv"
            onChange={(event) => handleUpload(event.target.files)}
          />
          <div className="list">
            {files.map((file) => (
              <div key={file.id} className={`file-row ${selectedFileIds.includes(file.id) ? "selected" : ""}`}>
                <button className="file-select" onClick={() => toggleFile(file.id)} title={file.filename}>
                  <FileText size={17} />
                  <span>{file.filename}</span>
                </button>
                <button
                  className="file-delete"
                  onClick={() => handleDeleteFile(file.id)}
                  title="删除文件"
                  aria-label={`删除 ${file.filename}`}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        </section>

        <section className="panel memory-panel">
          <div className="panel-title">
            <span>长期记忆</span>
            <button className="icon-button" onClick={refreshSidebars} title="刷新">
              <RefreshCw size={17} />
            </button>
          </div>
          <div className="memory-list">
            {memories.map((memory) => (
              <div key={memory.id} className="memory-row">
                <p>{memory.content}</p>
                <button
                  className="memory-delete"
                  onClick={() => handleDeleteMemory(memory.id)}
                  title="删除记忆"
                  aria-label="删除记忆"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
        </section>
      </aside>

      <section className="chat">
        <header className="chat-header">
          <div>
            <h1>{activeConversation?.title ?? UNTITLED_TITLE}</h1>
            <p>{selectedFiles.length ? `已选择 ${selectedFiles.length} 个文件` : "未选择文件"}</p>
          </div>
          <div className="selected-files">
            {selectedFiles.map((file) => (
              <span key={file.id}>{file.filename}</span>
            ))}
          </div>
        </header>

        <div className="messages">
          {(activeConversation?.messages ?? []).map((message) => (
            <article key={message.id} className={`message ${message.role}`}>
              <div className="bubble">
                <div>{message.content}</div>
                {message.role === "assistant" && activeBusy && !message.content ? (
                  <div className="thinking">
                    <Loader2 className="spin" size={18} />
                    正在处理
                  </div>
                ) : null}
                {message.artifacts?.length ? (
                  <div className="artifact-list">
                    {message.artifacts.map((artifact) => (
                      <ArtifactView key={`${artifact.kind}-${artifact.id}`} artifact={artifact} />
                    ))}
                  </div>
                ) : null}
              </div>
            </article>
          ))}
          <div ref={messageEndRef} />
        </div>

        <form className="composer" onSubmit={handleSubmit}>
          <button type="button" className="icon-button" onClick={() => fileInputRef.current?.click()} title="添加附件">
            <Paperclip size={20} />
          </button>
          <textarea
            value={activeConversation?.draft ?? ""}
            onChange={(event) => updateActiveDraft(event.target.value)}
            placeholder="让智能体总结文件、分析表格、生成报告..."
            rows={1}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submitMessage();
              }
            }}
          />
          <button className="send-button" disabled={activeBusy || !activeConversation?.draft.trim()} title="发送">
            <Send size={19} />
          </button>
        </form>
      </section>
    </main>
  );
}

function ArtifactView({ artifact }: { artifact: ArtifactInfo }) {
  if (artifact.kind === "chart") {
    const title = getChartTitle(artifact);
    return (
      <div className="chart-artifact">
        <a className="chart-open-link" href={artifact.download_url} target="_blank" rel="noreferrer">
          <BarChart3 size={16} />
          打开图表
        </a>
        <img src={artifact.download_url} alt={title} />
      </div>
    );
  }

  return (
    <a className="artifact-link" href={artifact.download_url} target="_blank" rel="noreferrer">
      <FileText size={16} />
      下载{artifact.kind === "word" ? " Word" : " Excel"}文件
    </a>
  );
}

function getChartTitle(artifact: ArtifactInfo): string {
  const title = artifact.metadata?.title;
  return typeof title === "string" && title.trim() ? title : "Excel 数据图表";
}

function loadConversationState(): ConversationState {
  const fallback = createConversation();
  try {
    const rawConversations = window.localStorage.getItem(STORAGE_KEY);
    const parsed = rawConversations ? (JSON.parse(rawConversations) as Conversation[]) : [];
    const conversations = parsed.length ? parsed.map(normalizeConversation) : [fallback];
    const storedActiveId = window.localStorage.getItem(ACTIVE_STORAGE_KEY);
    const activeConversationId = conversations.some((conversation) => conversation.id === storedActiveId)
      ? storedActiveId!
      : conversations[0].id;
    return { conversations, activeConversationId };
  } catch {
    return { conversations: [fallback], activeConversationId: fallback.id };
  }
}

function normalizeConversation(conversation: Conversation): Conversation {
  return {
    ...conversation,
    title: conversation.title || UNTITLED_TITLE,
    messages: conversation.messages?.length ? conversation.messages : [createWelcomeMessage()],
    selectedFileIds: conversation.selectedFileIds ?? [],
    draft: conversation.draft ?? "",
    createdAt: conversation.createdAt ?? new Date().toISOString(),
    updatedAt: conversation.updatedAt ?? new Date().toISOString()
  };
}

function createConversation(): Conversation {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    title: UNTITLED_TITLE,
    messages: [createWelcomeMessage()],
    selectedFileIds: [],
    draft: "",
    createdAt: now,
    updatedAt: now
  };
}

function createWelcomeMessage(): Message {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    content: WELCOME_TEXT
  };
}

function buildConversationTitle(message: string): string {
  const title = message.replace(/\s+/g, " ").trim();
  return title.length > 18 ? `${title.slice(0, 18)}...` : title || UNTITLED_TITLE;
}

function appendArtifact(current: ArtifactInfo[] | undefined, artifact: ArtifactInfo): ArtifactInfo[] {
  return mergeArtifacts(current, [artifact]);
}

function mergeArtifacts(current: ArtifactInfo[] | undefined, incoming: ArtifactInfo[] | undefined): ArtifactInfo[] {
  const result = [...(current ?? [])];
  for (const artifact of incoming ?? []) {
    if (!result.some((item) => item.id === artifact.id && item.kind === artifact.kind)) {
      result.push(artifact);
    }
  }
  return result;
}
