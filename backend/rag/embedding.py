"""
Embedding 客户端：调硅基流动的 BAAI/bge-m3 把文本变成向量（第 7 周核心）

为什么用硅基流动：DeepSeek 不提供 Embedding API；硅基流动免费额度足够学习期，
bge-m3 是中文语义检索的主流开源模型（1024 维）。

⚠️ 最重要的坑（面试可讲）：入库和查询必须用同一个 Embedding 模型。
不同模型的向量空间完全不同，混用后相似度全是错的、且不报错——
所以这里把「向量化」收敛成唯一入口，入库和检索都从这拿向量。
"""

import os

import httpx
from dotenv import load_dotenv

# 本模块在 import 时就读配置，必须自己确保 .env 已加载（main.py 的 load_dotenv 来不及）
load_dotenv()

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_URL = "https://api.siliconflow.cn/v1/embeddings"

BATCH_SIZE = 16  # 每次请求最多带多少条文本（官方限制 32，留余量）


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量向量化：自动分批调 API，返回与输入顺序一致的向量列表"""
    if not SILICONFLOW_API_KEY or SILICONFLOW_API_KEY.startswith("sk-xxxx"):
        raise RuntimeError(
            "未配置硅基流动 Key：请在 backend/.env 填入 SILICONFLOW_API_KEY（siliconflow.cn 免费注册）"
        )
    if not texts:
        return []

    vectors: list[list[float]] = []
    with httpx.Client(timeout=httpx.Timeout(30.0, read=120.0)) as client:
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start : start + BATCH_SIZE]
            resp = client.post(
                EMBEDDING_URL,
                headers={"Authorization": f"Bearer {SILICONFLOW_API_KEY}"},
                json={"model": EMBEDDING_MODEL, "input": batch},
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Embedding 接口返回 {resp.status_code}: {resp.text[:200]}")
            data = resp.json()["data"]
            # API 按 index 返回，保险起见按 index 排序后再取值
            data.sort(key=lambda item: item["index"])
            vectors.extend(item["embedding"] for item in data)
    return vectors


def embed_query(text: str) -> list[float]:
    """单条查询向量化（检索时用）"""
    return embed_texts([text])[0]
