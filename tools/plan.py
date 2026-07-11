# -*- coding: utf-8 -*-
"""Build search plan.json from profile + profiles.json + sources (no network)."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

from common import ensure_utf8_stdio, read_json, repo_root, write_json
from config_loader import load_config, resolve_path
from profile_io import apply_overrides, load_profile, profile_summary, validate_profile
from registry import SourceRegistry


def build_plan(
    profile: dict,
    profile_name: str = "standard",
    cfg: dict | None = None,
) -> dict:
    root = repo_root()
    profiles = read_json(root / "profiles.json", default={}) or {}
    knobs = profiles.get(profile_name) or profiles.get("standard") or {}
    reg = SourceRegistry()
    max_q = int(knobs.get("max_search_queries") or 16)
    queries = reg.expand_query_templates(profile, max_queries=max_q)

    university_portals = []
    if cfg:
        univ = ((cfg.get("sources") or {}).get("university_career") or {})
        if univ.get("enabled", True):
            university_portals = list(univ.get("portals") or [])

    import_paths = []
    if cfg:
        im = ((cfg.get("sources") or {}).get("imports") or {})
        if im.get("enabled", True):
            import_paths = list(im.get("paths") or [])

    plan = {
        "created_at": datetime.now().isoformat(),
        "profile_summary": profile_summary(profile),
        "run_profile": profile_name,
        "knobs": knobs,
        "directions": profile.get("directions") or [],
        "cities": (profile.get("constraints") or {}).get("cities") or [],
        "exclude_companies": (profile.get("constraints") or {}).get("exclude_companies") or [],
        "enable_layers": knobs.get("enable_layers") or ["L0", "L3"],
        "search_queries": queries,
        "university_portals": university_portals,
        "import_paths": import_paths,
        "curated_source_ids": [s.get("id") for s in reg.list_sources() if s.get("layer") in (knobs.get("enable_layers") or [])],
        "blocked_domains": sorted(reg.blocked),
        "target_leads": knobs.get("target_leads") or 20,
        "auto_send": False,  # hard rule: plan never enables auto send
        "notes": [
            "L0 宿主搜索由 Claude Skill 执行（WebSearch/tinyfish 等）",
            "默认只生成 ready，不自动 send",
            "大学就业网 / 双选会导入请在 config.yaml 配置",
        ],
    }
    return plan


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Build plan.json from profile")
    parser.add_argument("--config", default=None)
    parser.add_argument("--profile-file", default=None, help="profile.yaml path")
    parser.add_argument("--run-profile", default=None, help="quick|standard|deep")
    parser.add_argument("--out", default=None, help="output plan.json")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    profile_path = args.profile_file or cfg.get("profile_path") or "profile.yaml"
    profile_path = resolve_path(cfg, profile_path)
    if not profile_path.exists():
        print(f"❌ profile 不存在: {profile_path}")
        print("   先运行: python tools/cli.py parse-resume --pdf your.pdf")
        return 1

    profile = load_profile(profile_path)
    profile = apply_overrides(profile, cfg.get("user_overrides"))
    for w in validate_profile(profile):
        print(f"⚠️  {w}")

    run_profile = args.run_profile or (cfg.get("pipeline") or {}).get("profile") or "standard"
    plan = build_plan(profile, run_profile, cfg)

    out = Path(args.out) if args.out else Path(cfg.get("run", {}).get("work_dir") or "runs") / "plan.json"
    if not out.is_absolute():
        out = resolve_path(cfg, str(out)) if args.out else repo_root() / out
    write_json(out, plan)
    print(f"✅ plan 已写入 {out}")
    print(f"   档位: {run_profile} | 查询数: {len(plan['search_queries'])} | 目标线索: {plan['target_leads']}")
    print("   示例查询:")
    for q in plan["search_queries"][:5]:
        print(f"   - {q}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
