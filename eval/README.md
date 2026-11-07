# 评测（eval/）

所有评测数字由脚本实跑得出，**不手工编造**。

> ⚠️ **标注者声明**：本数据集的金标准标注由**项目作者本人**完成（非独立第三方）。
> 作者对系统实现有充分了解，标注虽按统一规则执行（见下），但与系统输出存在
> 潜在的相关性偏置，数字应视为**作者视角的自我评估**，而非独立人工评测的结论。
> 重新标注即可获得独立结果：`make_label_skeletons.py` 可随时生成空白骨架，
> 按「标注者须知」用第三方标注者重标后重跑脚本。

```
eval/
├── dataset/
│   ├── jobs.jsonl               # 岗位数据集（124 条真实公开 JD，来源 V2EX 酷工作，见 source_url）
│   ├── raw_v2ex/                # 原始采集（溯源用）
│   ├── retrieval_queries.jsonl  # 检索问题 ↔ 相关岗位 ID（12 条，人工标注）
│   ├── match_labels.jsonl       # 画像 × 岗位 → 匹配/不匹配（124 条，正样本 8）
│   └── extract_labels.jsonl     # 抽取金标准字段（124 条）
├── scripts/
│   ├── make_label_skeletons.py  # 生成标注骨架（预填客观上下文，不预填判断）
│   ├── run_retrieval.py         # 检索三组对比：纯向量 / 混合 / 混合+重排 → Recall@5 / MRR
│   ├── run_match.py             # 匹配：LLM 分数 vs 人工标注 → 准确率/P/R/F1
│   ├── run_extract.py           # 抽取：字段级准确率 + 失败率
│   └── run_pipeline.py          # 流水线：质检回退率 / 耗时 / token 成本
└── results/                     # 脚本输出的 Markdown 表（可贴进 README）
```

## 标注指南（人工，预计 30~60 分钟）

```bash
python eval/scripts/make_label_skeletons.py
# 生成 eval/dataset/*.jsonl.skeleton → 去掉 .skeleton 后缀开始标注
```

1. **retrieval_queries.jsonl**：自己写 8~15 个自然语言检索问题（覆盖城市/技能/方向/学历维度），
   通读 `jobs.jsonl` 后把与该问题相关的岗位 `id` 填进 `relevant_job_ids`（可多个，问题要有明确相关集）。
2. **match_labels.jsonl**：以 `examples/demo/profile.yaml`（或换成你自己的画像）的视角，
   逐条判断 `label`：1 = 值得投递，0 = 不值得。
3. **extract_labels.jsonl**：通读每条 `jd_text`，按**原文**填写七个字段；原文未提及填 `""`（或 `[]`），
   原文无法确定填 `null`（评测脚本跳过该字段）。

## 运行评测

```bash
python eval/scripts/run_retrieval.py        # 需要检索标注；耗 embedding API
python eval/scripts/run_match.py            # 需要匹配标注；耗 LLM API
python eval/scripts/run_extract.py          # 需要抽取标注；耗 LLM API
python eval/scripts/run_pipeline.py --limit 10   # 不需要标注；耗 LLM + embedding API
```

结果输出到 `eval/results/*.md`。

## 示例模式（验证脚本可跑，非正式评测）

`examples/demo/eval/` 内置 8 条示例 JD 与示例标注（**是脚本作者写的演示数据，
不是人工正式标注，其结果不代表系统真实效果**）。加 `--demo` 运行：

```bash
python eval/scripts/run_retrieval.py --demo
python eval/scripts/run_match.py --demo
python eval/scripts/run_extract.py --demo
```

正式评测数字以 `eval/dataset/` 人工标注跑出的结果为准。
