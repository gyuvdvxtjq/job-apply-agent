# -*- coding: utf-8 -*-
"""生成三份人工标注骨架文件（不预填任何判断，只预填客观上下文）。

输出到 eval/dataset/ 下：
- retrieval_queries.jsonl  检索问题 ↔ 相关岗位 ID（评测者自己想 query 并标注相关岗位）
- match_labels.jsonl       简历画像 × 岗位 → 匹配 1 / 不匹配 0
- extract_labels.jsonl     JD 抽取金标准（不确定的字段填 null，脚本跳过该字段）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_common import DATASET_DIR, load_jsonl  # noqa: E402

TEMPLATE_HEADER = {
    "retrieval_queries.jsonl": {
        "_说明": "每行一个自然语言检索问题。relevant_job_ids 填你判断与问题相关的岗位 id 列表（看 dataset/jobs.jsonl）。建议 8~15 个问题，覆盖城市/技能/方向/学历等维度。",
    },
    "match_labels.jsonl": {
        "_说明": "对指定简历画像（默认 examples/demo/profile.yaml）判断每个岗位是否值得投递：label=1 匹配、0 不匹配。建议全量标注。可在 profile_path 换成你自己的真实画像后重标一组。",
    },
    "extract_labels.jsonl": {
        "_说明": "通读 jd_text 后填金标准。公司/岗位无法从原文确定就填 null，评测脚本跳过该字段。cities/tech_stack 是列表。",
    },
}


def main() -> None:
    jobs = load_jsonl(DATASET_DIR / "jobs.jsonl")
    for name, header in TEMPLATE_HEADER.items():
        out = DATASET_DIR / f"{name}.skeleton"
        with open(out, "w", encoding="utf-8") as f:
            f.write(json.dumps(header, ensure_ascii=False) + "\n")
            if name == "retrieval_queries.jsonl":
                for i in range(1, 11):
                    f.write(json.dumps({
                        "query_id": f"q{i}", "query": "",
                        "relevant_job_ids": [],
                    }, ensure_ascii=False) + "\n")
            elif name == "match_labels.jsonl":
                for j in jobs:
                    f.write(json.dumps({
                        "job_id": j["id"], "profile": "examples/demo/profile.yaml",
                        "label": None,
                        "job_title": j.get("job_title") or "",
                        "company": j.get("company") or "",
                    }, ensure_ascii=False) + "\n")
            else:
                for j in jobs:
                    f.write(json.dumps({
                        "job_id": j["id"],
                        "company": None, "job_title": None, "cities": None,
                        "education_requirement": None, "tech_stack": None,
                        "deadline": None, "apply_method": None,
                        "_jd_preview": (j.get("jd_text") or "")[:120],
                    }, ensure_ascii=False) + "\n")
        print(f"✅ 骨架已生成: {out}（复制去掉 .skeleton 后缀开始标注）")


if __name__ == "__main__":
    main()
