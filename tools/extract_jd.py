# -*- coding: utf-8 -*-
"""JD 结构化抽取：公司/岗位/城市/学历要求/技术栈/截止日期/投递方式。

- Pydantic 严格校验；校验失败把错误信息回喂模型自动重试（ask_validated_json）
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
from json_task import ask_validated_json, parse_model_json  # noqa: F401 (re-export)

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


def extract_jd_info(
    jd_text: str,
    client: ChatClient,
    max_retries: int = 2,
    log_path: str | Path | None = None,
) -> tuple[JDInfo | None, dict[str, Any]]:
    """抽取 JD 结构化字段。

    返回 (JDInfo | None, stats)。stats: {"ok": bool, "attempts": int, "errors": [...]}
    """
    messages: list[dict[str, str]] = [
        {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": f"岗位描述文本：\n{jd_text}"},
    ]
    result, stats = ask_validated_json(
        client,
        messages,
        JDInfo.model_validate,
        purpose="jd_extract",
        max_retries=max_retries,
    )
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
