"""
检索评估脚本（第 8 周：RAG 调优的量化依据）

评估思路（无标注数据时的标准做法）：
1. 从向量库里随机抽样 N 个分片；
2. 每个分片截取开头 50 字当作「模拟用户问题」（用户的问题本来就是原文的口语化变体，
   截取片段是最接近真实场景的无标注构造法）；
3. 分别用「纯向量 Top5」和「向量 Top20 + Rerank Top5」检索，看目标分片是否被召回；
4. 输出两种方案的 Top5 命中率对比 —— 这就是简历上「检索准确率提升 X%」的数据来源。

命中判定：目标分片的 (doc_id, chunk_index) 出现在结果里；
容差 ±1 片（相邻片因 overlap 重叠，内容高度相似，召回相邻片同样可用）。

运行：python -m rag.evaluate --sample 20 --seed 42
"""

import argparse
import random
import time

from rag import kb_store, vector_store
from rag.rerank import rerank


def build_cases(sample_n: int, seed: int, doc_id: int | None) -> list[dict]:
    """从已向量化的文档中抽样评估用例"""
    docs = [d for d in kb_store.list_documents() if d["vectorized"]]
    if doc_id:
        docs = [d for d in docs if d["id"] == doc_id]
    if not docs:
        raise SystemExit("没有已向量化的文档，请先上传并向量化")

    pool: list[dict] = []
    for d in docs:
        for idx, text in enumerate(kb_store.get_chunks(d["id"])):
            pool.append({"doc_id": d["id"], "chunk_index": idx, "text": text})

    rng = random.Random(seed)
    sample_n = min(sample_n, len(pool))
    return rng.sample(pool, sample_n)


def is_hit(target: dict, hits: list[dict], tolerance: int = 1) -> bool:
    return any(
        h["doc_id"] == target["doc_id"]
        and abs(h["chunk_index"] - target["chunk_index"]) <= tolerance
        for h in hits
    )


def make_query(text: str) -> str:
    """模拟用户问题：截取分片开头 50 字（去掉目录点线等噪声）"""
    q = text[:50].replace(".", " ").strip()
    return q or text[:50]


def evaluate(sample_n: int, seed: int, doc_id: int | None) -> None:
    cases = build_cases(sample_n, seed, doc_id)
    print(f"评估样本：{len(cases)} 个分片 ｜ 命中容差：相邻 ±1 片\n")
    print(f"{'#':>3} {'目标(doc:片)':<14} {'向量Top5':<8} {'精排Top5':<8} {'检索ms':>7} {'重排ms':>7}")
    print("-" * 56)

    vec_hits = 0
    rr_hits = 0
    retrieve_ms_total = 0.0
    rerank_ms_total = 0.0

    for i, case in enumerate(cases, start=1):
        query = make_query(case["text"])

        t0 = time.perf_counter()
        candidates = vector_store.search(query, top_n=20)
        t1 = time.perf_counter()
        reranked = rerank(query, candidates, top_n=5)
        t2 = time.perf_counter()
        retrieve_ms_total += (t1 - t0) * 1000
        rerank_ms_total += (t2 - t1) * 1000

        vec_ok = is_hit(case, candidates[:5])
        rr_ok = is_hit(case, reranked)
        vec_hits += vec_ok
        rr_hits += rr_ok

        target_label = f"{case['doc_id']}:{case['chunk_index']}"
        print(
            f"{i:>3} {target_label:<14} {'✓' if vec_ok else '✗':<8} {'✓' if rr_ok else '✗':<8} "
            f"{(t1 - t0) * 1000:>7.0f} {(t2 - t1) * 1000:>7.0f}"
        )

    n = len(cases)
    print("-" * 56)
    print(
        f"\n结果汇总（{n} 个样本）："
        f"\n  纯向量检索 Top5 命中率：{vec_hits}/{n} = {vec_hits / n * 100:.1f}%"
        f"\n  向量+Rerank  Top5 命中率：{rr_hits}/{n} = {rr_hits / n * 100:.1f}%"
        f"\n  平均检索耗时（含向量embedding）：{retrieve_ms_total / n:.0f}ms"
        f"\n  平均重排耗时：{rerank_ms_total / n:.0f}ms"
    )
    if rr_hits >= vec_hits:
        print(f"\n结论：Rerank 将 Top5 命中率提升了 {(rr_hits - vec_hits) / n * 100:+.1f} 个百分点")
    print("\n（换 --seed 或加大 --sample 多跑几次，结果更稳定；把这几个数字记进简历素材库）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG 检索评估：对比加/不加 Rerank 的 Top5 命中率")
    parser.add_argument("--sample", type=int, default=20, help="抽样分片数（默认 20）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子，保证可复现")
    parser.add_argument("--doc", type=int, default=None, help="只评估指定文档 id")
    args = parser.parse_args()
    evaluate(args.sample, args.seed, args.doc)
