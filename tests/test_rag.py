# -*- coding: utf-8 -*-
"""RAG 核心测试：真 Chroma（Ephemeral，离线）+ 假 embedder/reranker。"""
from __future__ import annotations

import json
import re
import zlib

import chromadb
import pytest

from rag import (
    HybridRetriever,
    JDVectorStore,
    build_bm25_index,
    bm25_search,
    ingest_jobs_file,
    rrf_combine,
    tokenize_zh,
)


def _unique_collection() -> str:
    import uuid

    return f"jd_{uuid.uuid4().hex[:12]}"


class FakeEmbedder:
    """确定性词袋向量（crc32 散列），离线可复现。"""

    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * 16
            for tok in re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", t):
                v[zlib.crc32(tok.encode()) % 16] += 1.0
            out.append(v)
        return out

    def embed_query(self, text):
        return self.embed([text])[0]


class FakeReranker:
    """按关键词命中打分的假 cross-encoder。"""

    def __init__(self, keyword: str):
        self.keyword = keyword

    def rerank(self, query, documents, top_n=None):
        scored = sorted(
            range(len(documents)),
            key=lambda i: (self.keyword in documents[i]),
            reverse=True,
        )
        if top_n:
            scored = scored[:top_n]
        return [
            {"index": i, "score": 1.0 if self.keyword in documents[i] else 0.1}
            for i in scored
        ]


def make_store(tmp_path) -> JDVectorStore:
    # chromadb 的 EphemeralClient 同进程共享 System，必须用唯一集合名隔离测试
    return JDVectorStore(
        tmp_path / "chroma", collection=_unique_collection(),
        client=chromadb.EphemeralClient(),
    )


MINI_JOBS = [
    {"id": "a1", "company": "甲公司", "job_title": "大模型应用实习生", "city": "深圳",
     "jd_text": "岗位职责：\n负责 RAG 检索增强与向量数据库调优。\n任职要求：\n熟悉 Python 与 LangChain。"},
    {"id": "a2", "company": "乙公司", "job_title": "数据分析实习生", "city": "北京",
     "jd_text": "岗位职责：\nSQL 取数与报表搭建。\n任职要求：\n熟悉 Pandas。"},
    {"id": "a3", "company": "丙公司", "job_title": "后端实习生", "city": "杭州",
     "jd_text": "岗位职责：\nGo 微服务开发。\n任职要求：\n熟悉 MySQL。"},
]


def write_jobs(tmp_path, jobs=MINI_JOBS):
    p = tmp_path / "jobs.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for j in jobs:
            f.write(json.dumps(j, ensure_ascii=False) + "\n")
    return p


# ---------------------------------------------------------------- tokenizer/RRF
def test_tokenize_zh_keeps_english_words():
    tokens = tokenize_zh("熟悉 LangChain 与 RAG")
    assert "langchain" in tokens and "rag" in tokens
    assert "熟悉" in tokens


def test_rrf_combine_prefers_items_in_both_rankings():
    scores = rrf_combine([["a", "b", "c"], ["b", "d"]], k=60)
    assert max(scores, key=scores.get) == "b"
    assert scores["b"] > scores["a"]


# ---------------------------------------------------------------- store/bm25
def test_store_upsert_query_count(tmp_path):
    store = make_store(tmp_path)
    emb = FakeEmbedder()
    chunks = [
        {"chunk_id": "a1::职责::0", "job_id": "a1", "section": "职责", "idx": 0,
         "text": "负责 RAG 检索增强", "company": "甲公司", "job_title": "大模型", "city": "深圳"},
        {"chunk_id": "a2::职责::0", "job_id": "a2", "section": "职责", "idx": 0,
         "text": "SQL 取数与报表", "company": "乙公司", "job_title": "数据分析", "city": "北京"},
    ]
    store.upsert_chunks(chunks, emb.embed([c["text"] for c in chunks]))
    assert store.count() == 2
    hits = store.query(emb.embed_query("RAG 检索"), top_k=2)
    assert hits[0]["chunk_id"] == "a1::职责::0"
    assert hits[0]["company"] == "甲公司"
    assert 0.0 <= hits[0]["vector_score"] <= 1.0 + 1e-6
    # upsert 幂等
    store.upsert_chunks(chunks, emb.embed([c["text"] for c in chunks]))
    assert store.count() == 2


def test_bm25_search_prefers_keyword_match():
    chunks = [
        {"chunk_id": "c1", "text": "负责 RAG 检索增强与向量数据库", "job_id": "a1", "section": "职责"},
        {"chunk_id": "c2", "text": "SQL 取数与报表搭建", "job_id": "a2", "section": "职责"},
        {"chunk_id": "c3", "text": "Go 微服务开发与 MySQL 优化", "job_id": "a3", "section": "职责"},
    ]
    bm25, _ = build_bm25_index(chunks)
    hits = bm25_search(bm25, chunks, "RAG 向量数据库", top_k=3)
    assert hits[0]["chunk_id"] == "c1"
    # 3 条以上语料才能保证非负 IDF（2 条时 log(1.5/1.5)=0）
    assert hits[0]["bm25_score"] > 0


# ---------------------------------------------------------------- retriever
def make_retriever(tmp_path, reranker=None, rerank_enabled=True):
    store = make_store(tmp_path)
    emb = FakeEmbedder()
    ingest_jobs_file(write_jobs(tmp_path), store, emb)
    return HybridRetriever(
        store, emb, reranker,
        cfg={"vector_k": 5, "bm25_k": 5, "rrf_k": 60, "rerank": {"enabled": rerank_enabled}},
    )


def test_hybrid_search_rag_query(tmp_path):
    retriever = make_retriever(tmp_path)
    results = retriever.search("有 RAG 经验的岗位", top_k=3, mode="hybrid", rerank=False)
    assert results
    assert "rrf_score" in results[0]
    top_texts = " ".join(r["text"] for r in results[:2])
    assert "RAG" in top_texts or "检索" in top_texts


def test_vector_and_bm25_modes(tmp_path):
    retriever = make_retriever(tmp_path)
    vec = retriever.search("数据分析", top_k=2, mode="vector", rerank=False)
    assert vec and "vector_score" in vec[0]
    bm = retriever.search("Pandas 报表", top_k=2, mode="bm25", rerank=False)
    assert bm and "bm25_score" in bm[0]


def test_rerank_layer_applied(tmp_path):
    retriever = make_retriever(tmp_path, reranker=FakeReranker("向量数据库"))
    results = retriever.search("RAG 相关岗位", top_k=2, mode="hybrid", rerank=True)
    assert results and "rerank_score" in results[0]


def test_rerank_respects_config_default(tmp_path):
    # 配置关闭重排且未显式指定 → 不走 reranker
    retriever = make_retriever(tmp_path, reranker=FakeReranker("向量数据库"), rerank_enabled=False)
    results = retriever.search("RAG 相关岗位", top_k=2, mode="hybrid")
    assert results and "rerank_score" not in results[0]


def test_empty_store_returns_empty(tmp_path):
    store = make_store(tmp_path)
    retriever = HybridRetriever(store, FakeEmbedder(), None)
    assert retriever.search("任何查询", top_k=3, mode="hybrid", rerank=False) == []


def test_ingest_skips_jobs_without_text(tmp_path):
    store = make_store(tmp_path)
    p = tmp_path / "jobs2.jsonl"
    p.write_text(
        json.dumps({"id": "x1", "jd_text": "  "}, ensure_ascii=False) + "\n"
        + json.dumps(MINI_JOBS[0], ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    stats = ingest_jobs_file(p, store, FakeEmbedder())
    assert stats["jobs"] == 1
    assert stats["failed"] == ["x1"]
