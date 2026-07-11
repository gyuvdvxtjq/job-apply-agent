# -*- coding: utf-8 -*-
"""Collect leads from imports + optional URL fetches. Skill handles L0 web search.

This CLI stage is intentionally partial: full multi-source fan-out is orchestrated
by Claude Skill using plan.json + tools here.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from common import ensure_utf8_stdio, read_json, repo_root, write_json
from config_loader import load_config, resolve_path
from extract import extract_emails_with_context, score_email_for_job
from profile_io import apply_overrides, load_profile
from registry import SourceRegistry
from store import JobLeads, SentLog
from adapters.imports import load_import_file
from adapters.fetch import fetch_and_extract_emails
from match import is_excluded_company


def collect_from_imports(paths: list[str], profile: dict, leads: JobLeads, sent: SentLog) -> int:
    added = 0
    for path in paths:
        rows = load_import_file(path)
        for row in rows:
            company = row.get("company") or ""
            email = row.get("contact_email") or ""
            job = row.get("job_title") or "实习生"
            if not company and not email:
                continue
            if company and is_excluded_company(profile, company):
                continue
            if email and sent.is_sent(email):
                continue
            if email and leads.find_by_email(email):
                continue
            leads.add(
                company=company or "(未知公司)",
                job_title=job,
                contact_email=email,
                jd_summary=row.get("jd_summary") or "",
                source_url=row.get("source_url") or "",
                source_type="import",
                confidence=0.7 if email else 0.3,
            )
            added += 1
    return added


def collect_from_urls(urls: list[str], profile: dict, leads: JobLeads, sent: SentLog, reg: SourceRegistry) -> int:
    added = 0
    for url in urls:
        if reg.is_blocked_url(url):
            print(f"跳过屏蔽域: {url}")
            continue
        print(f"抓取: {url}")
        res = fetch_and_extract_emails(url)
        if not res.get("ok"):
            print(f"  失败: {res.get('error') or res.get('status_code')}")
            continue
        for item in res.get("emails") or []:
            email = item["email"]
            if sent.is_sent(email) or leads.find_by_email(email):
                continue
            conf = score_email_for_job(email, source_url=url, preferred_locals=reg.email_priority)
            if item.get("has_recruiting_context"):
                conf = min(1.0, conf + 0.15)
            leads.add(
                company="",
                job_title="实习生",
                contact_email=email,
                jd_summary=(item.get("context") or "")[:300],
                source_url=res.get("url") or url,
                source_type="fetch",
                confidence=round(conf, 3),
            )
            added += 1
    return added


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Collect leads (imports + URL list)")
    parser.add_argument("--config", default=None)
    parser.add_argument("--plan", default=None, help="plan.json path")
    parser.add_argument("--url", action="append", default=[], help="Extra URL to fetch (repeatable)")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    plan_path = Path(args.plan) if args.plan else repo_root() / "runs" / "plan.json"
    plan = read_json(plan_path, default={}) or {}

    profile_path = resolve_path(cfg, cfg.get("profile_path") or "profile.yaml")
    profile = {}
    if profile_path.exists():
        profile = apply_overrides(load_profile(profile_path), cfg.get("user_overrides"))

    data_dir = resolve_path(cfg, args.data_dir)
    leads = JobLeads(data_dir)
    sent = SentLog(data_dir)
    reg = SourceRegistry()

    import_paths = list(plan.get("import_paths") or [])
    im_cfg = ((cfg.get("sources") or {}).get("imports") or {})
    for p in im_cfg.get("paths") or []:
        if p not in import_paths:
            import_paths.append(p)

    n1 = collect_from_imports(import_paths, profile, leads, sent)
    urls = list(args.url or [])
    # university portals from plan
    for portal in plan.get("university_portals") or []:
        u = portal.get("list_url") if isinstance(portal, dict) else None
        if u:
            urls.append(u)
    n2 = collect_from_urls(urls, profile, leads, sent, reg)

    pool = {
        "created_at": datetime.now().isoformat(),
        "from_imports": n1,
        "from_urls": n2,
        "total_leads": sum(leads.count_by_status().values()),
        "counts": leads.count_by_status(),
    }
    out = repo_root() / "runs" / "lead_pool_meta.json"
    write_json(out, pool)
    print(f"✅ 采集完成: imports+{n1}, urls+{n2}")
    print(f"   当前线索: {pool['counts']}")
    print("   L0 网页搜索请由 Claude Skill 按 plan.search_queries 执行并 add 线索")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
