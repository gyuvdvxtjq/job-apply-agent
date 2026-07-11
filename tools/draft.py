# -*- coding: utf-8 -*-
"""Skeleton cover-letter builder from profile evidence (Skill should refine)."""
from __future__ import annotations

from match import match_score


def build_cover_letter(profile: dict, company: str, job_title: str, jd_summary: str = "",
                       source_hint: str = "") -> str:
    ident = profile.get("identity") or {}
    name = ident.get("name") or "（姓名）"
    phone = ident.get("phone") or ""
    github = ident.get("github") or ""
    edu = (profile.get("education") or [{}])[0]
    school = edu.get("school") or ""
    major = edu.get("major") or ""
    cons = profile.get("constraints") or {}
    available = cons.get("available_from") or ""
    duration = cons.get("available_duration") or ""

    m = match_score(profile, f"{job_title}\n{jd_summary}")
    highlights = m.get("selected_highlights") or profile.get("highlights") or []
    skills = m.get("matched_skills") or (profile.get("skills") or [])[:6]

    where = source_hint or "贵司招聘信息"
    lines = []
    lines.append(f"{company or '贵司'}招聘负责人/HR 您好：")
    lines.append("")
    intro_bits = []
    if school:
        intro_bits.append(school)
    if major:
        intro_bits.append(f"{major}专业")
    intro_bits.append(f"学生{name}" if name != "（姓名）" else "本人")
    lines.append(
        f"我是{('、'.join(intro_bits))}，在{where}看到「{job_title or '实习'}」岗位，特此投递简历。"
    )
    lines.append("")

    if skills:
        lines.append(f"与岗位相关的技能包括：{', '.join(skills)}。")
    if highlights:
        lines.append("相关经历：")
        for h in highlights[:3]:
            title = h.get("title") or "项目经历"
            blurb = h.get("blurb") or ""
            metrics = "、".join(h.get("metrics") or [])
            piece = f"- {title}"
            if metrics:
                piece += f"（{metrics}）"
            if blurb and blurb != title:
                piece += f"：{blurb[:120]}"
            lines.append(piece)
    else:
        lines.append("（请在 profile.yaml 的 highlights 中补充可验证的项目证据后重试生成。）")

    lines.append("")
    tail = "期待有机会进一步沟通。"
    if available or duration:
        tail = f"我可在{available or '近期'}到岗" + (f"，实习周期{duration}" if duration else "") + "。" + tail
    lines.append(tail)
    lines.append("简历见附件，感谢阅读。")
    lines.append("")
    lines.append(name)
    if phone:
        lines.append(f"电话：{phone}")
    if github:
        lines.append(f"GitHub：{github}")
    return "\n".join(lines)
