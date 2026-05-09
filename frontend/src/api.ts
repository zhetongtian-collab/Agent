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
