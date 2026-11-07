# -*- coding: utf-8 -*-
"""抽取评测：结构化抽取字段准确率（vs 人工金标准）+ 抽取失败率。

用法：
  python eval/scripts/run_extract.py
  python eval/scripts/run_extract.py --demo
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_common import DATASET_DIR, ROOT, jobs_map, load_jsonl, md_table, norm_list, norm_scalar, save_result  # noqa: E402
from extract_jd import extract_jd_info  # noqa: E402
from llm import LLMClient  # noqa: E402

FIELDS = ["company", "job_title", "cities", "education_requirement", "tech_stack", "deadline", "apply_method"]
LIST_FIELDS = {"cities", "tech_stack"}


def field_correct(field: str, pred: dict, gold: dict) -> bool | None:
    """单字段对比；金标准为 null 表示该字段无法判定 → None（跳过）。"""
    if field not in gold or gold[field] is None:
        return None
    pv = (pred or {}).get(field)
    if field in LIST_FIELDS:
        return norm_list(pv) == norm_list(gold[field])
    return norm_scalar(pv) == norm_scalar(gold[field])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    if args.demo:
        base = ROOT / "examples" / "demo" / "eval"
        labels = load_jsonl(base / "extract_labels.jsonl")
        jobs = jobs_map(base / "jobs.jsonl")
    else:
        labels = load_jsonl(DATASET_DIR / "extract_labels.jsonl")
        jobs = jobs_map()
    if not labels:
        print("❌ 抽取标注为空。先完成标注（模板见 eval/README.md），或 --demo 用示例标注。")
        return

    llm = LLMClient(cfg={"temperature": 0.0})
    stats = {f: {"hit": 0, "total": 0} for f in FIELDS}
    n_ok = n_fail = 0
    attempt_total = 0
    detail_rows = []

    for lb in labels:
        job = jobs.get(lb["job_id"])
        if not job:
            continue
        info, s = extract_jd_info(job.get("jd_text") or "", llm)
        attempt_total += s["attempts"]
        if info is None:
            n_fail += 1
            detail_rows.append([lb["job_id"], "❌ 抽取失败", "", s["attempts"]])
            continue
        n_ok += 1
        pred = info.model_dump()
        flags = []
        for f in FIELDS:
            correct = field_correct(f, pred, lb)
            if correct is not None:
                stats[f]["total"] += 1
                if correct:
                    stats[f]["hit"] += 1
                else:
                    flags.append(f)
        detail_rows.append([lb["job_id"], "✅", "、".join(flags) or "全对", s["attempts"]])

    total = n_ok + n_fail
    rows = []
    for f in FIELDS:
        t = stats[f]["total"]
        acc = stats[f]["hit"] / t if t else None
        rows.append([f, t, stats[f]["hit"], "—" if acc is None else f"{acc:.1%}"])
    rows.append(["（整体）", total, n_ok, f"成功率 {n_ok / total:.1%}" if total else "—"])

    title = "## 结构化抽取评测：字段准确率\n"
    meta = (
        f"\n- 样本: {total} | 平均尝试次数: {attempt_total / max(1, total):.2f}"
        f" | 抽取失败率: {n_fail / max(1, total):.1%}"
        f"\n- 模型: {llm.model} | 列表字段按集合精确匹配，标量按规范化后全等"
        f"\n- 生成时间: {datetime.now().isoformat(timespec='seconds')}"
        + ("\n- ⚠️ 示例标注（demo），仅演示脚本流程，非正式评测\n" if args.demo else "\n")
    )
    table = md_table(["字段", "可判定样本", "正确", "准确率"], rows)
    detail = md_table(["job_id", "结果", "错误字段", "尝试次数"], detail_rows)
    save_result("extract.md", title + meta + "\n" + table + "\n\n### 逐条明细\n\n" + detail + "\n")


if __name__ == "__main__":
    main()
