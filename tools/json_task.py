# -*- coding: utf-8 -*-
"""LLM JSON 任务通用循环：请求 → 解析 → 校验 → 失败回喂重试。

供 JD 抽取 / 匹配评分 / 质检等所有结构化输出任务复用，保证「校验错误回喂」
策略全项目一致（见 DESIGN.md §2.3/§2.4）。
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from pydantic import ValidationError

from llm import LLMError

REPAIR_PROMPT = "上一次输出不合法：{err}\n请重新输出完整且合法的 JSON，不要解释，不要加 markdown 围栏。"


def parse_model_json(text: str) -> dict[str, Any]:
    """容忍 markdown 围栏与前后缀文本，解析出第一个 JSON 对象。"""
    if not text:
        raise ValueError("empty response")
    cleaned = text.strip()
    if "```" in cleaned:
        for part in cleaned.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[len("json"):].strip()
            if part.startswith("{"):
                cleaned = part
                break
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in response")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("JSON root is not an object")
    return data


def ask_validated_json(
    client: Any,
    messages: list[dict[str, str]],
    validate: Callable[[dict[str, Any]], Any],
    *,
    purpose: str = "",
    max_retries: int = 2,
) -> tuple[Any, dict[str, Any]]:
    """执行一个结构化 JSON 任务。

    validate: 对解析出的 dict 做校验/转换（如 Model.model_validate），
    校验失败抛 ValueError/ValidationError 即触发回喂重试。
    返回 (结果 | None, stats)；网络层错误不循环（客户端已重试），直接判负。
    """
    stats: dict[str, Any] = {"ok": False, "attempts": 0, "errors": []}
    for _ in range(max_retries + 1):
        stats["attempts"] += 1
        try:
            resp = client.chat(messages, purpose=purpose, json_mode=True)
        except LLMError as e:
            stats["errors"].append(f"api: {e}")
            return None, stats
        messages.append({"role": "assistant", "content": resp.content})
        try:
            result = validate(parse_model_json(resp.content))
        except (ValueError, ValidationError) as e:
            err = str(e).splitlines()[0][:300]
            stats["errors"].append(err)
            messages.append({"role": "user", "content": REPAIR_PROMPT.format(err=err)})
            continue
        stats["ok"] = True
        return result, stats
    return None, stats
