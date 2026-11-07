# -*- coding: utf-8 -*-
"""Embedding / Rerank 客户端测试：MockTransport 全离线。"""
from __future__ import annotations

import json

import httpx
import pytest

from embeddings import EmbeddingClient, EmbeddingError
from rerank import RerankClient, RerankError


def emb_response(texts):
    return {
        "data": [{"index": i, "embedding": [float(i)] * 4} for i in range(len(texts))],
        "usage": {"prompt_tokens": len(texts) * 7, "total_tokens": len(texts) * 7},
    }


def make_embedder(handler, tmp_path, **kw) -> EmbeddingClient:
    return EmbeddingClient(
        base_url="https://mock/v1", api_key="k", model="emb-m",
        log_path=tmp_path / "log.jsonl", transport=httpx.MockTransport(handler), **kw,
    )


def test_embed_preserves_order_and_batches(tmp_path):
    calls = []

    def handler(req):
        texts = json.loads(req.read())["input"]
        calls.append(len(texts))
        return httpx.Response(200, json=emb_response(texts))

    c = make_embedder(handler, tmp_path)
    texts = [f"doc{i}" for i in range(33)]  # 33 条 → 32+1 两批
    vecs = c.embed(texts)
    assert len(vecs) == 33
    # 响应里的 embedding 值 = 批内局部 index；分批不影响全局顺序
    assert vecs[0] == [0.0] * 4
    assert vecs[31] == [31.0] * 4
    assert vecs[32] == [0.0] * 4
    assert calls == [32, 1]


def test_embed_retry_on_500(tmp_path, monkeypatch):
    import embeddings

    monkeypatch.setattr(embeddings.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json=emb_response(["x"]))

    c = make_embedder(handler, tmp_path)
    assert len(c.embed(["x"])) == 1
    assert calls["n"] == 2


def test_embed_no_retry_on_400(tmp_path):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(400, text="bad")

    c = make_embedder(handler, tmp_path)
    with pytest.raises(EmbeddingError):
        c.embed(["x"])
    assert calls["n"] == 1


def test_embed_empty_input(tmp_path):
    c = make_embedder(lambda req: httpx.Response(200, json=emb_response([])), tmp_path)
    assert c.embed([]) == []


def make_reranker(handler, tmp_path, **kw) -> RerankClient:
    return RerankClient(
        base_url="https://mock/v1", api_key="k", model="rr-m",
        log_path=tmp_path / "log.jsonl", transport=httpx.MockTransport(handler), **kw,
    )


def test_rerank_parses_results(tmp_path):
    def handler(req):
        return httpx.Response(200, json={"results": [
            {"index": 2, "relevance_score": 0.9},
            {"index": 0, "relevance_score": 0.4},
        ]})

    c = make_reranker(handler, tmp_path)
    out = c.rerank("q", ["a", "b", "c"], top_n=2)
    assert out == [{"index": 2, "score": 0.9}, {"index": 0, "score": 0.4}]


def test_rerank_empty_documents(tmp_path):
    c = make_reranker(lambda req: httpx.Response(200, json={"results": []}), tmp_path)
    assert c.rerank("q", []) == []


def test_rerank_error_after_retries(tmp_path, monkeypatch):
    import rerank

    monkeypatch.setattr(rerank.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503, text="down")

    c = make_reranker(handler, tmp_path, max_retries=1)
    with pytest.raises(RerankError):
        c.rerank("q", ["a"])
    assert calls["n"] == 2
