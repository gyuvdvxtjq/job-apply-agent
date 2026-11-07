## 结构化抽取评测：字段准确率

- 样本: 8 | 平均尝试次数: 1.00 | 抽取失败率: 0.0%
- 模型: deepseek-ai/DeepSeek-V4-Flash | 列表字段按集合精确匹配，标量按规范化后全等
- 生成时间: 2026-11-07T14:50:31
- ⚠️ 示例标注（demo），仅演示脚本流程，非正式评测

| 字段 | 可判定样本 | 正确 | 准确率 |
|---|---|---|---|
| company | 8 | 8 | 100.0% |
| job_title | 8 | 8 | 100.0% |
| cities | 8 | 6 | 75.0% |
| education_requirement | 8 | 6 | 75.0% |
| tech_stack | 8 | 5 | 62.5% |
| deadline | 8 | 8 | 100.0% |
| apply_method | 8 | 7 | 87.5% |
| （整体） | 8 | 8 | 成功率 100.0% |

### 逐条明细

| job_id | 结果 | 错误字段 | 尝试次数 |
|---|---|---|---|
| demo-001 | ✅ | tech_stack | 1 |
| demo-002 | ✅ | education_requirement | 1 |
| demo-003 | ✅ | cities | 1 |
| demo-004 | ✅ | 全对 | 1 |
| demo-005 | ✅ | cities、education_requirement、tech_stack、apply_method | 1 |
| demo-006 | ✅ | 全对 | 1 |
| demo-007 | ✅ | 全对 | 1 |
| demo-008 | ✅ | tech_stack | 1 |
