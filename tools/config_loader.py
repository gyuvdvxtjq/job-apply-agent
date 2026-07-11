# -*- coding: utf-8 -*-
"""Load config.example / config.yaml with env overrides."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from common import env_or, repo_root


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    root = repo_root()
    if config_path is None:
        candidate = root / "config.yaml"
        if not candidate.exists():
            candidate = root / "config.example.yaml"
        config_path = candidate
    path = Path(config_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Env overrides for secrets
    smtp = cfg.setdefault("smtp", {})
    if env_or("SMTP_SERVER"):
        smtp["server"] = env_or("SMTP_SERVER")
    if env_or("SMTP_PORT"):
        smtp["port"] = int(env_or("SMTP_PORT"))
    if env_or("SMTP_EMAIL"):
        smtp["email"] = env_or("SMTP_EMAIL")
    if env_or("SMTP_PASSWORD"):
        smtp["password"] = env_or("SMTP_PASSWORD")

    cfg["_config_path"] = str(path)
    cfg["_config_dir"] = str(path.parent)
    cfg["_repo_root"] = str(root)
    return cfg


def resolve_path(cfg: dict, raw: str) -> Path:
    p = Path(raw)
    if p.is_absolute():
        return p
    base = Path(cfg.get("_config_dir") or repo_root())
    return (base / p).resolve()
