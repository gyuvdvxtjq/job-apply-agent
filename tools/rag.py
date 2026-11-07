# -*- coding: utf-8 -*-
"""混合检索：Chroma 向量召回 + BM25 关键词召回 → RRF 融合 → 可选重排。

- 向量通道捕获语义（"有检索经验的岗" ↔ "RAG/向量数据库"），BM25 通道
  捕获精确关键词（模型名、框架名如 "LangGraph" 这类低频词是向量模型的弱项）
- RRF（Reciprocal Rank Fusion）只用排名不用分数，避免两路分数量纲不可比
- 重排为可选层（cross-encoder 精但慢且费钱），config.rag.rerank.enabled 控制，
  评测据此做「纯向量 / 混合 / 混合+重排」三组对比
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import jieba
from rank_bm25 import BM25Okapi

from chunker import chunk_jd

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")

for _w in ("大模型", "大语言模型", "检索增强", "向量数据库", "智能体", "校招", "应届生", "实习生"):
    jieba.add_word(_w)


def tokenize_zh(text: str) -> list[str]:
    """中文 jieba 分词 + 英文按词保留（模型名/框架名不被切碎）。"""
    tokens: list[str] = []
    for seg in re.split(r"([a-zA-Z0-9]+)", text or ""):
        if re.fullmatch(r"[a-zA-Z0-9]+", seg):
            tokens.append(seg.lower())
        else:
            tokens.extend(t for t in jieba.cut_for_search(seg) if t.strip())
    return tokens


class JDVectorStore:
    """Chroma 持久化向量库，一个 chunk 一条记录。"""

    def __init__(self, persist_dir: str | Path, collection: str = "jd_chunks", client: Any | None = None):
        import chromadb
        from chromadb.config import Settings

        self._client = client or chromadb.PersistentClient(
            path=str(persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},
        )

    def reset(self) -> None:
        cid = self._collection.name
        self._client.delete_collection(cid)
        self._collection = self._client.get_or_create_collection(
            name=cid, metadata={"hnsw:space": "cosine"}
        )

    def upsert_chunks(self, chunks: list[dict[str, Any]], embeddings: list[list[float]]) -> int:
        if not chunks:
            return 0
        self._collection.upsert(
            ids=[c["chunk_id"] for c in chunks],
            embeddings=embeddings,
            documents=[c["text"] for c in chunks],
            metadatas=[
                {
                    "job_id": c["job_id"],
                    "section": c["section"],
                    "company": c.get("company") or "",
                    "job_title": c.get("job_title") or "",
                    "city": c.get("city") or "",
                }
                for c in chunks
            ],
        )
        return len(chunks)

    def count(self) -> int:
        return self._collection.count()

    def query(self, vector: list[float], top_k: int = 20) -> list[dict[str, Any]]:
        if self.count() == 0:
            return []
        res = self._collection.query(query_embeddings=[vector], n_results=min(top_k, self.count()))
        out: list[dict[str, Any]] = []
        for i, cid in enumerate(res["ids"][0]):
            meta = res["metadatas"][0][i]
            distance = res["distances"][0][i]
            out.append(
                {
                    "chunk_id": cid,
                    "text": res["documents"][0][i],
                    **meta,
                    "vector_score": round(1.0 - float(distance), 4),  # cosine distance → 相似度
                }
            )
        return out

    def all_chunks(self) -> list[dict[str, Any]]:
        """全量拉取（供 BM25 索引重建；数据量为百级，毫秒级完成）。"""
        if self.count() == 0:
            return []
        got = self._collection.get()
        out: list[dict[str, Any]] = []
        for i, cid in enumerate(got["ids"]):
            meta = got["metadatas"][i]
            out.append({"chunk_id": cid, "text": got["documents"][i], **meta})
        return out


def build_bm25_index(chunks: list[dict[str, Any]]) -> tuple[BM25Okapi, list[dict[str, Any]]]:
    corpus_tokens = [tokenize_zh(c["text"]) for c in chunks]
    bm25 = BM25Okapi(corpus_tokens)
    return bm25, chunks


def bm25_search(
    bm25: BM25Okapi, chunks: list[dict[str, Any]], query: str, top_k: int = 20
) -> list[dict[str, Any]]:
    scores = bm25.get_scores(tokenize_zh(query))
    ranked = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [{**chunks[i], "bm25_score": round(float(scores[i]), 4)} for i in ranked]


def rrf_combine(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion：score = Σ 1/(k + rank)。只用排名，不涉量纲。"""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return scores


class HybridRetriever:
    def __init__(self, store: JDVectorStore, embedder: Any, reranker: Any | None = None, cfg: dict | None = None):
        cfg = cfg or {}
        self.store = store
        self.embedder = embedder
        self.reranker = reranker
        self.vector_k = int(cfg.get("vector_k", 20))
        self.bm25_k = int(cfg.get("bm25_k", 20))
        self.rrf_k = int(cfg.get("rrf_k", 60))
        self.rerank_enabled = bool((cfg.get("rerank") or {}).get("enabled", True))
        self.rerank_top_n = int((cfg.get("rerank") or {}).get("top_n", 5))

    def search(
        self,
        query: str,
        top_k: int = 5,
        mode: str = "hybrid",
        rerank: bool | None = None,
    ) -> list[dict[str, Any]]:
        """mode: hybrid | vector | bm25。rerank=None 时取配置默认。"""
        use_rerank = self.rerank_enabled if rerank is None else rerank
        all_chunks = self.store.all_chunks()
        if not all_chunks:
            return []

        candidates: list[dict[str, Any]]
        rankings: list[list[str]] = []

        if mode in ("hybrid", "vector"):
            qvec = self.embedder.embed_query(query)
            vec_hits = self.store.query(qvec, top_k=self.vector_k)
            rankings.append([h["chunk_id"] for h in vec_hits])
            candidates = vec_hits
        else:
            candidates = []

        if mode in ("hybrid", "bm25"):
            bm25, _ = build_bm25_index(all_chunks)
            bm_hits = bm25_search(bm25, all_chunks, query, top_k=self.bm25_k)
            rankings.append([h["chunk_id"] for h in bm_hits])
            by_id = {h["chunk_id"]: h for h in candidates}
            for h in bm_hits:
                by_id.setdefault(h["chunk_id"], h)
            candidates = list(by_id.values())

        if not candidates:
            return []

        if mode == "hybrid" and len(rankings) > 1:
            fused = rrf_combine(rankings, k=self.rrf_k)
            candidates.sort(key=lambda h: fused.get(h["chunk_id"], 0.0), reverse=True)
            for h in candidates:
                h["rrf_score"] = round(fused.get(h["chunk_id"], 0.0), 6)
        elif mode == "vector":
            pass  # 已按向量相似度排序
        else:  # bm25 单路
            candidates.sort(key=lambda h: h.get("bm25_score", 0.0), reverse=True)

        if use_rerank and self.reranker is not None:
            pool = candidates[: self.rerank_top_n * 3]
            results = self.reranker.rerank(
                query, [c["text"] for c in pool], top_n=min(top_k, len(pool))
            )
            reranked = []
            for r in results:
                item = dict(pool[r["index"]])
                item["rerank_score"] = round(r["score"], 4)
                reranked.append(item)
            return reranked

        return candidates[:top_k]


def ingest_jobs_file(
    jobs_path: str | Path,
    store: JDVectorStore,
    embedder: Any,
    max_chars: int = 500,
    reset: bool = False,
) -> dict[str, Any]:
    """读取 jobs.jsonl（每行一个 {id/company/job_title/city/jd_text/source_url}），
    分块、向量化、写入向量库。"""
    import json

    if reset:
        store.reset()
    total_chunks = 0
    total_jobs = 0
    failed: list[str] = []
    with open(jobs_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            job = json.loads(line)
            jid = str(job.get("id") or f"job-{total_jobs + 1}")
            jd_text = job.get("jd_text") or ""
            if not jd_text.strip():
                failed.append(jid)
                continue
            chunks = chunk_jd(jd_text, job_id=jid, max_chars=max_chars)
            for c in chunks:
                c["company"] = job.get("company") or ""
                c["job_title"] = job.get("job_title") or ""
                c["city"] = job.get("city") or ""
            if not chunks:
                failed.append(jid)
                continue
            embeddings = embedder.embed([c["text"] for c in chunks])
            store.upsert_chunks(chunks, embeddings)
            total_chunks += len(chunks)
            total_jobs += 1
    return {"jobs": total_jobs, "chunks": total_chunks, "failed": failed}
