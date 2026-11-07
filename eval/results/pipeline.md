## 流水线评测：质检回退 / 耗时 / token 成本

- 样本: 10 条 JD（数据集前 10 条） | 画像: examples/demo/profile.yaml | 模型: deepseek-ai/DeepSeek-V4-Flash
- 生成时间: 2026-11-07T15:03:37
- token 成本按 config.llm.price_per_mtok 计算，价格表为 0 时成本显示 0（token 数为准）

| 指标 | 数值 |
|---|---|
| 首稿即通过质检 | 0/10（0%） |
| 经历质检回退重写 | 1/10（10%） |
| 重试用尽仍不合格（到人工闸门） | 1/10（10%） |
| 匹配分低被跳过 | 9/10（90%） |
| 平均每条耗时 | 60974 ms |
| LLM 调用总次数 | 36 |
| 平均每次调用 token | 1307 |
| token 总量（prompt/completion） | 24226 / 22832 |
| 估算成本（元，按价格表） | 0.0000 |

### 逐条明细

| job_id | 结局 | 质检轮数 | 首稿通过 | 终态通过 | 耗时(ms) |
|---|---|---|---|---|---|
| v2ex-1243876 | low_match | 0 | False | False | 40816 |
| v2ex-1250045 | low_match | 0 | False | False | 27836 |
| v2ex-1250192 | low_match | 0 | False | False | 194972 |
| v2ex-1250716 | low_match | 0 | False | False | 42846 |
| v2ex-1250726 | low_match | 0 | False | False | 14429 |
| v2ex-1250841 | low_match | 0 | False | False | 28184 |
| v2ex-1250883 | low_match | 0 | False | False | 38968 |
| v2ex-1250894 | low_match | 0 | False | False | 34784 |
| v2ex-1251159 | awaiting_approval | 3 | False | False | 139692 |
| v2ex-1252035 | low_match | 0 | False | False | 47188 |
