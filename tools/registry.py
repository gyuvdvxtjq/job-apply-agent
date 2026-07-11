# -*- coding: utf-8 -*-
"""Source registry: load sources.json, health-check, filter blocked domains."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx

from common import read_json, repo_root


class SourceRegistry:
    def __init__(self, sources_path: str | Path | None = None):
        root = repo_root()
        path = Path(sources_path) if sources_path else root / "sources.json"
        data = read_json(path, default={}) or {}
        self.path = path
        self.meta = data
        self.sources: list[dict] = list(data.get("sources") or [])
        self.blocked = set(data.get("blocked_domains") or [])
        self.email_priority = list(data.get("email_local_part_priority") or [])

    def list_sources(self, layer: str | None = None, enabled_only: bool = False) -> list[dict]:
        items = self.sources
        if layer:
            items = [s for s in items if s.get("layer") == layer]
        if enabled_only:
            items = [s for s in items if s.get("enabled", True)]
        return items

    def is_blocked_url(self, url: str) -> bool:
        u = (url or "").lower()
        return any(d in u for d in self.blocked)

    def expand_query_templates(self, profile: dict, max_queries: int = 16) -> list[str]:
        directions = profile.get("directions") or ["实习"]
        cities = (profile.get("constraints") or {}).get("cities") or [""]
        templates: list[str] = []
        for src in self.sources:
            if src.get("type") != "search_query":
                continue
            for t in src.get("query_templates") or []:
                templates.append(t)
        queries: list[str] = []
        for d in directions:
            for c in cities:
                for t in templates:
                    q = t.format(direction=d, city=c).strip()
                    q = " ".join(q.split())
                    if q and q not in queries:
                        queries.append(q)
                    if len(queries) >= max_queries:
                        return queries
        # fallback generic
        if not queries:
            for d in directions:
                queries.append(f"{d} 实习 邮箱")
        return queries[:max_queries]

    def render_url(self, source: dict, query: str) -> str | None:
        tpl = source.get("url_template")
        if not tpl:
            return None
        try:
            return tpl.format(query=quote_plus(query))
        except Exception:
            return tpl

    def health_check(self, timeout: float = 8.0, limit: int | None = None) -> list[dict]:
        targets = [s for s in self.sources if s.get("health_url")]
        if limit:
            targets = targets[:limit]
        results: list[dict] = []

        def _one(src: dict) -> dict:
            url = src["health_url"]
            t0 = time.time()
            try:
                with httpx.Client(follow_redirects=True, timeout=timeout) as client:
                    r = client.get(url, headers={"User-Agent": "job-apply-agent/0.1"})
                    ok = r.status_code < 500
                    return {
                        "id": src.get("id"),
                        "name": src.get("name"),
                        "ok": ok,
                        "status_code": r.status_code,
                        "ms": int((time.time() - t0) * 1000),
                    }
            except Exception as e:
                return {
                    "id": src.get("id"),
                    "name": src.get("name"),
                    "ok": False,
                    "error": str(e),
                    "ms": int((time.time() - t0) * 1000),
                }

        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(_one, s) for s in targets]
            for f in as_completed(futs):
                results.append(f.result())
        results.sort(key=lambda x: x.get("id") or "")
        return results

    def alive_ids(self, health: list[dict] | None = None) -> set[str]:
        health = health if health is not None else self.health_check()
        return {h["id"] for h in health if h.get("ok")}
