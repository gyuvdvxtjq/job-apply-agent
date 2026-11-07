# -*- coding: utf-8 -*-
"""评测公共工具：数据加载、chunk→job 聚合、Markdown 表输出。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sys
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
load_dotenv(ROOT / ".env", override=False)

EVAL_DIR = ROOT / "eval"
DATASET_DIR = EVAL_DIR / "dataset"
RESULTS_DIR = EVAL_DIR / "results"


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def jobs_map(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    path = path or (DATASET_DIR / "jobs.jsonl")
    return {j["id"]: j for j in load_jsonl(path)}


def chunks_to_job_ranking(hits: list[dict[str, Any]]) -> list[str]:
    """chunk 级命中聚合为 job 级排名（每 job 取其最高排名 chunk，保序去重）。"""
    seen: dict[str, None] = {}
    for h in hits:
        seen.setdefault(h.get("job_id") or "", None)
    return [j for j in seen if j]


def recall_at_k(ranked_jobs: list[str], relevant: set[str], k: int = 5) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked_jobs[:k]) & relevant) / len(relevant)


def mrr(ranked_jobs: list[str], relevant: set[str]) -> float:
    for i, j in enumerate(ranked_jobs, start=1):
        if j in relevant:
            return 1.0 / i
    return 0.0


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def save_result(name: str, content: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    p = RESULTS_DIR / name
    p.write_text(content, encoding="utf-8")
    print(f"✅ 结果已写入 {p}")
    return p


def norm_scalar(v: Any) -> str:
    return str(v or "").strip().lower()


def norm_list(v: Any) -> set[str]:
    return {norm_scalar(x) for x in (v or []) if norm_scalar(x)}
