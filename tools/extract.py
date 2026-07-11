# -*- coding: utf-8 -*-
"""Email extraction and light contact validation."""
from __future__ import annotations

import re
from urllib.parse import urlparse

_IGNORED_SUFFIXES = {".png", ".jpg", ".jpeg", ".css", ".js", ".svg", ".gif", ".woff", ".ico"}
_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# contexts that suggest recruiting contact
_CTX_HINTS = re.compile(
    r"(简历|投递|实习|校招|招聘|HR|邮箱|email|apply|intern|campus|career)",
    re.I,
)


def extract_emails_from_text(text: str) -> list[str]:
    if not text:
        return []
    raw = _EMAIL_PATTERN.findall(text)
    seen: set[str] = set()
    result: list[str] = []
    for email in raw:
        el = email.lower()
        if any(el.endswith(suf) for suf in _IGNORED_SUFFIXES):
            continue
        local = el.split("@", 1)[0]
        if re.search(r"\.(png|jpe?g|css|js|svg|gif|woff|ico|bmp|webp)$", local):
            continue
        if el not in seen:
            seen.add(el)
            result.append(email)
    return result


def extract_emails_with_context(text: str, window: int = 40) -> list[dict]:
    """Return emails with nearby text and a weak recruiting-context flag."""
    if not text:
        return []
    out = []
    for m in _EMAIL_PATTERN.finditer(text):
        email = m.group(0)
        start = max(0, m.start() - window)
        end = min(len(text), m.end() + window)
        ctx = text[start:end].replace("\n", " ")
        out.append({
            "email": email,
            "context": ctx,
            "has_recruiting_context": bool(_CTX_HINTS.search(ctx)),
        })
    # dedupe by lower email, prefer recruiting context
    best: dict[str, dict] = {}
    for item in out:
        key = item["email"].lower()
        prev = best.get(key)
        if prev is None or (item["has_recruiting_context"] and not prev["has_recruiting_context"]):
            best[key] = item
    return list(best.values())


def domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def email_domain(email: str) -> str:
    if "@" not in email:
        return ""
    return email.split("@", 1)[1].lower()


def looks_like_public_mail_provider(email: str) -> bool:
    d = email_domain(email)
    return d in {
        "gmail.com", "qq.com", "163.com", "126.com", "sina.com", "outlook.com",
        "hotmail.com", "foxmail.com", "icloud.com", "yeah.net", "139.com",
    }


def score_email_for_job(email: str, company: str = "", source_url: str = "",
                        preferred_locals: list[str] | None = None) -> float:
    """Heuristic 0~1 score; higher is better for cold apply."""
    score = 0.4
    local = email.split("@", 1)[0].lower()
    preferred_locals = preferred_locals or [
        "campus", "hr", "jobs", "job", "recruit", "career", "careers",
        "internship", "intern", "apply", "talent",
    ]
    if any(local == p or local.startswith(p) for p in preferred_locals):
        score += 0.35
    if looks_like_public_mail_provider(email):
        score -= 0.15  # personal mailboxes are riskier but sometimes real HR
    host = domain_from_url(source_url)
    ed = email_domain(email)
    if host and ed and (ed in host or host.endswith(ed) or ed.endswith(host.split(".")[-2] + "." + host.split(".")[-1] if host.count(".") >= 1 else ed)):
        score += 0.2
    if company and company.lower().replace(" ", "") in email.lower():
        score += 0.1
    return max(0.0, min(1.0, score))
