# -*- coding: utf-8 -*-
"""LLM 匹配评分：简历画像 vs 岗位 JD 的语义匹配裁决。

替代原 match.py 的词法打分作为主判（词法分作为对照信号输入提示词）。
输出结构化 MatchVerdict：分数、理由、JD 原文证据引用、硬性缺口。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from json_task import ask_validated_json

MATCH_SYSTEM_PROMPT = """你是校招岗位匹配评估官。给定「简历画像」和「岗位JD」，评估该候选人投递此岗位的匹配程度，只输出一个 JSON 对象。

输出字段：
- score: 0~1 的匹配分（0.9+ 高度匹配，0.5~0.7 可投，<0.4 不建议）
- reasons: 评分理由（字符串列表，2~4 条，引用具体匹配点或不匹配点）
- evidence_quotes: 直接从 JD 原文摘录的证据句（字符串列表，0~3 条，禁止改写）
- hard_gaps: 硬性缺口（字符串列表，如学历/专业/城市不符；无则空列表）

规则：只依据输入材料判断，禁止想象简历里没有的经历；score 必须是数字；输出必须是合法 JSON。"""


class MatchVerdict(BaseModel):
    score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    evidence_quotes: list[str] = Field(default_factory=list)
    hard_gaps: list[str] = Field(default_factory=list)

    @field_validator("score")
    @classmethod
    def _clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


def _build_user_prompt(
    profile: dict[str, Any],
    jd_text: str,
    lexical_score: float | None,
    jd_info: dict[str, Any] | None,
) -> str:
    highlights = profile.get("highlights") or []
    hl_lines = "\n".join(
        f"- {h.get('title', '')}（技能: {'、'.join(h.get('skills') or []) or '无'}；"
        f"指标: {'、'.join(h.get('metrics') or []) or '无'}）"
        for h in highlights[:6]
    ) or "（无项目经历记录）"
    edu = "；".join(
        f"{e.get('school', '')} {e.get('major', '')} {e.get('degree', '')}".strip()
        for e in (profile.get("education") or [])
    ) or "未填"
    parts = [
        "【简历画像】",
        f"技能: {'、'.join(profile.get('skills') or []) or '未填'}",
        f"方向: {'、'.join(profile.get('directions') or []) or '未填'}",
        f"教育: {edu}",
        "项目经历（写信证据只能来自这里）:",
        hl_lines,
        "",
        "【岗位JD】",
        jd_text or "（无 JD 文本）",
    ]
    if jd_info:
        parts.append(
            f"【结构化抽取】公司={jd_info.get('company') or '?'} 岗位={jd_info.get('job_title') or '?'} "
            f"城市={'/'.join(jd_info.get('cities') or []) or '?'} "
            f"学历={jd_info.get('education_requirement') or '?'}"
        )
    if lexical_score is not None:
        parts.append(f"（词法匹配参考分: {lexical_score}，仅供对照，不要求一致）")
    return "\n".join(parts)


def match_lead_with_llm(
    profile: dict[str, Any],
    jd_text: str,
    client: Any,
    lexical_score: float | None = None,
    jd_info: dict[str, Any] | None = None,
    max_retries: int = 2,
) -> tuple[MatchVerdict | None, dict[str, Any]]:
    """返回 (MatchVerdict | None, stats)。"""
    messages = [
        {"role": "system", "content": MATCH_SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(profile, jd_text, lexical_score, jd_info)},
    ]
    return ask_validated_json(
        client, messages, MatchVerdict.model_validate,
        purpose="match_score", max_retries=max_retries,
    )
