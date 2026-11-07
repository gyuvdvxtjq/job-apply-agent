# -*- coding: utf-8 -*-
"""流水线评测：质检回退前后不合格率、平均耗时、LLM 调用与 token 成本。

对数据集前 N 条 JD 各跑一次完整图流水线（临时 store，不污染业务数据），
token/耗时统计来自 logs/llm_calls.jsonl 的本次增量（目的=jm_eval 前缀过滤）。

用法：
  python eval/scripts/run_pipeline.py --limit 10
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from eval_common import DATASET_DIR, ROOT, load_jsonl, md_table, save_result  # noqa: E402
from llm import estimate_cost  # noqa: E402
from store import JobLeads  # noqa: E402

LOG_PATH = ROOT / "logs" / "llm_calls.jsonl"


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)


def read_log_delta(path: Path, start_line: int) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= start_line and line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--jobs", default=None)
    args = ap.parse_args()

    jobs_path = Path(args.jobs) if args.jobs else DATASET_DIR / "jobs.jsonl"
    jobs = load_jsonl(jobs_path)[: args.limit]
    if not jobs:
        print("❌ 无评测样本")
        return

    from graph import build_pipeline, run_lead
    from langgraph.checkpoint.memory import MemorySaver
    from llm import LLMClient
    from rag import HybridRetriever, JDVectorStore
    from embeddings import EmbeddingClient

    # 检索器指向评测库（若已由 run_retrieval 建好则复用，否则现场建）
    db_dir = ROOT / "data" / "eval_chroma"
    store = JDVectorStore(db_dir, collection="eval_jobs")
    if store.count() == 0:
        from rag import ingest_jobs_file
        ingest_jobs_file(jobs_path, store, EmbeddingClient())
    retriever = HybridRetriever(store, EmbeddingClient(), None,
                                cfg={"vector_k": 20, "bm25_k": 20, "rrf_k": 60,
                                     "rerank": {"enabled": False}})
    llm_cfg = {"temperature": 0.2}
    llm = LLMClient(cfg=llm_cfg)

    log_start = count_lines(LOG_PATH)
    t_start = time.monotonic()

    with tempfile.TemporaryDirectory() as td:
        leads = JobLeads(Path(td) / "data")
        # demo profile 作为统一画像
        import yaml

        with open(ROOT / "examples" / "demo" / "profile.yaml", "r", encoding="utf-8") as f:
            profile = yaml.safe_load(f) or {}

        graph = build_pipeline({"graph": {"max_retries": 2, "min_match_score": 0.5,
                                          "retrieve_top_k": 5}},
                               llm, retriever, leads,
                               checkpointer=MemorySaver())
        results = []
        for job in jobs:
            lead_id = leads.add(
                company=job.get("company") or "",
                job_title=job.get("job_title") or "",
                contact_email=f"eval-{job['id']}@example.com",
                jd_summary=(job.get("jd_text") or "")[:2000],
                source_url=job.get("source_url") or "",
            )
            t0 = time.monotonic()
            values = run_lead(graph, leads, lead_id, profile)
            wall_ms = (time.monotonic() - t0) * 1000
            results.append({
                "job_id": job["id"],
                "outcome": values.get("outcome"),
                "qa_rounds": values.get("retry_count"),
                "first_pass": (values.get("retry_count") or 0) == 1 and values.get("qa_passed"),
                "final_pass": bool(values.get("qa_passed")),
                "wall_ms": wall_ms,
            })

    records = read_log_delta(LOG_PATH, log_start)
    total_tokens = sum(r.get("prompt_tokens", 0) + r.get("completion_tokens", 0) for r in records)
    prompt_tokens = sum(r.get("prompt_tokens", 0) for r in records)
    completion_tokens = sum(r.get("completion_tokens", 0) for r in records)
    n_calls = len(records)
    cost = estimate_cost(
        type("U", (), {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                       "total_tokens": total_tokens})(),
        llm.price_per_mtok,
    )
    wall_total_s = time.monotonic() - t_start

    n = len(results)
    first_pass = sum(1 for r in results if r["first_pass"])
    rewritten = sum(1 for r in results if (r["qa_rounds"] or 0) > 1)
    still_bad = sum(1 for r in results if not r["final_pass"] and r["outcome"] == "awaiting_approval")
    low_match = sum(1 for r in results if r["outcome"] == "low_match")

    title = "## 流水线评测：质检回退 / 耗时 / token 成本\n"
    meta = (
        f"\n- 样本: {n} 条 JD（数据集前 {n} 条） | 画像: examples/demo/profile.yaml | 模型: {llm.model}"
        f"\n- 生成时间: {datetime.now().isoformat(timespec='seconds')}"
        f"\n- token 成本按 config.llm.price_per_mtok 计算，价格表为 0 时成本显示 0（token 数为准）\n"
    )
    table = md_table(
        ["指标", "数值"],
        [
            ["首稿即通过质检", f"{first_pass}/{n}（{first_pass / n:.0%}）"],
            ["经历质检回退重写", f"{rewritten}/{n}（{rewritten / n:.0%}）"],
            ["重试用尽仍不合格（到人工闸门）", f"{still_bad}/{n}（{still_bad / n:.0%}）"],
            ["匹配分低被跳过", f"{low_match}/{n}（{low_match / n:.0%}）"],
            ["平均每条耗时", f"{wall_total_s * 1000 / n:.0f} ms"],
            ["LLM 调用总次数", str(n_calls)],
            ["平均每次调用 token", f"{total_tokens / max(1, n_calls):.0f}"],
            ["token 总量（prompt/completion）", f"{prompt_tokens} / {completion_tokens}"],
            ["估算成本（元，按价格表）", f"{cost:.4f}"],
        ],
    )
    detail = md_table(
        ["job_id", "结局", "质检轮数", "首稿通过", "终态通过", "耗时(ms)"],
        [[r["job_id"], r["outcome"], r["qa_rounds"], r["first_pass"], r["final_pass"],
          f"{r['wall_ms']:.0f}"] for r in results],
    )
    save_result("pipeline.md", title + meta + "\n" + table + "\n\n### 逐条明细\n\n" + detail + "\n")


if __name__ == "__main__":
    main()
