from pathlib import Path
import hashlib
import math
import re

import chromadb

from app.core.config import settings


# 基于哈希的简易文本向量器。
# 它不依赖外部 embedding 模型，而是把词语哈希到固定维度的向量里。
# 优点是本地即可运行、速度快；缺点是语义理解能力比真正的 embedding 模型弱。
class HashEmbedding:
    # 初始化一个非常轻量的哈希向量器。
    # dimensions 表示向量维度；维度越大，词语哈希碰撞越少，但占用空间也更多。
    def __init__(self, dimensions: int = 256):
        self.dimensions = dimensions

    # 把文本转换成固定长度的数字向量。
    # 做法是先提取中英文词，再对每个词做 sha256 哈希，
    # 根据哈希值决定它落到哪个维度上，最后做归一化，方便向量相似度比较。
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


# 向量数据库封装类。
# 负责连接本地 ChromaDB，并管理两个集合：
# memories 用于长期记忆检索，documents 用于上传文档片段检索。
# 业务层不直接操作 ChromaDB，而是通过这个类完成写入、删除和搜索。
class VectorStore:
    # 初始化向量数据库。
    # persist_dir 是 ChromaDB 的持久化目录，不传时使用配置里的 vector_dir。
    # 同时创建两个 collection：memories 保存长期记忆，documents 保存文档分块。
    def __init__(self, persist_dir: Path | None = None):
        self.persist_dir = Path(persist_dir or settings.vector_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.embedding = HashEmbedding()
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.memories = self.client.get_or_create_collection("memories")
        self.documents = self.client.get_or_create_collection("documents")

    # 新增或更新一条长期记忆的向量数据。
    # vector_id 是向量库中的唯一 ID，memory_id 是关系型数据库里的记录 ID；
    # content 会被转换成 embedding，metadata 用来把向量结果关联回数据库记录。
    def upsert_memory(self, memory_id: int, vector_id: str, content: str) -> None:
        self.memories.upsert(
            ids=[vector_id],
            documents=[content],
            embeddings=[self.embedding.embed(content)],
            metadatas=[{"memory_id": memory_id}],
        )

    # 从向量库中删除一条长期记忆。
    # 这里只删除 ChromaDB 里的向量数据，数据库记录的删除由 MemoryStore 负责。
    def delete_memory(self, vector_id: str) -> None:
        self.memories.delete(ids=[vector_id])

    # 在长期记忆 collection 里做相似度搜索。
    # query 会先被转换成向量，然后取最相似的 limit 条结果；
    # 返回值会把文档内容和 metadata 合并成普通 dict，方便业务层使用。
    def search_memories(self, query: str, limit: int = 5) -> list[dict]:
        result = self.memories.query(query_embeddings=[self.embedding.embed(query)], n_results=limit)
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        return [{"content": doc, **(meta or {})} for doc, meta in zip(documents, metadatas, strict=False)]

    # 把一个上传文件拆出的多个文本片段写入文档向量库。
    # 每个 chunk 都会生成一个稳定格式的 ID，并保存 file_id 和 filename，
    # 这样搜索结果可以知道来自哪个文件。
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

    # 删除某个文件对应的所有文档向量片段。
    # 当用户删除上传文件时调用，避免向量库还保留旧文件内容。
    def delete_document_chunks(self, file_id: int) -> None:
        self.documents.delete(where={"file_id": file_id})

    # 在上传文档的向量库里搜索相关片段。
    # 如果传入 file_ids，就只在这些文件范围内检索；
    # 否则会在所有已索引的文档片段中搜索，并返回内容和来源 metadata。
    def search_documents(self, query: str, limit: int = 5, file_ids: list[int] | None = None) -> list[dict]:
        where = {"file_id": {"$in": file_ids}} if file_ids else None
        result = self.documents.query(query_embeddings=[self.embedding.embed(query)], n_results=limit, where=where)
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        return [{"content": doc, **(meta or {})} for doc, meta in zip(documents, metadatas, strict=False)]
