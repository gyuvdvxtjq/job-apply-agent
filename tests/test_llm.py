# -*- coding: utf-8 -*-
"""LLMClient 单元测试：httpx.MockTransport 模拟端点，全离线。"""
from __future__ import annotations

import json as jsonlib

import httpx
import pytest

import llm
from llm import LLMClient, LLMError, Usage, estimate_cost

BASE_CFG = {"price_per_mtok": {"prompt": 1.0, "completion": 2.0}}


def make_client(handler, tmp_path, **overrides) -> LLMClient:
    return LLMClient(
        base_url="https://mock/v1",
        api_key="test-key",
        model="mock-model",
        cfg={**BASE_CFG, **overrides},
        log_path=tmp_path / "log.jsonl",
        transport=httpx.MockTransport(handler),
    )


def ok_body(model="mock-model"):
    return {
        "choices": [
            {"message": {"content": "hi"}, "finish_reason": "stop"}
        ],
        "model": model,
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def read_log(tmp_path) -> list[dict]:
    lines = (tmp_path / "log.jsonl").read_text(encoding="utf-8").strip().splitlines()
    return [jsonlib.loads(x) for x in lines]


def test_chat_success_and_log(tmp_path):
    c = make_client(lambda req: httpx.Response(200, json=ok_body()), tmp_path)
    r = c.chat([{"role": "user", "content": "x"}], purpose="unit-test")
    assert r.content == "hi"
    assert r.usage.total_tokens == 15
    rec = read_log(tmp_path)[-1]
    assert rec["ok"] is True
    assert rec["purpose"] == "unit-test"
    assert rec["prompt_tokens"] == 10
    assert rec["model"] == "mock-model"


def test_retry_on_500_then_success(tmp_path, monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json=ok_body())

    c = make_client(handler, tmp_path)
    r = c.chat([{"role": "user", "content": "x"}])
    assert calls["n"] == 2
    assert r.content == "hi"


def test_retry_exhausted_raises_and_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    def handler(req):
        return httpx.Response(503, text="unavailable")

    c = make_client(handler, tmp_path, max_retries=1)
    with pytest.raises(LLMError):
        c.chat([{"role": "user", "content": "x"}])
    rec = read_log(tmp_path)[-1]
    assert rec["ok"] is False
    assert "503" in rec["error"]


def test_no_retry_on_400(tmp_path):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(400, text="bad request")

    c = make_client(handler, tmp_path)
    with pytest.raises(LLMError):
        c.chat([{"role": "user", "content": "x"}])
    assert calls["n"] == 1


def test_json_mode_sends_response_format_and_falls_back(tmp_path):
    seen: list[dict] = []

    def handler(req):
        body = jsonlib.loads(req.content)
        seen.append(body)
        if "response_format" in body:
            return httpx.Response(400, text="response_format unsupported")
        return httpx.Response(200, json=ok_body())

    c = make_client(handler, tmp_path)
    r = c.chat([{"role": "user", "content": "x"}], json_mode=True)
    assert r.content == "hi"
    assert seen[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in seen[1]


def test_chat_stream_parses_sse(tmp_path):
    sse = (
        'data: {"model":"mock-model","choices":[{"delta":{"content":"你"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"好"}}]}\n\n'
        'data: {"model":"mock-model","choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(req):
        return httpx.Response(
            200, text=sse, headers={"content-type": "text/event-stream"}
        )

    c = make_client(handler, tmp_path)
    chunks = list(c.chat_stream([{"role": "user", "content": "x"}], purpose="stream"))
    assert "".join(chunks) == "你好"
    rec = read_log(tmp_path)[-1]
    assert rec["ok"] is True
    assert rec["completion_tokens"] == 2


def test_missing_api_key_raises():
    import os

    env_backup = os.environ.pop("LLM_API_KEY", None)
    try:
        with pytest.raises(LLMError):
            LLMClient(base_url="https://mock/v1")
    finally:
        if env_backup is not None:
            os.environ["LLM_API_KEY"] = env_backup


def test_estimate_cost():
    assert estimate_cost(Usage(1_000_000, 500_000), {"prompt": 1.0, "completion": 2.0}) == 2.0
    assert estimate_cost(Usage(1000, 1000), None) == 0.0
