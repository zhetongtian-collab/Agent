import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { FileText, Loader2, MessageSquare, Paperclip, RefreshCw, Send, Trash2, Upload } from "lucide-react";
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

export function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "请输入任务，或先上传 Word、Excel、PDF、TXT、CSV 文件。"
    }
  ]);
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [memories, setMemories] = useState<MemoryInfo[]>([]);
  const [selectedFileIds, setSelectedFileIds] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const messageEndRef = useRef<HTMLDivElement | null>(null);

  const selectedFiles = useMemo(
    () => files.filter((file) => selectedFileIds.includes(file.id)),
    [files, selectedFileIds]
  );

  useEffect(() => {
    refreshSidebars();
  }, []);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function refreshSidebars() {
    const [nextFiles, nextMemories] = await Promise.all([listFiles(), listMemories()]);
    setFiles(nextFiles);
    setMemories(nextMemories);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const message = input.trim();
    if (!message || busy) return;

    const assistantId = crypto.randomUUID();
    setInput("");
    setBusy(true);
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", content: message },
      { id: assistantId, role: "assistant", content: "" }
    ]);

    try {
      await streamChat(message, selectedFileIds, (event) => {
        if (event.type === "token") {
          updateAssistantMessage(assistantId, (item) => ({ ...item, content: item.content + event.content }));
        } else if (event.type === "artifact") {
          updateAssistantMessage(assistantId, (item) => ({
            ...item,
            artifacts: appendArtifact(item.artifacts, event.artifact)
          }));
        } else if (event.type === "done") {
          updateAssistantMessage(assistantId, (item) => ({
            ...item,
            content: event.answer || item.content,
            artifacts: mergeArtifacts(item.artifacts, event.artifacts)
          }));
        } else if (event.type === "error") {
          updateAssistantMessage(assistantId, (item) => ({
            ...item,
            content: item.content || `请求失败：${event.message}`
          }));
        }
      });
      await refreshSidebars();
    } catch (error) {
      updateAssistantMessage(assistantId, (item) => ({ ...item, content: `请求失败：${String(error)}` }));
    } finally {
      setBusy(false);
    }
  }

  function updateAssistantMessage(id: string, updater: (message: Message) => Message) {
    setMessages((current) => current.map((message) => (message.id === id ? updater(message) : message)));
  }

  async function handleUpload(fileList: FileList | null) {
    const file = fileList?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const uploaded = await uploadFile(file);
      setFiles((current) => [uploaded, ...current]);
      setSelectedFileIds((current) => [...new Set([...current, uploaded.id])]);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDeleteFile(fileId: number) {
    await deleteFile(fileId);
    setFiles((current) => current.filter((file) => file.id !== fileId));
    setSelectedFileIds((current) => current.filter((id) => id !== fileId));
  }

  async function handleDeleteMemory(memoryId: number) {
    await deleteMemory(memoryId);
    setMemories((current) => current.filter((memory) => memory.id !== memoryId));
  }

  function toggleFile(id: number) {
    setSelectedFileIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
    );
  }

  return (
    <main className="workspace">
      <aside className="sidebar">
        <div className="brand">
          <MessageSquare size={22} />
          <span>LongChain Office</span>
        </div>

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
            <span>记忆</span>
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
            <h1>智能办公助手</h1>
            <p>{selectedFiles.length ? `已选择 ${selectedFiles.length} 个文件` : "未选择文件"}</p>
          </div>
          <div className="selected-files">
            {selectedFiles.map((file) => (
              <span key={file.id}>{file.filename}</span>
            ))}
          </div>
        </header>

        <div className="messages">
          {messages.map((message) => (
            <article key={message.id} className={`message ${message.role}`}>
              <div className="bubble">
                <div>{message.content}</div>
                {message.role === "assistant" && busy && !message.content ? (
                  <div className="thinking">
                    <Loader2 className="spin" size={18} />
                    正在处理
                  </div>
                ) : null}
                {message.artifacts?.length ? (
                  <div className="artifact-list">
                    {message.artifacts.map((artifact) => (
                      <a
                        key={`${artifact.kind}-${artifact.id}`}
                        className="artifact-link"
                        href={artifact.download_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <FileText size={16} />
                        下载{artifact.kind === "word" ? " Word" : " Excel"}文件
                      </a>
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
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="让智能体总结文件、分析表格、生成报告..."
            rows={1}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                handleSubmit(event);
              }
            }}
          />
          <button className="send-button" disabled={busy || !input.trim()} title="发送">
            <Send size={19} />
          </button>
        </form>
      </section>
    </main>
  );
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
