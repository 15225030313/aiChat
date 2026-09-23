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

from rag import vector_store
from rag.kb_store import add_document, clear_documents, delete_document, list_documents, save_upload_file
from rag.parse import chunk_text, parse_file
from rag.rerank import rerank

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
    """知识库 id：不传/为 null 时走普通对话，传了就走 RAG 检索问答"""
    knowledge_base_id: int | None = None


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

    # 上传后立即向量化入 Chroma（分片少时秒级完成）
    vectorized = 0
    vector_error = ""
    try:
        vectorized = vector_store.vectorize_document(doc_id)
    except Exception as e:  # 向量化失败不阻塞上传，文档保持「待处理」可手动重试
        vector_error = str(e)

    result = {
        "id": doc_id,
        "filename": file.filename,
        "chunk_count": len(chunks),
        "text_length": len(text),
        "vectorized": vectorized,
    }
    if vector_error:
        result["vector_error"] = vector_error
    return result


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
    vector_store.delete_doc(doc_id)  # 同步删除 Chroma 里的向量
    return {"deleted": doc_id}


@app.delete("/api/kb/documents")
def kb_clear():
    count = clear_documents()
    vector_store.clear_all()  # 同步清空向量库
    return {"cleared": count}


@app.post("/api/kb/vectorize/{doc_id}")
def kb_vectorize(doc_id: int):
    """手动向量化：补处理上传时向量化失败/历史遗留的「待处理」文档"""
    try:
        count = vector_store.vectorize_document(doc_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"doc_id": doc_id, "vectorized": count}


RAG_SYSTEM_PROMPT = """你是一个企业知识库问答助手。请严格根据下面的参考资料回答用户问题，并在答案中用 [1]、[2] 这样的编号标注引用了哪条资料。如果参考资料中没有相关内容，请直接回答「知识库中没有找到相关资料」，不要编造。

参考资料：
{context}"""


def build_rag_context(question: str) -> tuple[str, list[dict]]:
    """
    RAG 检索两级漏斗：问题向量化 → Chroma 粗排召回 Top20 → Rerank 精排取 Top5。
    返回 (拼好的 context 文本, sources 元数据列表)。
    """
    candidates = vector_store.search(question, top_n=20)
    if not candidates:
        return "", []
    hits = rerank(question, candidates, top_n=5)

    blocks: list[str] = []
    sources: list[dict] = []
    for i, hit in enumerate(hits, start=1):
        # Rerank 命中时展示精排分，否则展示粗排余弦相似度
        score = hit.get("rerank_score", hit["similarity"])
        blocks.append(f"[{i}] （来源：{hit['filename']}，相关度 {score:.2f}）\n{hit['text']}")
        sources.append(
            {
                "index": i,
                "doc_id": hit["doc_id"],
                "filename": hit["filename"],
                "chunk_index": hit["chunk_index"],
                "similarity": score,
                # 截断展示用，点击角标时前端展示这段
                "snippet": hit["text"][:300],
            }
        )
    return "\n\n".join(blocks), sources


@app.post("/api/chat")
def chat(req: ChatRequest):
    """
    流式对话接口（SSE），双模式：
    - knowledge_base_id 为空：普通对话，直接透传 DeepSeek
    - 传了 kb id：先检索知识库，把参考片段拼进 system prompt 再流式回答；
      流的第一个事件是 {"type":"sources","sources":[...]}，前端用来渲染引用溯源
    """
    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY.startswith("sk-xxxx"):
        raise HTTPException(
            status_code=500,
            detail="未配置 API Key：请复制 backend/.env.example 为 backend/.env 并填入 DEEPSEEK_API_KEY",
        )

    msgs = [m.model_dump() for m in req.messages]
    sources: list[dict] = []

    if req.knowledge_base_id is not None:
        # RAG 模式：取最后一条用户消息作为检索问题
        question = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), "")
        if not question:
            raise HTTPException(status_code=400, detail="没有可检索的用户问题")
        context, sources = build_rag_context(question)
        if not context:
            raise HTTPException(status_code=400, detail="知识库为空或尚未向量化，请先在管理页上传/向量化文档")
        # RAG 的灵魂就这几行：检索结果以 system 角色注入，模型只能「开卷作答」
        msgs = [{"role": "system", "content": RAG_SYSTEM_PROMPT.format(context=context)}] + msgs

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": msgs,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    def stream_upstream():
        # RAG 模式：先推引用元数据事件，前端据此渲染 [1][2] 角标对应的来源
        if sources:
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources}, ensure_ascii=False)}\n\n"

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
