# -*- coding: utf-8 -*-
"""检索评测：纯向量 vs 混合 vs 混合+重排 三组对比，指标 Recall@5 / MRR。

用法：
  python eval/scripts/run_retrieval.py                # 用 eval/dataset 标注
  python eval/scripts/run_retrieval.py --demo         # 用 examples/demo 示例标注（演示脚本用）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_common import (  # noqa: E402
    DATASET_DIR,
    chunks_to_job_ranking,
    jobs_map,
    load_jsonl,
    md_table,
    mrr,
    recall_at_k,
    save_result,
)
from embeddings import EmbeddingClient  # noqa: E402
from rag import HybridRetriever, JDVectorStore  # noqa: E402
from rerank import RerankClient  # noqa: E402
from eval_common import ROOT  # noqa: E402


def build_retriever(db_dir: Path, collection: str, with_rerank: bool) -> HybridRetriever:
    store = JDVectorStore(db_dir, collection=collection)
    return HybridRetriever(
        store, EmbeddingClient(),
        RerankClient() if with_rerank else None,
        cfg={"vector_k": 20, "bm25_k": 20, "rrf_k": 60, "rerank": {"enabled": with_rerank}},
    )


def eval_config(retriever: HybridRetriever, mode: str, use_rerank: bool,
                queries: list[dict], top_k: int = 5) -> dict:
    per_query = []
    recalls, mrrs, latencies = [], [], []
    for q in queries:
        t0 = time.monotonic()
        hits = retriever.search(q["query"], top_k=20, mode=mode, rerank=use_rerank)
        latencies.append((time.monotonic() - t0) * 1000)
        ranked = chunks_to_job_ranking(hits)
        relevant = set(q["relevant_job_ids"])
        r5 = recall_at_k(ranked, relevant, k=top_k)
        m = mrr(ranked, relevant)
        recalls.append(r5)
        mrrs.append(m)
        per_query.append({
            "query_id": q["query_id"], "query": q["query"],
            f"recall@{top_k}": round(r5, 3), "mrr": round(m, 3),
            "n_relevant": len(relevant),
        })
    n = max(1, len(queries))
    return {
        "recall": sum(recalls) / n,
        "mrr": sum(mrrs) / n,
        "avg_latency_ms": sum(latencies) / n,
        "per_query": per_query,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="使用示例标注（examples/demo/eval）")
    ap.add_argument("--jobs", default=None, help="覆盖 jobs.jsonl 路径")
    ap.add_argument("--db", default=None, help="Chroma 目录（默认先 ingest 再评测）")
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()

    if args.demo:
        base = ROOT / "examples" / "demo" / "eval"
        jobs_path = base / "jobs.jsonl"
        queries = load_jsonl(base / "retrieval_queries.jsonl")
        db_dir = Path(args.db) if args.db else ROOT / "runs" / "eval_demo_chroma"
        collection = "eval_demo"
    else:
        jobs_path = Path(args.jobs) if args.jobs else DATASET_DIR / "jobs.jsonl"
        queries = load_jsonl(DATASET_DIR / "retrieval_queries.jsonl")
        db_dir = Path(args.db) if args.db else ROOT / "data" / "eval_chroma"
        collection = "eval_jobs"
    if not queries or not all(q.get("query") and q.get("relevant_job_ids") for q in queries):
        print("❌ 检索标注为空或不完整。先完成标注（模板见 eval/README.md），或 --demo 用示例标注。")
        return

    # 为评测单独建库（不污染业务库）
    store = JDVectorStore(db_dir, collection=collection)
    store.reset()
    from rag import ingest_jobs_file
    stats = ingest_jobs_file(jobs_path, store, EmbeddingClient())
    print(f"评测库: {stats['jobs']} 条 JD → {stats['chunks']} chunks @ {db_dir}/{collection}")

    configs = [
        ("纯向量", "vector", False),
        ("混合(向量+BM25+RRF)", "hybrid", False),
        ("混合+重排", "hybrid", True),
    ]
    rows, details = [], []
    for name, mode, use_rerank in configs:
        retriever = build_retriever(db_dir, collection, with_rerank=use_rerank)
        res = eval_config(retriever, mode, use_rerank, queries, top_k=args.top_k)
        rows.append([name, f"{res['recall']:.3f}", f"{res['mrr']:.3f}",
                     f"{res['avg_latency_ms']:.0f}", len(queries)])
        for pq in res["per_query"]:
            details.append([name, pq["query_id"], pq["query"][:40],
                            pq[f"recall@{args.top_k}"], pq["mrr"]])

    title = "## 检索评测：纯向量 vs 混合 vs 混合+重排\n"
    meta = (
        f"\n- 数据集: `{jobs_path.relative_to(ROOT) if args.demo is False else jobs_path.name}`"
        f"（{stats['jobs']} 条 JD / {stats['chunks']} chunks）"
        f"\n- 查询数: {len(queries)}（人工标注） | 指标: Recall@{args.top_k}(job 级) / MRR"
        f"\n- 生成时间: {datetime.now().isoformat(timespec='seconds')}"
        + ("\n- ⚠️ 示例标注（demo），仅演示脚本流程，非正式评测\n" if args.demo else "\n")
    )
    table = md_table(["配置", f"Recall@{args.top_k}", "MRR", "平均耗时(ms)", "查询数"], rows)
    detail_table = md_table(["配置", "query_id", "query", f"recall@{args.top_k}", "mrr"], details)
    save_result("retrieval.md", title + meta + "\n" + table + "\n\n### 逐查询明细\n\n" + detail_table + "\n")


if __name__ == "__main__":
    main()
