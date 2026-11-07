# -*- coding: utf-8 -*-
"""匹配评测：LLM 匹配评分 vs 人工标注，计算准确率 / 精确率 / 召回率 / F1。

用法：
  python eval/scripts/run_match.py            # eval/dataset/match_labels.jsonl
  python eval/scripts/run_match.py --demo     # 示例标注
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_common import DATASET_DIR, ROOT, jobs_map, load_jsonl, md_table, save_result  # noqa: E402
from llm import LLMClient  # noqa: E402
from match import match_score  # noqa: E402
from match_llm import match_lead_with_llm  # noqa: E402

THRESHOLD = 0.5


def load_profile(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    if args.demo:
        base = ROOT / "examples" / "demo" / "eval"
        labels = load_jsonl(base / "match_labels.jsonl")
        jobs = jobs_map(base / "jobs.jsonl")
    else:
        labels = load_jsonl(DATASET_DIR / "match_labels.jsonl")
        jobs = jobs_map()
    labels = [x for x in labels if x.get("label") in (0, 1)]
    if not labels:
        print("❌ 匹配标注为空。先完成标注（模板见 eval/README.md），或 --demo 用示例标注。")
        return

    profile = load_profile(ROOT / "examples" / "demo" / "profile.yaml")
    llm = LLMClient(cfg={"temperature": 0.1})

    rows, detail_rows = [], []
    tp = fp = tn = fn = 0
    failed = 0
    for lb in labels:
        job = jobs.get(lb["job_id"])
        if not job:
            continue
        jd_text = f"{job.get('job_title') or ''}\n{job.get('jd_text') or ''}"
        lexical = match_score(profile, jd_text)["score"]
        verdict, stats = match_lead_with_llm(profile, jd_text, llm, lexical_score=lexical)
        if verdict is None:
            failed += 1
            pred, score = -1, None
        else:
            score = round(verdict.score, 3)
            pred = 1 if score >= THRESHOLD else 0
        truth = lb["label"]
        if pred == -1:
            detail_rows.append([lb["job_id"], truth, "抽取失败", "", ""])
        else:
            if pred == 1 and truth == 1:
                tp += 1
            elif pred == 1 and truth == 0:
                fp += 1
            elif pred == 0 and truth == 0:
                tn += 1
            else:
                fn += 1
            detail_rows.append([lb["job_id"], truth, pred, score,
                                (verdict.reasons or [""])[0][:40]])

    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    title = "## 匹配评测：LLM 匹配分 vs 人工标注\n"
    meta = (
        f"\n- 阈值: score ≥ {THRESHOLD} 判为匹配 | 样本: {total}（抽取失败 {failed} 不计入）"
        f"\n- 画像: examples/demo/profile.yaml | 模型: {llm.model}"
        f"\n- 生成时间: {datetime.now().isoformat(timespec='seconds')}"
        + ("\n- ⚠️ 示例标注（demo），仅演示脚本流程，非正式评测\n" if args.demo else "\n")
    )
    table = md_table(
        ["准确率", "精确率", "召回率", "F1", "TP", "FP", "TN", "FN"],
        [[f"{accuracy:.3f}", f"{precision:.3f}", f"{recall:.3f}", f"{f1:.3f}", tp, fp, tn, fn]],
    )
    detail = md_table(["job_id", "人工", "预测", "score", "首条理由"], detail_rows)
    save_result("match.md", title + meta + "\n" + table + "\n\n### 逐条明细\n\n" + detail + "\n")


if __name__ == "__main__":
    main()
