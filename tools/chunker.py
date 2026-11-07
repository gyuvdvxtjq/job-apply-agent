# -*- coding: utf-8 -*-
"""JD 分块：按「岗位职责 / 任职要求 / 其他」语义分块。

设计：JD 是高度模板化文本，段落标题本身就是语义边界。按标题切分而非
固定滑动窗口，保证每个 chunk 自成一个可检索、可展示的语义单元
（检索粒度 = 展示粒度）。无法识别标题的 JD 整体或按句切分，全部归入「其他」。
"""
from __future__ import annotations

import re
from typing import Any

# (标题正则, 归入的语义桶)。标题行要求短行命中，避免正文里偶然出现关键词被误切。
SECTION_PATTERNS: list[tuple[str, str]] = [
    (r"岗位职责|工作职责|职位职责|工作内容|职责描述|岗位描述|职位描述", "职责"),
    (r"任职要求|任职资格|岗位要求|职位要求|任职条件|招聘要求|资格要求|能力要求|加分项|优先条件", "要求"),
    (r"福利待遇|薪资待遇|薪酬福利|我们提供|工作地点|办公地点|公司简介|公司介绍|"
     r"关于我们|团队介绍|投递方式|简历投递|联系方式|截止时间|截止日期", "其他"),
]

_MAX_HEADER_LEN = 30

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;\n])")


_EXACT_OTHER = {"其他", "其他事项", "其他说明"}
_PUNCT_ONLY = re.compile(r"[：:、，,\s]*")


def _match_bucket(text: str) -> str | None:
    """命中标题关键词且残余只剩标点/空白才认定为标题。

    「工作地点深圳，简历投递至 hr@x.com」这类含关键词的正文不会误判；
    「工作地点：深圳」这类 KV 行也保留为正文，避免丢内容。
    """
    t = text.strip()
    if t.rstrip("：: 、，,") in _EXACT_OTHER:
        return "其他"
    for pattern, bucket in SECTION_PATTERNS:
        if re.search(pattern, t):
            residual = re.sub(pattern, "", t).strip()
            if _PUNCT_ONLY.fullmatch(residual or ""):
                return bucket
    return None


def _detect_section(line: str) -> str | None:
    """若该行是标题行，返回语义桶名；否则 None。

    支持「岗位职责：」「【岗位职责】」「一、任职要求」等常见写法。
    """
    s = line.strip()
    if not s or len(s) > _MAX_HEADER_LEN:
        return None
    candidates = [s]
    m = re.match(r"^[【\[]([^【\]】]{0,20})[】\]]\s*(.*)$", s)
    if m:
        candidates = [m.group(1)]
        if m.group(2).strip():
            candidates.append(m.group(2).strip())
    for c in candidates:
        c = re.sub(r"^(?:[一二三四五六七八九十]+[、.．]|\d+[、.．]|#{1,4}\s*)", "", c).strip()
        if not c:
            continue
        bucket = _match_bucket(c)
        if bucket is not None:
            return bucket
    return None


def _split_long_text(text: str, max_chars: int) -> list[str]:
    """按句子边界把超长段落切成 ≤max_chars 的块。"""
    if len(text) <= max_chars:
        return [text] if text.strip() else []
    sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    parts: list[str] = []
    buf = ""
    for sent in sentences:
        if buf and len(buf) + len(sent) > max_chars:
            parts.append(buf)
            buf = sent
        else:
            buf += sent
        while len(buf) > max_chars * 2:
            # 单句超长的极端情况，硬切
            parts.append(buf[:max_chars])
            buf = buf[max_chars:]
    if buf.strip():
        parts.append(buf)
    return [p for p in (x.strip() for x in parts) if p]


def chunk_jd(
    jd_text: str,
    job_id: str = "",
    max_chars: int = 500,
) -> list[dict[str, Any]]:
    """把一段 JD 文本切成块。

    返回 list[{"chunk_id", "job_id", "section", "idx", "text"}]，
    chunk_id 形如 "{job_id}::要求::0"。
    """
    lines = (jd_text or "").splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_bucket, current_lines = "其他", []

    for line in lines:
        bucket = _detect_section(line)
        if bucket is not None:
            if current_lines:
                sections.append((current_bucket, current_lines))
            current_bucket, current_lines = bucket, []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_bucket, current_lines))

    # 合并相邻同桶（例如「职责」后跟「工作内容」两段标题）
    merged: list[tuple[str, list[str]]] = []
    for bucket, ls in sections:
        if merged and merged[-1][0] == bucket:
            merged[-1][1].extend(ls)
        else:
            merged.append((bucket, ls))

    chunks: list[dict[str, Any]] = []
    counters: dict[str, int] = {}
    for bucket, ls in merged:
        text = "\n".join(ls).strip()
        if not text:
            continue
        for part in _split_long_text(text, max_chars):
            i = counters.get(bucket, 0)
            counters[bucket] = i + 1
            chunks.append(
                {
                    "chunk_id": f"{job_id}::{bucket}::{i}",
                    "job_id": job_id,
                    "section": bucket,
                    "idx": i,
                    "text": part,
                }
            )
    return chunks
