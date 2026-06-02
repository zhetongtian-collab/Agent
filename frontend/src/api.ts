export type FileInfo = {
  id: number;
  filename: string;
  content_type: string | null;
  created_at: string;
  preview: string;
};

export type MemoryInfo = {
  id: number;
  content: string;
  source: string;
  created_at: string;
};

export type ChatResponse = {
  answer: string;
  session_id: string;
  used_file_ids: number[];
  memories: string[];
  artifacts: ArtifactInfo[];
};

export type ArtifactInfo = {
  id: number;
  kind: string;
  path?: string;
  download_url: string;
  absolute_download_url?: string;
  metadata?: Record<string, unknown>;
};

export type TaskStepStatus = "preparing" | "running" | "success" | "failed";

export type TaskStep = {
  id: string;
  title: string;
  status: TaskStepStatus;
  tool_name?: string;
  detail?: string;
};

export async function sendChat(message: string, fileIds: number[], sessionId = "default"): Promise<ChatResponse> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, file_ids: fileIds, session_id: sessionId })
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export type ChatStreamEvent =
  | { type: "token"; content: string }
  | { type: "artifact"; artifact: ArtifactInfo }
  | { type: "plan"; steps: TaskStep[] }
  | { type: "step"; step: TaskStep }
  | { type: "done"; answer: string; artifacts: ArtifactInfo[] }
  | { type: "error"; message: string };

export async function streamChat(
  message: string,
  fileIds: number[],
  onEvent: (event: ChatStreamEvent) => void,
  sessionId = "default"
): Promise<void> {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, file_ids: fileIds, session_id: sessionId })
  });
  if (!response.ok || !response.body) {
    throw new Error(await response.text());
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      onEvent(JSON.parse(line.slice(6)) as ChatStreamEvent);
    }
  }
}

export async function uploadFile(file: File): Promise<FileInfo> {
  const data = new FormData();
  data.append("file", file);
  const response = await fetch("/api/files/upload", { method: "POST", body: data });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function listFiles(): Promise<FileInfo[]> {
  const response = await fetch("/api/files");
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function deleteFile(fileId: number): Promise<void> {
  const response = await fetch(`/api/files/${fileId}`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(await response.text());
  }
}

export async function listMemories(): Promise<MemoryInfo[]> {
  const response = await fetch("/api/memory");
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function deleteMemory(memoryId: number): Promise<void> {
  const response = await fetch(`/api/memory/${memoryId}`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(await response.text());
  }
}
