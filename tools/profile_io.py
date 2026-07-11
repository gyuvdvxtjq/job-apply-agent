# -*- coding: utf-8 -*-
"""Profile schema, load/save, and light validation. No personal hardcoding."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from common import repo_root

PROFILE_SCHEMA_VERSION = 1

EMPTY_PROFILE: dict[str, Any] = {
    "schema_version": PROFILE_SCHEMA_VERSION,
    "identity": {
        "name": "",
        "phone": "",
        "email": "",
        "github": "",
    },
    "education": [],
    # education item: {school, major, degree, grade_or_grad_year}
    "skills": [],
    "directions": [],
    "highlights": [],
    # highlight: {title, skills[], metrics[], blurb}
    "constraints": {
        "cities": [],
        "available_from": "",
        "available_duration": "",
        "exclude_companies": [],
        "exclude_keywords": [],
    },
    "raw_text_excerpt": "",
}


def empty_profile() -> dict[str, Any]:
    return deepcopy(EMPTY_PROFILE)


def load_profile(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"profile not found: {p}")
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    base = empty_profile()
    return _merge_profile(base, data)


def save_profile(path: str | Path, profile: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # YAML for human edit
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(profile, f, allow_unicode=True, sort_keys=False)


def _merge_profile(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for key in ("identity", "constraints"):
        if isinstance(override.get(key), dict):
            out[key] = {**out.get(key, {}), **override[key]}
    for key in ("education", "skills", "directions", "highlights"):
        if key in override and override[key] is not None:
            out[key] = override[key]
    if override.get("raw_text_excerpt"):
        out["raw_text_excerpt"] = override["raw_text_excerpt"]
    if override.get("schema_version"):
        out["schema_version"] = override["schema_version"]
    return out


def apply_overrides(profile: dict, overrides: dict | None) -> dict:
    if not overrides:
        return profile
    out = deepcopy(profile)
    # flat identity fields
    for k in ("name", "phone", "email", "github"):
        if overrides.get(k):
            out.setdefault("identity", {})[k] = overrides[k]
    cons = out.setdefault("constraints", {})
    for k in ("cities", "directions", "available_from", "available_duration",
              "exclude_companies", "exclude_keywords"):
        if k == "directions" and overrides.get("directions"):
            out["directions"] = list(overrides["directions"])
        elif overrides.get(k) not in (None, [], ""):
            cons[k] = overrides[k]
    return out


def validate_profile(profile: dict) -> list[str]:
    """Return list of warnings (empty if ok enough to run)."""
    warnings: list[str] = []
    ident = profile.get("identity") or {}
    if not ident.get("name"):
        warnings.append("identity.name 为空：求职信署名会受影响")
    if not profile.get("skills") and not profile.get("highlights"):
        warnings.append("skills 与 highlights 皆空：匹配与写信质量会很差，请编辑 profile")
    if not profile.get("directions") and not (profile.get("constraints") or {}).get("cities"):
        warnings.append("directions 与 cities 皆空：搜索计划会过于宽泛")
    return warnings


def profile_summary(profile: dict) -> str:
    ident = profile.get("identity") or {}
    edu = profile.get("education") or []
    school = edu[0].get("school", "") if edu else ""
    cities = (profile.get("constraints") or {}).get("cities") or []
    dirs = profile.get("directions") or []
    return (
        f"{ident.get('name') or '(未命名)'} | {school or '学校未填'} | "
        f"方向:{','.join(dirs) or '-'} | 城市:{','.join(cities) or '-'}"
    )
