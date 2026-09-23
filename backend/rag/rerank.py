"""
Rerank 重排（第 8 周核心：RAG 调优的标配答案）

为什么召回后还要重排（面试必考）：
- 向量检索是「粗排」：双塔结构，问题和文档各自独立编码成向量再算相似度，
  快（可以离线建索引）但排序精度有限；
- Rerank 是「精排」：交叉编码器把「问题+文档」拼在一起送进模型逐对打分，
  精度高但慢——所以只能对少量候选（Top20）用。
- 先粗排缩小范围、再精排挑最好的，是效果与成本的经典平衡（两级漏斗）。

接口：硅基流动 /v1/rerank，模型 BAAI/bge-reranker-v2-m3（免费额度）。
"""

import os

import httpx
from dotenv import load_dotenv

load_dotenv()

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_URL = "https://api.siliconflow.cn/v1/rerank"


def rerank(question: str, hits: list[dict], top_n: int = 5) -> list[dict]:
    """
    对召回的候选分片精排，返回按相关度重排后的前 top_n 条。

    输入/输出都是 vector_store.search() 的 hit 结构，
    额外在每条上挂 rerank_score（交叉编码器相关分，仅供参考展示）。
    重排失败时降级：直接返回原顺序前 top_n（粗排结果兜底，问答不中断）。
    """
    if not hits:
        return []
    if not SILICONFLOW_API_KEY or SILICONFLOW_API_KEY.startswith("sk-xxxx"):
        return hits[:top_n]

    try:
        with httpx.Client(timeout=httpx.Timeout(20.0, read=60.0)) as client:
            resp = client.post(
                RERANK_URL,
                headers={"Authorization": f"Bearer {SILICONFLOW_API_KEY}"},
                json={
                    "model": RERANK_MODEL,
                    "query": question,
                    "documents": [h["text"] for h in hits],
                    "top_n": top_n,
                    "return_documents": False,
                },
            )
        if resp.status_code != 200:
            return hits[:top_n]  # 降级兜底

        results = resp.json()["results"]  # [{index, relevance_score}]
        reranked: list[dict] = []
        for r in results:
            hit = dict(hits[r["index"]])
            hit["rerank_score"] = round(r["relevance_score"], 4)
            reranked.append(hit)
        return reranked
    except Exception:
        return hits[:top_n]  # 网络异常等一律降级，不让问答挂掉
