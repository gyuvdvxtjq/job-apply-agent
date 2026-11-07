# -*- coding: utf-8 -*-
"""Embedding 客户端（OpenAI 兼容 /embeddings，默认硅基流动 BAAI/bge-m3）。

- 输入自动分批（每批 ≤32 条），429/5xx/超时指数退避重试
- 每次调用追加 logs/llm_calls.jsonl（purpose=embedding），与 LLM 共用记账格式
- 连接参数：EMBEDDING_BASE_URL → LLM_BASE_URL；EMBEDDING_API_KEY → SILICONFLOW_API_KEY
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from common import repo_root

DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_MODEL = "BAAI/bge-m3"
BATCH_SIZE = 32
_TRANSIENT = {429, 500, 502, 503, 504}


class EmbeddingError(RuntimeError):
    pass


class EmbeddingClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        max_retries: int = 2,
        timeout: float = 30.0,
        log_path: str | Path | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("EMBEDDING_BASE_URL")
            or os.environ.get("LLM_BASE_URL")
            or DEFAULT_BASE_URL
        ).rstrip("/")
        self.api_key = (
            api_key
            or os.environ.get("EMBEDDING_API_KEY")
            or os.environ.get("SILICONFLOW_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or ""
        )
        self.model = model or os.environ.get("EMBEDDING_MODEL") or DEFAULT_MODEL
        self.max_retries = max_retries
        self.timeout = timeout
        self._transport = transport
        self._log_path = Path(log_path) if log_path else repo_root() / "logs" / "llm_calls.jsonl"

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化，返回与输入等长的向量列表。"""
        if not texts:
            return []
        out: dict[int, list[float]] = {}
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start : start + BATCH_SIZE]
            for idx, vec in zip(range(start, start + len(batch)), self._embed_batch(batch)):
                out[idx] = vec
        return [out[i] for i in range(len(texts))]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        url = f"{self.base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"model": self.model, "input": batch}
        t0 = time.monotonic()
        last_err = ""
        for attempt in range(1, self.max_retries + 2):
            try:
                with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                    resp = client.post(url, json=payload, headers=headers)
                if resp.status_code in _TRANSIENT:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                elif resp.status_code >= 400:
                    self._log(len(batch), 0, int((time.monotonic() - t0) * 1000), False, f"HTTP {resp.status_code}")
                    raise EmbeddingError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                else:
                    body = resp.json()
                    data = sorted(body.get("data", []), key=lambda x: x.get("index", 0))
                    usage = body.get("usage") or {}
                    self._log(
                        len(batch),
                        int(usage.get("prompt_tokens") or 0),
                        int((time.monotonic() - t0) * 1000),
                        True,
                    )
                    return [item["embedding"] for item in data]
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_err = f"network: {e}"
            if attempt <= self.max_retries:
                time.sleep(1.5 ** (attempt - 1))
        self._log(len(batch), 0, int((time.monotonic() - t0) * 1000), False, last_err)
        raise EmbeddingError(f"embedding 失败（{self.max_retries + 1} 次尝试）: {last_err}")

    def _log(self, inputs: int, prompt_tokens: int, latency_ms: int, ok: bool, error: str = "") -> None:
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "purpose": "embedding",
            "model": self.model,
            "inputs": inputs,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": 0,
            "latency_ms": latency_ms,
            "ok": ok,
            "error": error,
        }
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
