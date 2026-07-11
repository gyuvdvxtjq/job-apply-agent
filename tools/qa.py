# -*- coding: utf-8 -*-
"""QA gate: filter/skip bad leads; never auto-send."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from common import ensure_utf8_stdio, read_json, repo_root
from config_loader import load_config, resolve_path
from extract import looks_like_public_mail_provider
from match import is_excluded_company, match_score
from profile_io import apply_overrides, load_profile
from registry import SourceRegistry
from store import JobLeads

_EMAIL_OK = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def qa_lead(lead: dict, profile: dict, reg: SourceRegistry, min_score: float,
            require_url: bool) -> tuple[bool, str]:
    email = (lead.get("contact_email") or "").strip()
    company = lead.get("company") or ""
    body = lead.get("body") or ""
    url = lead.get("source_url") or ""

    if not email or not _EMAIL_OK.match(email):
        return False, "无效邮箱"
    if reg.is_blocked_url(url):
        return False, "来源域在屏蔽列表"
    if require_url and not url:
        return False, "缺少 source_url"
    if company and is_excluded_company(profile, company):
        return False, "公司在排除列表"
    jd = " ".join([lead.get("job_title") or "", lead.get("jd_summary") or ""])
    ms = match_score(profile, jd)
    score = lead.get("match_score")
    if score is None:
        score = ms["score"]
        lead["match_score"] = score
    if score < min_score and not body:
        return False, f"匹配分过低 {score}<{min_score}"
    if body and len(body.strip()) < 80:
        return False, "求职信过短"
    # personal mailbox warning only — still allow if recruiting context
    conf = lead.get("confidence")
    if looks_like_public_mail_provider(email) and (conf is not None and conf < 0.5):
        return False, "个人邮箱且置信度低"
    return True, "ok"


def run_qa(data_dir: Path, profile: dict, min_score: float, require_url: bool) -> dict:
    leads = JobLeads(data_dir)
    reg = SourceRegistry()
    stats = {"checked": 0, "ready": 0, "skipped": 0, "pending_kept": 0}
    for lead in leads.list():
        if lead.get("status") not in ("pending", "ready"):
            continue
        stats["checked"] += 1
        ok, reason = qa_lead(lead, profile, reg, min_score, require_url)
        if not ok:
            leads.mark_skipped(lead["id"], reason)
            stats["skipped"] += 1
            print(f"⏭  #{lead['id']} skipped: {reason}")
        else:
            # keep ready if has body; else pending
            if lead.get("body"):
                if lead.get("status") != "ready":
                    leads.set_body(lead["id"], lead["body"])
                stats["ready"] += 1
            else:
                stats["pending_kept"] += 1
    return stats


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="QA leads → skip bad ones")
    parser.add_argument("--config", default=None)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--min-score", type=float, default=None)
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    profile_path = resolve_path(cfg, cfg.get("profile_path") or "profile.yaml")
    if not profile_path.exists():
        print(f"❌ 需要 profile: {profile_path}")
        return 1
    profile = apply_overrides(load_profile(profile_path), cfg.get("user_overrides"))

    knobs = {}
    try:
        profiles = read_json(repo_root() / "profiles.json", default={}) or {}
        name = (cfg.get("pipeline") or {}).get("profile") or "standard"
        knobs = profiles.get(name) or {}
    except Exception:
        knobs = {}
    min_score = args.min_score if args.min_score is not None else float(knobs.get("min_match_score") or 0.35)
    require_url = bool((cfg.get("pipeline") or {}).get("require_source_url", True))
    data_dir = resolve_path(cfg, args.data_dir)
    stats = run_qa(data_dir, profile, min_score, require_url)
    print(f"✅ QA 完成: {stats}")
    print("默认不发送。审查: python tools/cli.py list --status ready")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
