# -*- coding: utf-8 -*-
"""Extract text from resume PDF and build a draft profile (rules + optional structure).

LLM-based deep structure is done by Claude Skill after this tool dumps text.
This module always works offline with heuristics so the CLI is usable without AI.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from common import ensure_utf8_stdio, repo_root
from profile_io import empty_profile, save_profile, validate_profile

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"1[3-9]\d{9}")
_GITHUB_RE = re.compile(r"https?://github\.com/[A-Za-z0-9_.\-]+/?")
_URL_RE = re.compile(r"https?://[^\s)\]>]+")

# Direction keywords (extensible; not user-specific)
DIRECTION_KEYWORDS = {
    "数据分析": ["数据分析", "data analysis", "data analyst", "商业分析", "数据开发"],
    "AI Agent": ["ai agent", "智能体", "agent", "工具调用", "tool use"],
    "AIGC": ["aigc", "生成式", "内容生成"],
    "LLM应用": ["llm", "大模型", "prompt", "rag", "微调"],
    "机器学习": ["机器学习", "machine learning", "深度学习", "ml", "deep learning"],
    "后端开发": ["后端", "backend", "java", "go ", "spring"],
    "前端开发": ["前端", "frontend", "react", "vue"],
    "算法": ["算法", "algorithm", "计算机视觉", "cv", "nlp"],
}

SKILL_LEXICON = [
    "Python", "Java", "C++", "Go", "JavaScript", "TypeScript", "SQL",
    "Pandas", "NumPy", "PyTorch", "TensorFlow", "Spark", "PySpark",
    "Docker", "Kubernetes", "Linux", "Git", "FastAPI", "Flask", "Django",
    "React", "Vue", "LangChain", "Claude", "OpenAI", "RAG", "Prompt",
    "Excel", "Tableau", "PowerBI", "Shiny", "MATLAB",
]


def extract_pdf_text(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise SystemExit("需要 pypdf：pip install pypdf") from e
    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()


def _guess_name(lines: list[str]) -> str:
    for line in lines[:12]:
        s = line.strip()
        if not s or len(s) > 20:
            continue
        if _EMAIL_RE.search(s) or _PHONE_RE.search(s) or "http" in s.lower():
            continue
        if re.fullmatch(r"[一-鿿·]{2,8}", s):
            return s
        if re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", s):
            return s
    return ""


def _guess_education(text: str) -> list[dict]:
    edu = []
    # 简单模式：含「大学」的行
    for line in text.splitlines():
        if "大学" in line or "学院" in line or "University" in line:
            school = line.strip()[:80]
            major = ""
            m = re.search(r"(专业[:：]\s*|Major[:：]\s*)([^\s,，|]+)", line)
            if m:
                major = m.group(2)
            edu.append({
                "school": school,
                "major": major,
                "degree": "",
                "grade_or_grad_year": "",
            })
            if len(edu) >= 2:
                break
    return edu


def _guess_skills(text: str) -> list[str]:
    found = []
    lower = text.lower()
    for sk in SKILL_LEXICON:
        if sk.lower() in lower or sk in text:
            if sk not in found:
                found.append(sk)
    # R language: match as whole word to avoid false positives
    if re.search(r'\bR\b', text) and "R" not in found:
        found.append("R")
    return found


def _guess_directions(text: str) -> list[str]:
    lower = text.lower()
    dirs = []
    for name, kws in DIRECTION_KEYWORDS.items():
        if any(kw.lower() in lower for kw in kws):
            dirs.append(name)
    return dirs


def _guess_highlights(text: str) -> list[dict]:
    """Heuristic project-like bullets; Claude Skill should refine."""
    highlights = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for i, ln in enumerate(lines):
        if len(ln) < 12:
            continue
        if any(k in ln for k in ("项目", "负责", "实现", "搭建", "设计", "优化", "Pipeline", "系统")):
            metrics = re.findall(r"\d+(?:\.\d+)?%|\d+(?:\.\d+)?\s*万?条|\d+(?:\.\d+)?\s*倍", ln)
            highlights.append({
                "title": ln[:40],
                "skills": [],
                "metrics": metrics[:4],
                "blurb": ln[:200],
            })
        if len(highlights) >= 8:
            break
    return highlights


def build_profile_from_text(text: str) -> dict:
    profile = empty_profile()
    lines = text.splitlines()
    emails = _EMAIL_RE.findall(text)
    phones = _PHONE_RE.findall(text)
    githubs = _GITHUB_RE.findall(text)

    profile["identity"]["name"] = _guess_name(lines)
    profile["identity"]["email"] = emails[0] if emails else ""
    profile["identity"]["phone"] = phones[0] if phones else ""
    profile["identity"]["github"] = githubs[0] if githubs else ""
    profile["education"] = _guess_education(text)
    profile["skills"] = _guess_skills(text)
    profile["directions"] = _guess_directions(text)
    profile["highlights"] = _guess_highlights(text)
    profile["raw_text_excerpt"] = text[:4000]
    return profile


def parse_resume(pdf_path: str | Path, out_path: str | Path) -> dict:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"resume not found: {pdf_path}")
    text = extract_pdf_text(pdf_path)
    if not text or len(text) < 40:
        raise ValueError("PDF 文本提取结果过短，请换可选中文本的 PDF，或手写 profile.yaml")
    profile = build_profile_from_text(text)
    save_profile(out_path, profile)
    return profile


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Parse resume PDF → profile.yaml")
    parser.add_argument("--pdf", required=True, help="Path to resume PDF")
    parser.add_argument("--out", default="profile.yaml", help="Output profile path")
    args = parser.parse_args(argv)

    profile = parse_resume(args.pdf, args.out)
    warns = validate_profile(profile)
    print(f"✅ 已写入 {args.out}")
    print(f"   姓名: {profile['identity'].get('name') or '(未识别，请手改)'}")
    print(f"   技能数: {len(profile.get('skills') or [])}")
    print(f"   方向: {', '.join(profile.get('directions') or []) or '(请手改)'}")
    print(f"   证据条数: {len(profile.get('highlights') or [])}")
    for w in warns:
        print(f"⚠️  {w}")
    print("提示: 请打开 profile.yaml 补全 cities / 到岗时间 / 项目证据，再跑 plan。")
    print("若使用 Claude Code，可用 Skill 在解析后深化 highlights。")
    return 0


if __name__ == "__main__":
    # allow `python tools/parse_resume.py` from repo root
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
