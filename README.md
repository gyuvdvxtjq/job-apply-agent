# job-apply-agent

一个开源的 AI 求职助手。你只需要准备一份简历 PDF 和一个 SMTP 邮箱，它就能自动完成：**搜索岗位 → 匹配 JD → 生成针对性求职信 → 等你审查后发送**。

整个流程由 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 驱动——Claude 作为 AI Agent 调度 Python CLI 工具链，你不需要手动执行任何命令。

> **安全承诺**：默认不会自动发送任何邮件。所有线索停在 `ready` 状态，你审查后才 `send --confirm`。

---

## 一键开始（粘贴给 Claude Code）

安装好依赖后，把下面这段话粘贴到 Claude Code 里，AI 会自动帮你走完全流程：

```
读取本项目的 SKILL.md，按照里面的调度流程执行求职投递任务。

前置检查：
1. 如果没有 config.yaml，帮我从 config.example.yaml 复制一份，然后提示我填写 SMTP 和简历路径
2. 如果没有 profile.yaml，运行 parse-resume 解析我的简历 PDF，然后让我确认/补充城市和求职方向

确认配置就绪后，依次执行：
- Plan：生成搜索计划（standard 档）
- Collect：按计划多渠道采集岗位线索和邮箱
- Draft：为每条线索生成针对性求职信
- QA：过滤低质量线索

最后用 list --status ready 展示所有待发送线索给我审查。不要自动发送。
```

> 你也可以只粘贴其中一步，比如 `帮我采集这个页面的岗位：https://某公司.com/careers`。

---

## 它能做什么

```
你的简历 PDF ──> 解析为 profile.yaml
                        │
              ┌─────────┴──────────┐
              │      Plan 阶段      │  生成搜索计划
              └─────────┬──────────┘
                        │
              ┌─────────┴──────────┐
              │    Collect 阶段     │  多渠道搜集岗位 + 邮箱
              └─────────┬──────────┘
                        │
              ┌─────────┴──────────┐
              │     Draft 阶段      │  按 JD 生成针对性求职信
              └─────────┬──────────┘
                        │
              ┌─────────┴──────────┐
              │      QA 阶段       │  过滤低质线索
              └─────────┬──────────┘
                        │
                  你审查 → send
```

**你只需准备两样东西：**
1. 一份 PDF 简历
2. 一个能发邮件的 SMTP 账号（QQ邮箱、Outlook 等均可）

## 快速开始（手动 CLI）

> 不用 Claude Code？也可以手动一步步操作。

### 安装

```bash
git clone https://github.com/gyuvdvxtjq/job-apply-agent.git
cd job-apply-agent
pip install -r requirements.txt
```

### 配置（3 分钟）

```bash
cp config.example.yaml config.yaml
```

打开 `config.yaml`，填写：

| 必填项 | 说明 |
|--------|------|
| `smtp.server` | 邮箱 SMTP 服务器，如 `smtp.qq.com` |
| `smtp.email` | 你的发件邮箱 |
| `smtp.password` | 授权码（推荐用环境变量 `SMTP_PASSWORD`，不写进文件） |
| `resume.path` | 简历 PDF 的路径 |

可选项：
- `user_overrides.cities` — 期望城市（覆盖简历中推断的）
- `sources.imports.paths` — 双选会/校招 CSV 文件路径

### 使用

**第一步：解析简历**

```bash
python tools/cli.py parse-resume --pdf ./你的简历.pdf
```

会生成 `profile.yaml`——打开它，补全城市、方向、项目经历等。

**第二步：生成搜索计划**

```bash
python tools/cli.py plan --run-profile standard
```

支持 `quick`（快速 10 条）/ `standard`（标准 25 条）/ `deep`（深度 40 条）三档。

**第三步：采集岗位**

```bash
# 从公司招聘页采集
python tools/cli.py collect --url "https://某公司.com/careers"

# 手动添加
python tools/cli.py add --company "某科技" --job "数据分析实习" \
  --email "hr@example.com" --jd "需要Python" --source "https://..."
```

**第四步：生成求职信**

```bash
python tools/cli.py draft
```

**第五步：质量检查**

```bash
python tools/cli.py qa
python tools/cli.py list --status ready
```

**第六步：审查后发送**

```bash
# 发单条
python tools/cli.py send --id 1 --confirm

# 或全部发送
python tools/cli.py send-all --confirm
```

> 没有 `--confirm` 不会发送任何邮件。

## CLI 命令速查

| 命令 | 作用 |
|------|------|
| `parse-resume --pdf X` | PDF 简历 → profile.yaml |
| `plan --run-profile X` | 生成搜索计划 |
| `collect --url X` | 从 URL 采集岗位和邮箱 |
| `add --company X --job X --email X` | 手动添加线索 |
| `draft` | 为 pending 线索生成求职信 |
| `set-body --id N --body "..."` | 手动替换某条求职信正文 |
| `qa` | 过滤低质量线索 |
| `list --status ready` | 查看待发送线索 |
| `status` | 总览统计 |
| `send --id N --confirm` | 发送单条 |
| `send-all --confirm` | 发送所有 ready |
| `export` | 导出 Markdown 报告 |
| `health` | 检查数据源可用性 |

## 数据源

工具从公开渠道采集，**不会登录任何网站**，不绕过验证码。

| 层级 | 来源 | 说明 |
|------|------|------|
| L0 | Web 搜索 | Claude 或搜索引擎按关键词搜 |
| L1 | 学校就业网 / 公司 careers 页 | 你在 config 中配置的 URL |
| L2 | SearXNG（可选） | 自建元搜索实例 |
| L3 | 求职社区 | 牛客、应届生求职网、V2EX 等 |
| L4 | 发现式搜索 | 线索不足时扩大搜索范围 |

默认屏蔽需要登录的站点：BOSS 直聘、猎聘、LinkedIn、脉脉等。

## 项目结构

```
config.example.yaml   ← 配置模板（复制为 config.yaml 使用）
profile.yaml          ← 你的简历画像（gitignore，不会提交）
sources.json          ← 数据源注册表
profiles.json         ← quick/standard/deep 三档参数

SKILL.md              ← Claude Code Skill 调度入口
prompts/              ← 四阶段 Prompt（01_plan ~ 04_qa）

tools/
├── cli.py            ← CLI 入口（12 个子命令）
├── parse_resume.py   ← PDF 解析
├── plan.py           ← 搜索规划
├── collect.py        ← 岗位采集
├── draft.py          ← 求职信生成
├── qa.py             ← 质量检查
├── store.py          ← 线索存储（JSON）
├── mailer.py         ← SMTP 发送
├── match.py          ← JD-简历匹配评分
├── extract.py        ← 邮箱提取
├── registry.py       ← 数据源管理
├── config_loader.py  ← 配置加载
├── profile_io.py     ← Profile 读写
├── common.py         ← 通用工具函数
└── adapters/
    ├── fetch.py      ← HTTP 抓取
    └── imports.py    ← CSV/JSON 导入

examples/demo/        ← 脱敏示例数据
data/                 ← 运行时数据（gitignore）
runs/                 ← 运行计划（gitignore）
```

## 安全说明

- `config.yaml`、`profile.yaml`、`.env` 已在 `.gitignore` 中，**不会被提交**
- SMTP 密码推荐通过环境变量 `SMTP_PASSWORD` 传入
- `pipeline.auto_send` 强制为 `false`，代码中有硬检查

## 合规

- 仅使用公开页面与公开邮箱，不爬取登录墙后的内容
- 发送频率可控（默认间隔 5 秒），避免骚扰
- 投递后果由使用者自负
- 本工具不绕过任何网站的登录或验证码机制

## License

MIT
