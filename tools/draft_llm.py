# -*- coding: utf-8 -*-
"""LLM 求职信生成 + LLM 质检。

- 生成：证据只允许来自 profile.highlights 与 JD 原文（禁编造），
  支持携带上一轮质检 issues 作为修改指令（回退重写）
- 质检：LLM 审稿人（编造证据/空话套话/JD 对齐/格式），叠加规则检查
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from json_task import ask_validated_json

DRAFT_SYSTEM_PROMPT = """你是中文求职信撰写助手，为校招实习生岗位写一封求职信。只输出信件正文，不要任何解释或 markdown。

写作规则：
1. 证据只能来自给定的「项目经历」与「岗位JD」，禁止编造任何公司名、项目、数据；
2. 结构：称呼 → 一句话来源与身份 → 与 JD 对齐的经历段（2~3 条，点出 JD 具体要求）→ 到岗信息 → 署名与联系方式；
3. 全文 200~400 字，禁止空话套话单独成段（如「吃苦耐劳」「团队协作」无证据支撑的段落）；
4. 语气诚恳专业，不用表情符号。"""

QA_SYSTEM_PROMPT = """你是求职信质检审稿人。对照「项目经历」与「岗位JD」审查求职信，只输出一个 JSON 对象。

检查项：
1. 编造证据：信中是否出现项目经历里不存在的公司/项目/数据（最严重）；
2. 空话套话：是否存在无证据支撑的空洞表态；
3. JD 对齐：是否回应了 JD 的核心要求（至少一条具体对应）；
4. 格式：是否有称呼、署名；长度是否在 150~500 字。

输出字段：
- passed: 布尔，是否通过
- issues: 问题列表（字符串，每条以检查项开头，如 "编造证据: ..."；通过则空列表）
- severity: "high"（有编造或严重不对齐）或 "low"（小瑕疵）

规则：严格、具体、可执行；输出必须是合法 JSON。"""

_RULE_BANNED_EMPTY_PHRASES = ("吃苦耐劳", "无私奉献", "任劳任怨")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


class QAVerdict(BaseModel):
    passed: bool = False
    issues: list[str] = Field(default_factory=list)
    severity: str = "low"


def draft_cover_letter_llm(
    profile: dict[str, Any],
    lead: dict[str, Any],
    jd_info: dict[str, Any] | None = None,
    match_verdict: dict[str, Any] | None = None,
    retrieved_chunks: list[dict[str, Any]] | None = None,
    client: Any = None,
    extra_instructions: str = "",
    max_tokens: int = 800,
) -> str:
    """生成求职信正文。extra_instructions 携带上一轮质检问题（回退重写时）。"""
    ident = profile.get("identity") or {}
    cons = profile.get("constraints") or {}
    hl_lines = "\n".join(
        f"- {h.get('title', '')}：{h.get('blurb', '')}"
        + (f"（指标: {'、'.join(h.get('metrics') or [])}）" if h.get("metrics") else "")
        for h in (profile.get("highlights") or [])[:6]
    ) or "（无）"
    jd_points = "\n".join(f"- {c['text'][:150]}" for c in (retrieved_chunks or [])[:5]) or lead.get("jd_summary") or "（无）"
    match_line = ""
    if match_verdict:
        match_line = f"\n匹配评估要点：{'；'.join((match_verdict.get('reasons') or [])[:3])}"

    jd_info = jd_info or {}
    user = f"""【申请信息】
公司: {jd_info.get('company') or lead.get('company') or '贵司'}
岗位: {jd_info.get('job_title') or lead.get('job_title') or ''}
JD 来源: {lead.get('source_url') or '招聘信息'}

【项目经历（证据只能来自这里）】
{hl_lines}
【岗位 JD 要点】
{jd_points}{match_line}

【署名信息】
姓名: {ident.get('name') or '（姓名）'}  电话: {ident.get('phone') or '未填'}
学校专业: {'；'.join(f"{e.get('school','')}{e.get('major','')}" for e in (profile.get('education') or []))}
到岗: {cons.get('available_from') or '近期'}  实习周期: {cons.get('available_duration') or '未填'}"""

    if extra_instructions:
        user += f"\n\n【上一稿未通过质检，修改时必须解决】\n{extra_instructions}"

    resp = client.chat(
        [
            {"role": "system", "content": DRAFT_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        purpose="draft_cover_letter",
        temperature=0.4,
        max_tokens=max_tokens,
    )
    return resp.content.strip()


def qa_cover_letter_rules(draft: str, lead: dict[str, Any]) -> list[str]:
    """规则质检（不花钱、必查）：长度 / 称呼署名 / 套话 / 占位符残留。"""
    issues: list[str] = []
    text = (draft or "").strip()
    if len(text) < 120:
        issues.append(f"格式: 正文过短（{len(text)} 字 < 120）")
    if len(text) > 700:
        issues.append(f"格式: 正文过长（{len(text)} 字 > 700）")
    if "（姓名）" in text or "xxx" in text.lower():
        issues.append("格式: 存在未替换的占位符")
    for phrase in _RULE_BANNED_EMPTY_PHRASES:
        if phrase in text:
            issues.append(f"空话套话: 出现「{phrase}」且无证据支撑")
    return issues


def qa_cover_letter_llm(
    draft: str,
    profile: dict[str, Any],
    jd_text: str,
    client: Any,
    max_retries: int = 2,
) -> tuple[QAVerdict | None, dict[str, Any]]:
    """LLM 质检，返回 (QAVerdict | None, stats)。"""
    hl_lines = "\n".join(
        f"- {h.get('title', '')}：{h.get('blurb', '')}"
        for h in (profile.get("highlights") or [])[:6]
    ) or "（无）"
    user = f"""【项目经历（证据唯一来源）】
{hl_lines}

【岗位JD】
{jd_text or '（无）'}

【求职信】
{draft}"""
    messages = [
        {"role": "system", "content": QA_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    return ask_validated_json(
        client, messages, QAVerdict.model_validate,
        purpose="qa_cover_letter", max_retries=max_retries,
    )
