# -*- coding: utf-8 -*-
"""轻量 OpenAI 兼容 LLM 客户端（httpx 直连，不引入 SDK）。

- chat()：非流式对话，支持 JSON 模式（response_format=json_object，
  端点不支持时自动降级为纯提示词约束）
- chat_stream()：SSE 流式对话（供服务层 /generate 使用）
- 重试：429/5xx/超时/连接错误指数退避；4xx 参数错误立即失败
- 记账：每次调用（含最终失败）追加一行 JSONL 到 logs/llm_calls.jsonl，
  记录 model / purpose / usage / latency，评测脚本据此统计 token 与耗时；
  成本 = token × config.llm.price_per_mtok（价格表与日志分离，价格变动不污染历史）

连接参数来自 .env（可被显式入参覆盖）：
  LLM_BASE_URL  默认 https://api.deepseek.com/v1
  LLM_API_KEY   必填
  LLM_MODEL     默认 deepseek-chat
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import httpx

from common import repo_root

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT = 60.0

# 视为瞬时故障、值得重试的状态码
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    """模型调用最终失败（重试耗尽或不可重试的参数错误）。"""


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: Usage
    latency_ms: int
    finish_reason: str = ""


def estimate_cost(usage: Usage, price_per_mtok: dict[str, float] | None) -> float:
    """按价格表（元/百万 token）估算一次调用成本；无价格表返回 0.0。"""
    price = price_per_mtok or {}
    prompt_price = float(price.get("prompt", 0) or 0)
    completion_price = float(price.get("completion", 0) or 0)
    return (
        usage.prompt_tokens * prompt_price + usage.completion_tokens * completion_price
    ) / 1_000_000


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        cfg: dict[str, Any] | None = None,
        log_path: str | Path | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        cfg = cfg or {}
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or os.environ.get("LLM_API_KEY") or ""
        self.model = model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
        if not self.api_key:
            raise LLMError("缺少 LLM_API_KEY（.env），无法调用模型")
        self.temperature = float(cfg.get("temperature", 0.2))
        self.timeout = float(cfg.get("timeout_seconds", DEFAULT_TIMEOUT))
        self.max_retries = int(cfg.get("max_retries", 2))
        self.max_tokens = int(cfg.get("max_tokens", 1024))
        self.price_per_mtok = dict(cfg.get("price_per_mtok") or {})
        self._transport = transport
        self._log_path = Path(log_path) if log_path else repo_root() / "logs" / "llm_calls.jsonl"

    # ------------------------------------------------------------------ core
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        purpose: str = "",
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        t0 = time.monotonic()
        attempts = 0
        last_error = ""
        while attempts <= self.max_retries:
            attempts += 1
            try:
                body = self._request_chat(payload)
            except _TransientHTTPError as e:
                last_error = str(e)
                if attempts > self.max_retries:
                    break
                time.sleep(1.5 ** (attempts - 1))
                continue
            except _PermanentHTTPError as e:
                # json_object 不被端点支持时降级重试一次（不算失败）
                if json_mode and "response_format" in payload and _mentions_response_format(e):
                    payload.pop("response_format")
                    continue
                last_error = str(e)
                break
            usage = _parse_usage(body)
            content = ""
            choices = body.get("choices") or []
            if choices:
                content = (choices[0].get("message") or {}).get("content") or ""
            latency = int((time.monotonic() - t0) * 1000)
            model_used = body.get("model") or self.model
            self._log(
                purpose=purpose,
                model=model_used,
                usage=usage,
                latency_ms=latency,
                ok=True,
                attempts=attempts,
            )
            return LLMResponse(
                content=content,
                model=model_used,
                usage=usage,
                latency_ms=latency,
                finish_reason=(choices[0].get("finish_reason") or "") if choices else "",
            )
        latency = int((time.monotonic() - t0) * 1000)
        self._log(
            purpose=purpose,
            model=self.model,
            usage=Usage(),
            latency_ms=latency,
            ok=False,
            attempts=attempts,
            error=last_error,
        )
        raise LLMError(f"模型调用失败（{attempts} 次尝试）: {last_error}")

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        purpose: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """SSE 流式对话，逐段 yield 增量文本；结束时照常写调用日志。"""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        t0 = time.monotonic()
        emitted: list[str] = []
        usage = Usage()
        model_used = self.model
        try:
            with httpx.Client(
                timeout=self.timeout, transport=self._transport
            ) as client:
                with client.stream(
                    "POST", url, json=payload, headers=headers
                ) as resp:
                    if resp.status_code >= 400:
                        detail = resp.read().decode("utf-8", "replace")[:300]
                        raise LLMError(f"HTTP {resp.status_code}: {detail}")
                    for line in resp.iter_lines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        model_used = chunk.get("model") or model_used
                        if chunk.get("usage"):
                            usage = _parse_usage(chunk)
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = (choices[0].get("delta") or {}).get("content") or ""
                        if delta:
                            emitted.append(delta)
                            yield delta
        except LLMError:
            self._log(
                purpose=purpose,
                model=model_used,
                usage=usage,
                latency_ms=int((time.monotonic() - t0) * 1000),
                ok=False,
                attempts=1,
                error="stream failed",
            )
            raise
        self._log(
            purpose=purpose,
            model=model_used,
            usage=usage,
            latency_ms=int((time.monotonic() - t0) * 1000),
            ok=True,
            attempts=1,
        )

    # -------------------------------------------------------------- internals
    def _request_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            with httpx.Client(
                timeout=self.timeout, transport=self._transport
            ) as client:
                resp = client.post(url, json=payload, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            raise _TransientHTTPError(f"network: {e}") from e
        if resp.status_code in _TRANSIENT_STATUS:
            raise _TransientHTTPError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        if resp.status_code >= 400:
            raise _PermanentHTTPError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            return resp.json()
        except json.JSONDecodeError as e:
            raise _PermanentHTTPError(f"invalid JSON response: {e}") from e

    def _log(
        self,
        *,
        purpose: str,
        model: str,
        usage: Usage,
        latency_ms: int,
        ok: bool,
        attempts: int,
        error: str = "",
    ) -> None:
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "purpose": purpose,
            "model": model,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "latency_ms": latency_ms,
            "ok": ok,
            "attempts": attempts,
            "error": error,
        }
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


class _TransientHTTPError(RuntimeError):
    pass


class _PermanentHTTPError(RuntimeError):
    pass


def _mentions_response_format(err: _PermanentHTTPError) -> bool:
    return "response_format" in str(err)


def _parse_usage(body: dict[str, Any]) -> Usage:
    raw = body.get("usage") or {}
    return Usage(
        prompt_tokens=int(raw.get("prompt_tokens") or 0),
        completion_tokens=int(raw.get("completion_tokens") or 0),
        total_tokens=int(raw.get("total_tokens") or 0),
    )
