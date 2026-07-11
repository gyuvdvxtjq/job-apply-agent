# -*- coding: utf-8 -*-
"""Import company/job rows from local CSV/JSON (job fair lists, park directories)."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def load_import_file(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [_normalize(x) for x in data]
        if isinstance(data, dict) and "items" in data:
            return [_normalize(x) for x in data["items"]]
        return []
    if p.suffix.lower() in {".csv", ".tsv"}:
        delim = "\t" if p.suffix.lower() == ".tsv" else ","
        rows = []
        with open(p, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=delim)
            for row in reader:
                rows.append(_normalize(row))
        return rows
    return []


def _normalize(row: dict) -> dict[str, Any]:
    # flexible column names
    def g(*keys: str) -> str:
        for k in keys:
            for rk, rv in row.items():
                if rk and rk.lower().strip() == k.lower() and rv:
                    return str(rv).strip()
        return ""

    return {
        "company": g("company", "公司", "企业名称", "单位名称"),
        "job_title": g("job_title", "job", "岗位", "职位", "岗位名称"),
        "contact_email": g("email", "contact_email", "邮箱", "E-mail", "邮件"),
        "source_url": g("url", "source_url", "链接", "官网"),
        "jd_summary": g("jd", "jd_summary", "简介", "岗位描述"),
        "source_type": "import",
    }
