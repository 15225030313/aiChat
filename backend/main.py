"""
企业知识库AI问答系统 - 后端入口（阶段一：极简薄层）

职责只有一个：作为大模型 API 的流式中转代理。
- 前端永远不接触 API Key（安全红线）
- 后端持有密钥，把前端的对话请求转发给 DeepSeek，并把流式响应原样推回
- 后续 RAG / Function Calling 都在这个文件基础上扩展
"""

import json
import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from rag.kb_store import add_document, clear_documents, delete_document, list_documents, save_upload_file
from rag.parse import chunk_text, parse_file

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

app = FastAPI(title="AI知识库问答系统 - 后端")

# 跨域配置：开发阶段允许 Vite 默认端口
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@app.get("/api/health")
def health():
    """健康检查，前端/部署监控都用它"""
    return {"status": "ok", "model": DEEPSEEK_MODEL}


# ===== 知识库管理 API（阶段二：供管理页与后续 RAG 问答使用）=====

ALLOWED_SUFFIXES = {"pdf"}  # Word/TXT 解析为用户练习任务，完成后在此放开
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB


@app.post("/api/kb/upload")
async def kb_upload(file: UploadFile = File(...)):
    """上传文档 → 解析 → 分片 → 入库（第7周将在此链路后追加向量化）"""
    suffix = (file.filename or "").rsplit(".", 1)[-1].lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"暂不支持 .{suffix} 格式，当前仅支持 PDF")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="文件超过 10MB 上限")

    save_upload_file(file.filename or "unnamed.pdf", content)  # 原始文件留档
    try:
        text = parse_file_path_safe(file.filename or "", content)
        chunks = chunk_text(text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not chunks:
        raise HTTPException(status_code=400, detail="文档解析后没有可用文本（可能是扫描件/图片型PDF）")

    doc_id = add_document(file.filename or "unnamed.pdf", len(content), chunks)
    return {"id": doc_id, "filename": file.filename, "chunk_count": len(chunks), "text_length": len(text)}


def parse_file_path_safe(filename: str, content: bytes) -> str:
    """parse_file 只收路径，这里把上传内容落临时文件再解析"""
    import tempfile
    suffix = "." + filename.rsplit(".", 1)[-1].lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        return parse_file(tmp_path)
    finally:
        os.unlink(tmp_path)


@app.get("/api/kb/documents")
def kb_list():
    """文档列表（管理页）"""
    return list_documents()


@app.delete("/api/kb/documents/{doc_id}")
def kb_delete(doc_id: int):
    if not delete_document(doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"deleted": doc_id}


@app.delete("/api/kb/documents")
def kb_clear():
    return {"cleared": clear_documents()}


@app.post("/api/chat")
def chat(req: ChatRequest):
    """
    流式对话接口（SSE）

    前端 POST 过来对话历史，后端透传给 DeepSeek 的流式接口，
    再把 OpenAI 兼容格式的 SSE 数据一行行转发回去。
    """
    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY.startswith("sk-xxxx"):
        raise HTTPException(
            status_code=500,
            detail="未配置 API Key：请复制 backend/.env.example 为 backend/.env 并填入 DEEPSEEK_API_KEY",
        )

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [m.model_dump() for m in req.messages],
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    def stream_upstream():
        """逐块读取上游 SSE 并透传给前端"""
        with httpx.Client(timeout=httpx.Timeout(60.0, read=300.0)) as client:
            with client.stream(
                "POST",
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status_code != 200:
                    body = resp.read().decode("utf-8", errors="replace")
                    error_event = {"error": f"上游返回 {resp.status_code}: {body[:200]}"}
                    yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
                    return
                for chunk in resp.iter_text():
                    if chunk:
                        yield chunk

    return StreamingResponse(
        stream_upstream(),
        media_type="text/event-stream",
        headers={
            # 关键响应头：告诉浏览器/代理不要缓冲，逐字推给前端
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
