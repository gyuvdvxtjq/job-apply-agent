# -*- coding: utf-8 -*-
"""FastAPI 服务测试：注入假检索器/假 LLM，全离线（含 SSE 流解析）。"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from service.app import create_app


class FakeStore:
    def count(self):
        return 7


class FakeRetriever:
    store = FakeStore()

    def search(self, query, top_k=5, mode="hybrid", rerank=None):
        return [
            {
                "chunk_id": "a::职责::0", "job_id": "a", "section": "职责",
                "text": "负责 RAG 检索增强", "company": "甲", "job_title": "大模型",
                "city": "深圳", "rrf_score": 0.05,
            }
        ][:top_k]


MATCH_JSON = json.dumps({
    "score": 0.75, "reasons": ["技能匹配"], "evidence_quotes": ["熟悉 Python"], "hard_gaps": [],
}, ensure_ascii=False)


class FakeLLM:
    def chat(self, messages, **kw):
        from llm import LLMResponse, Usage

        return LLMResponse(content=MATCH_JSON, model="fake", usage=Usage(1, 1, 2), latency_ms=0)

    def chat_stream(self, messages, **kw):
        for chunk in ["你好", "，", "世界"]:
            yield chunk


def make_client() -> TestClient:
    app = create_app(retriever_builder=lambda: FakeRetriever(), llm_builder=lambda: FakeLLM())
    return TestClient(app)


def test_health():
    c = make_client()
    r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["chunks_indexed"] == 7


def test_search():
    c = make_client()
    r = c.post("/search", json={"query": "RAG 岗位", "top_k": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "RAG 岗位"
    assert len(body["results"]) == 1
    assert body["results"][0]["job_id"] == "a"


def test_search_rejects_bad_mode():
    c = make_client()
    r = c.post("/search", json={"query": "x", "mode": "nope"})
    assert r.status_code == 422


def test_match_returns_verdict():
    c = make_client()
    r = c.post("/match", json={"job_text": "招聘 Python 实习生"})
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"]["score"] == 0.75
    assert body["lexical_score"] >= 0


def test_match_empty_job_text_400():
    c = make_client()
    r = c.post("/match", json={"job_text": "  "})
    assert r.status_code == 400


def test_match_missing_profile_404():
    c = make_client()
    r = c.post("/match", json={"job_text": "x", "profile_path": "no/such.yaml"})
    assert r.status_code == 404


def test_generate_sse_stream():
    c = make_client()
    with c.stream("POST", "/generate", json={
        "company": "甲", "job_title": "大模型实习", "jd_text": "负责 RAG",
    }) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        deltas, done = [], False
        for line in resp.iter_lines():
            if not line.startswith("data:"):
                continue
            payload = json.loads(line[len("data:"):].strip())
            if "delta" in payload:
                deltas.append(payload["delta"])
            if payload.get("done"):
                done = True
    assert "".join(deltas) == "你好，世界"
    assert done is True


def test_generate_empty_jd_400():
    c = make_client()
    r = c.post("/generate", json={"jd_text": " "})
    assert r.status_code == 400
