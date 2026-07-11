# -*- coding: utf-8 -*-
"""HTTP fetch helpers for public pages."""
from __future__ import annotations

import re
from typing import Any

import httpx

from extract import extract_emails_with_context

_USER_AGENT = "job-apply-agent/0.1 (+https://github.com/; public research crawler)"
_TAG_RE = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", re.I)
_HTML_RE = re.compile(r"<[^>]+>")


def html_to_text(html: str) -> str:
    if not html:
        return ""
    s = _TAG_RE.sub(" ", html)
    s = _HTML_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def fetch_url(url: str, timeout: float = 15.0) -> dict[str, Any]:
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            r = client.get(url, headers={"User-Agent": _USER_AGENT})
            text = r.text
            return {
                "ok": r.status_code < 400,
                "status_code": r.status_code,
                "url": str(r.url),
                "html": text,
                "text": html_to_text(text),
                "error": "",
            }
    except Exception as e:
        return {
            "ok": False,
            "status_code": 0,
            "url": url,
            "html": "",
            "text": "",
            "error": str(e),
        }


def fetch_and_extract_emails(url: str, timeout: float = 15.0) -> dict[str, Any]:
    res = fetch_url(url, timeout=timeout)
    emails = extract_emails_with_context(res.get("text") or "")
    res["emails"] = emails
    return res
