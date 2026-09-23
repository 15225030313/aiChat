"""
Chroma 向量库封装（第 7 周核心）

Chroma 是本地零配置的向量数据库：PersistentClient 落盘到 chroma_data/，
重启服务数据不丢。核心操作就三个：add（入库）/ query（检索）/ delete（删除）。

设计：
- 单一 collection「kb_chunks」，用 metadata.doc_id 区分文档 —— 现阶段一个知识库足够，
  将来多知识库时用 metadata.kb_id 或按库分 collection 扩展
- 入库/查询都传「预计算好的向量」而不是让 Chroma 调默认 embedding 函数，
  保证入库和查询走同一个 bge-m3（见 embedding.py 里的坑位说明）
"""

import os

import chromadb

from rag.embedding import embed_query, embed_texts
from rag import kb_store

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "chroma_data")

_client = chromadb.PersistentClient(path=CHROMA_DIR)
# cosine 空间：用余弦相似度，语义检索的标准选择
_collection = _client.get_or_create_collection(name="kb_chunks", metadata={"hnsw:space": "cosine"})


def vectorize_document(doc_id: int) -> int:
    """
    把 SQLite 里某文档的全部分片向量化入 Chroma，并标记 vectorized=1。
    返回向量化分片数。失败时文档保持「待处理」状态，可重试。
    """
    chunks = kb_store.get_chunks(doc_id)
    if not chunks:
        raise ValueError(f"文档 {doc_id} 没有可向量化的分片")

    vectors = embed_texts(chunks)
    _collection.add(
        ids=[f"{doc_id}:{i}" for i in range(len(chunks))],
        embeddings=vectors,
        documents=chunks,
        metadatas=[{"doc_id": doc_id, "chunk_index": i} for i in range(len(chunks))],
    )
    kb_store.mark_vectorized(doc_id)
    return len(chunks)


def delete_doc(doc_id: int) -> None:
    """删除某文档的全部分量（与 SQLite 删除保持同步）"""
    _collection.delete(where={"doc_id": doc_id})


def clear_all() -> None:
    """清空整个向量库（管理页「清空知识库」时同步调用）"""
    _client.delete_collection("kb")
    global _collection
    _collection = _client.get_or_create_collection(name="kb_chunks", metadata={"hnsw:space": "cosine"})


def search(question: str, top_n: int = 5) -> list[dict]:
    """
    语义检索：问题向量化 → 召回 TopN 最相似分片。

    返回 [{doc_id, filename, chunk_index, text, similarity}, ...]
    similarity = 1 - 余弦距离（Chroma 返回的是距离，越小越相似）。
    """
    if _collection.count() == 0:
        return []

    res = _collection.query(
        query_embeddings=[embed_query(question)],
        n_results=min(top_n, _collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    hits: list[dict] = []
    for i in range(len(res["ids"][0])):
        meta = res["metadatas"][0][i]
        doc_id = meta["doc_id"]
        hits.append(
            {
                "doc_id": doc_id,
                "filename": kb_store.get_doc_filename(doc_id) or f"文档{doc_id}",
                "chunk_index": meta["chunk_index"],
                "text": res["documents"][0][i],
                "similarity": round(1 - res["distances"][0][i], 4),
            }
        )
    # 相似度降序
    return sorted(hits, key=lambda h: h["similarity"], reverse=True)
