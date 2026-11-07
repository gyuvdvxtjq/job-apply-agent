# -*- coding: utf-8 -*-
"""JD 结构化抽取测试：假 LLM 客户端 + 真实 Pydantic 校验，全离线。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from extract_jd import JDInfo, extract_jd_info, parse_model_json
from llm import LLMResponse, Usage

GOOD = (
    '{"company":"示例科技","job_title":"数据分析实习生","cities":["深圳"],'
    '"education_requirement":"本科","tech_stack":["Python","SQL"],'
    '"deadline":"2026-12-01","apply_method":"hr@example-tech.com"}'
)


class FakeLLM:
    """按序返回预置回复；记录每次收到的 messages。"""

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    def chat(self, messages, **kwargs):
        self.calls.append([dict(m) for m in messages])  # 快照，避免共享引用被后续 append 污染
        return LLMResponse(
            content=self.replies.pop(0), model="fake",
            usage=Usage(1, 1, 2), latency_ms=0,
        )


def test_extract_ok():
    info, stats = extract_jd_info(
        "深圳 示例科技 数据分析实习生 本科 Python SQL", FakeLLM([GOOD]), log_path=None
    )
    assert stats["ok"] is True
    assert stats["attempts"] == 1
    assert info.company == "示例科技"
    assert info.cities == ["深圳"]
    assert info.tech_stack == ["Python", "SQL"]
    assert info.deadline == "2026-12-01"


def test_extract_retries_on_invalid_json():
    fake = FakeLLM(["这不是 JSON", GOOD])
    info, stats = extract_jd_info("JD文本", fake)
    assert stats["ok"] is True
    assert stats["attempts"] == 2
    # 第二轮的 messages 应包含修复提示
    assert "不合法" in fake.calls[1][-1]["content"]


def test_extract_fails_after_max_retries():
    info, stats = extract_jd_info("JD文本", FakeLLM(["bad"] * 3), max_retries=2)
    assert info is None
    assert stats["ok"] is False
    assert stats["attempts"] == 3


def test_extract_api_error_no_loop():
    class BoomLLM:
        def chat(self, messages, **kwargs):
            from llm import LLMError

            raise LLMError("网络错误")

    info, stats = extract_jd_info("JD文本", BoomLLM(), max_retries=3)
    assert info is None
    assert stats["attempts"] == 1
    assert stats["errors"][0].startswith("api:")


def test_extract_fenced_json_accepted():
    fenced = f"```json\n{GOOD}\n```"
    info, stats = extract_jd_info("JD", FakeLLM([fenced]))
    assert stats["ok"] is True
    assert info.job_title == "数据分析实习生"


def test_parse_model_json_variants():
    assert parse_model_json('{"a": 1}') == {"a": 1}
    assert parse_model_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_model_json('说明文字 {"a": 1} 结尾') == {"a": 1}
    with pytest.raises(ValueError):
        parse_model_json("完全没有对象")
    with pytest.raises(ValueError):
        parse_model_json("")


def test_jdinfo_rejects_wrong_types():
    with pytest.raises(ValidationError):
        JDInfo.model_validate({"cities": "深圳"})  # 应为列表
    with pytest.raises(ValidationError):
        JDInfo.model_validate({"tech_stack": [1, 2]})
