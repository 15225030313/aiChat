"""
知识库元数据存储（SQLite）

设计说明：
- documents 表：文档级信息，管理页列表用
- chunks 表：分片文本，第 7 周向量化入库 Chroma 的数据来源；
  表里预留 vectorized 标记，接入 Chroma 后可标记同步状态
- 原始上传文件存 uploads/ 目录，便于以后重新解析
"""

import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "kb_data.sqlite3")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                vectorized INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL
            );
            """
        )


# 启动即建表
init_db()


def add_document(filename: str, size_bytes: int, chunks: list[str]) -> int:
    """写入文档记录 + 全部分片，返回文档 id"""
    now = datetime.now().isoformat(timespec="seconds")
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO documents (filename, size_bytes, chunk_count, created_at) VALUES (?, ?, ?, ?)",
            (filename, size_bytes, len(chunks), now),
        )
        doc_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO chunks (doc_id, chunk_index, text) VALUES (?, ?, ?)",
            [(doc_id, i, c) for i, c in enumerate(chunks)],
        )
    return doc_id


def list_documents() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, filename, size_bytes, chunk_count, vectorized, created_at "
            "FROM documents ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_chunks(doc_id: int) -> list[str]:
    """按片号顺序取某文档的全部分片（第7周向量化时用）"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT text FROM chunks WHERE doc_id = ? ORDER BY chunk_index", (doc_id,)
        ).fetchall()
    return [r["text"] for r in rows]


def get_doc_filename(doc_id: int) -> str | None:
    """查文档名（检索结果溯源展示用）"""
    with _conn() as conn:
        row = conn.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return row["filename"] if row else None


def mark_vectorized(doc_id: int) -> None:
    """向量化完成后打标记"""
    with _conn() as conn:
        conn.execute("UPDATE documents SET vectorized = 1 WHERE id = ?", (doc_id,))


def get_unvectorized_documents() -> list[dict]:
    """所有还没向量化的文档（管理页「一键向量化」用）"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, filename, chunk_count FROM documents WHERE vectorized = 0 ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_document(doc_id: int) -> bool:
    """删除文档及其分片，返回是否确实删了东西"""
    with _conn() as conn:
        cur = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    return cur.rowcount > 0


def clear_documents() -> int:
    """清空知识库，返回删除的文档数"""
    with _conn() as conn:
        (count,) = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM documents")
    return count


def save_upload_file(filename: str, content: bytes) -> str:
    """原始文件落盘 uploads/，返回保存路径"""
    safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
    path = os.path.join(UPLOAD_DIR, safe_name)
    with open(path, "wb") as f:
        f.write(content)
    return path
