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
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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
