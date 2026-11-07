# -*- coding: utf-8 -*-
"""Rerank 客户端（默认硅基流动 BAAI/bge-reranker-v2-m3，Jina 风格 /rerank 接口）。

- 429/5xx/超时指数退避重试；调用记账 purpose=rerank
- 可通过 config.rag.rerank.enabled=false 关闭（评测对照组之一）
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import httpx

from common import repo_root

DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"
_TRANSIENT = {429, 500, 502, 503, 504}


class RerankError(RuntimeError):
    pass


class RerankClient:
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
            or os.environ.get("RERANK_BASE_URL")
            or os.environ.get("EMBEDDING_BASE_URL")
            or os.environ.get("LLM_BASE_URL")
            or DEFAULT_BASE_URL
        ).rstrip("/")
        self.api_key = (
            api_key
            or os.environ.get("RERANK_API_KEY")
            or os.environ.get("SILICONFLOW_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or ""
        )
        self.model = model or os.environ.get("RERANK_MODEL") or DEFAULT_MODEL
        self.max_retries = max_retries
        self.timeout = timeout
        self._transport = transport
        self._log_path = Path(log_path) if log_path else repo_root() / "logs" / "llm_calls.jsonl"

    def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> list[dict]:
        """返回 [{"index": int, "score": float}, ...]，按相关度降序。"""
        if not documents:
            return []
        url = f"{self.base_url}/rerank"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload: dict = {
            "model": self.model,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n
        t0 = time.monotonic()
        last_err = ""
        for attempt in range(1, self.max_retries + 2):
            try:
                with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                    resp = client.post(url, json=payload, headers=headers)
                if resp.status_code in _TRANSIENT:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                elif resp.status_code >= 400:
                    self._log(len(documents), int((time.monotonic() - t0) * 1000), False, f"HTTP {resp.status_code}")
                    raise RerankError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                else:
                    body = resp.json()
                    self._log(len(documents), int((time.monotonic() - t0) * 1000), True)
                    return [
                        {"index": int(r["index"]), "score": float(r.get("relevance_score") or 0.0)}
                        for r in body.get("results", [])
                    ]
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_err = f"network: {e}"
            if attempt <= self.max_retries:
                time.sleep(1.5 ** (attempt - 1))
        self._log(len(documents), int((time.monotonic() - t0) * 1000), False, last_err)
        raise RerankError(f"rerank 失败（{self.max_retries + 1} 次尝试）: {last_err}")

    def _log(self, inputs: int, latency_ms: int, ok: bool, error: str = "") -> None:
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "purpose": "rerank",
            "model": self.model,
            "inputs": inputs,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_ms": latency_ms,
            "ok": ok,
            "error": error,
        }
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
