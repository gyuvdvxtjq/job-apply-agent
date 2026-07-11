# Task 01 — Plan

你是求职搜索规划 Agent。不要发送邮件。

## 输入

- `profile.yaml`（合并 config.user_overrides）
- `profiles.json` 中的档位 knobs（quick/standard/deep）
- `sources.json` 层定义
- `config.yaml` 的 sources.university_career / imports

## 动作

1. 阅读 profile：directions、cities、exclude、skills、highlights 是否够用；不够则先提示用户补全，不要编造 highlights。
2. 运行：`python tools/cli.py plan --run-profile {档位}`
3. 检查 `runs/plan.json`：
   - search_queries 是否覆盖「方向×城市」与「小公司发现」类
   - university_portals / import_paths 是否反映用户配置
   - auto_send 必须为 false
4. 向用户用简短列表展示：档位、目标线索数、前 8 条 query、启用层。

## 输出

- 确认 plan 路径
- 若用户要改城市/方向：指导改 profile 或 user_overrides 后重跑 plan
- 不要开始采集，除非主 Agent 进入 Task 02

## 禁止

- 写死任何学校/个人姓名到 plan 以外的代码
- 加入 BOSS/猎聘等 blocked 域 query 作为主策略
