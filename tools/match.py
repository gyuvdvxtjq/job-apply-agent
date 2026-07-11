# -*- coding: utf-8 -*-
"""Match profile highlights/skills against a JD summary. Pure heuristics (CLI-safe)."""
from __future__ import annotations

import re
from typing import Any


def _tokens(text: str) -> set[str]:
    if not text:
        return set()
    parts = re.split(r"[\s,，、/|；;（）()\[\]+]+", text.lower())
    return {p for p in parts if len(p) >= 2}


def match_score(profile: dict, jd_text: str) -> dict[str, Any]:
    """Return score 0~1, matched skills, selected highlights."""
    jd = jd_text or ""
    jd_l = jd.lower()
    skills = profile.get("skills") or []
    highlights = profile.get("highlights") or []
    directions = profile.get("directions") or []

    matched_skills = []
    for sk in skills:
        if sk and sk.lower() in jd_l:
            matched_skills.append(sk)

    dir_hits = sum(1 for d in directions if d and d.lower() in jd_l)
    selected = []
    for h in highlights:
        blob = " ".join([
            h.get("title") or "",
            h.get("blurb") or "",
            " ".join(h.get("skills") or []),
            " ".join(h.get("metrics") or []),
        ]).lower()
        # overlap between highlight and jd tokens
        overlap = _tokens(blob) & _tokens(jd)
        skill_overlap = sum(1 for s in (h.get("skills") or []) if s.lower() in jd_l)
        score_h = len(overlap) * 0.05 + skill_overlap * 0.15
        # also bonus if any metric and jd mentions data/scale-ish words
        if h.get("metrics") and any(k in jd_l for k in ("数据", "分析", "模型", "python", "ai", "agent")):
            score_h += 0.1
        selected.append((score_h, h))
    selected.sort(key=lambda x: x[0], reverse=True)
    top = [h for s, h in selected if s > 0][:4]
    if not top and highlights:
        top = highlights[:2]

    skill_score = min(0.5, 0.1 * len(matched_skills))
    dir_score = min(0.2, 0.1 * dir_hits)
    hl_score = min(0.3, 0.08 * len(top))
    total = min(1.0, skill_score + dir_score + hl_score + (0.1 if matched_skills or top else 0.0))

    # exclude keywords
    excludes = (profile.get("constraints") or {}).get("exclude_keywords") or []
    for kw in excludes:
        if kw and kw.lower() in jd_l:
            total = min(total, 0.2)

    return {
        "score": round(total, 3),
        "matched_skills": matched_skills,
        "selected_highlights": top,
        "direction_hits": dir_hits,
    }


def is_excluded_company(profile: dict, company: str) -> bool:
    excludes = (profile.get("constraints") or {}).get("exclude_companies") or []
    c = (company or "").lower()
    return any(ex and ex.lower() in c for ex in excludes)
