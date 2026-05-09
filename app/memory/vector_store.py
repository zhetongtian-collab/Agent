from pathlib import Path
import hashlib
import math
import re

import chromadb

from app.core.config import settings


class HashEmbedding:
    def __init__(self, dimensions: int = 256):
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class VectorStore:
    def __init__(self, persist_dir: Path | None = None):
        self.persist_dir = Path(persist_dir or settings.vector_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.embedding = HashEmbedding()
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.memories = self.client.get_or_create_collection("memories")
        self.documents = self.client.get_or_create_collection("documents")

    def upsert_memory(self, memory_id: int, vector_id: str, content: str) -> None:
        self.memories.upsert(
            ids=[vector_id],
            documents=[content],
            embeddings=[self.embedding.embed(content)],
            metadatas=[{"memory_id": memory_id}],
        )

    def search_memories(self, query: str, limit: int = 5) -> list[dict]:
        result = self.memories.query(query_embeddings=[self.embedding.embed(query)], n_results=limit)
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        return [{"content": doc, **(meta or {})} for doc, meta in zip(documents, metadatas, strict=False)]

    def upsert_document_chunks(self, file_id: int, filename: str, chunks: list[str]) -> None:
        if not chunks:
            return
        ids = [f"file-{file_id}-{index}" for index, _ in enumerate(chunks)]
        self.documents.upsert(
            ids=ids,
            documents=chunks,
            embeddings=[self.embedding.embed(chunk) for chunk in chunks],
            metadatas=[{"file_id": file_id, "filename": filename} for _ in chunks],
        )

    def delete_document_chunks(self, file_id: int) -> None:
        self.documents.delete(where={"file_id": file_id})

    def search_documents(self, query: str, limit: int = 5, file_ids: list[int] | None = None) -> list[dict]:
        where = {"file_id": {"$in": file_ids}} if file_ids else None
        result = self.documents.query(query_embeddings=[self.embedding.embed(query)], n_results=limit, where=where)
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        return [{"content": doc, **(meta or {})} for doc, meta in zip(documents, metadatas, strict=False)]
