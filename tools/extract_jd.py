# -*- coding: utf-8 -*-
"""JD 结构化抽取：公司/岗位/城市/学历要求/技术栈/截止日期/投递方式。

- Pydantic 严格校验；校验失败把错误信息回喂模型自动重试（最多 N 次）
- 每次抽取结果（成败/尝试次数）追加到 logs/jd_extract_log.jsonl，
  评测脚本据此统计失败率
- 只依据原文抽取，缺失字段留空——禁止编造由提示词 + 上层审查共同保证
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from common import repo_root
from llm import LLMError

DEFAULT_LOG = repo_root() / "logs" / "jd_extract_log.jsonl"

EXTRACT_SYSTEM_PROMPT = """你是招聘信息结构化抽取助手。从给定的岗位描述(JD)文本中抽取字段，只输出一个 JSON 对象，不要输出任何其他文字。

字段定义：
- company: 公司名（字符串，无法判断填 ""）
- job_title: 岗位名称
- cities: 工作城市列表（如 ["深圳"]，多城市 ["北京","上海"]，未提及 []）
- education_requirement: 学历要求（"本科"/"硕士"/"不限" 等，未提及 ""）
- tech_stack: 技术栈关键词列表（如 ["Python","RAG"]，未提及 []）
- deadline: 投递截止日期（尽量 YYYY-MM-DD 格式，未提及 ""）
- apply_method: 投递方式（邮箱 / 链接 / 平台名，未提及 ""）

规则：只依据原文抽取，缺失就留空或空数组，禁止编造；输出必须是合法 JSON。"""

REPAIR_PROMPT = "上一次输出不合法：{err}\n请重新输出完整且合法的 JSON，不要解释，不要加 markdown 围栏。"


class JDInfo(BaseModel):
    company: str = ""
    job_title: str = ""
    cities: list[str] = Field(default_factory=list)
    education_requirement: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    deadline: str = ""
    apply_method: str = ""


class ChatClient(Protocol):
    """LLMClient 的最小协议，便于测试注入假实现。"""

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any: ...


def parse_model_json(text: str) -> dict[str, Any]:
    """容忍 markdown 围栏与前后缀文本，解析出第一个 JSON 对象。"""
    if not text:
        raise ValueError("empty response")
    cleaned = text.strip()
    if "```" in cleaned:
        # 优先取围栏内的内容
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


def extract_jd_info(
    jd_text: str,
    client: ChatClient,
    max_retries: int = 2,
    log_path: str | Path | None = None,
) -> tuple[JDInfo | None, dict[str, Any]]:
    """抽取 JD 结构化字段。

    返回 (JDInfo | None, stats)。stats: {"ok": bool, "attempts": int, "errors": [...]}
    网络层错误不循环重试（客户端已做指数退避），直接判失败。
    """
    stats: dict[str, Any] = {"ok": False, "attempts": 0, "errors": []}
    messages: list[dict[str, str]] = [
        {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": f"岗位描述文本：\n{jd_text}"},
    ]
    result: JDInfo | None = None
    for _ in range(max_retries + 1):
        stats["attempts"] += 1
        try:
            resp = client.chat(messages, purpose="jd_extract", json_mode=True)
        except LLMError as e:
            stats["errors"].append(f"api: {e}")
            break
        messages.append({"role": "assistant", "content": resp.content})
        try:
            data = parse_model_json(resp.content)
            result = JDInfo.model_validate(data)
        except (ValueError, ValidationError) as e:
            err = str(e).splitlines()[0][:300]
            stats["errors"].append(err)
            messages.append({"role": "user", "content": REPAIR_PROMPT.format(err=err)})
            continue
        stats["ok"] = True
        break
    _append_log(log_path, jd_text, result, stats)
    return result, stats


def _append_log(
    log_path: str | Path | None,
    jd_text: str,
    result: JDInfo | None,
    stats: dict[str, Any],
) -> None:
    path = Path(log_path) if log_path else DEFAULT_LOG
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "ok": stats["ok"],
        "attempts": stats["attempts"],
        "errors": stats["errors"][-1:] if stats["errors"] else [],
        "jd_preview": (jd_text or "")[:80],
        "company": result.company if result else "",
        "job_title": result.job_title if result else "",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
