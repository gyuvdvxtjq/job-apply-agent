---
name: job-apply-agent
description: "求职投递助手 — 简历画像驱动、多层公开信息源采集、多阶段准备求职信；默认只生成 ready 供审查，不自动发送。Claude Code Skill + tools CLI。"
version: 0.1.0
---

# job-apply-agent Skill

架构对齐 [deep-research](https://github.com/hoolulu/deep-research) 的分阶段主 Agent 调度，但业务是**求职线索与求职信准备**，不是研报。

- **宿主**：Claude Code（默认用户也使用 Claude）
- **手脚**：`tools/` CLI（parse / plan / collect / draft / qa / send）
- **硬规则**：`auto_send=false`；发送必须用户审查后 `send --confirm`
- **禁止**：写死某个学校/城市/姓名/项目话术；登录墙招聘站（BOSS/猎聘等）

读取：`VERSION`、`profiles.json`、`sources.json`、`config.yaml`（或 example）、`profile.yaml`

---

## 0. 支付级质量标准

| # | 标准 | 说明 |
|---|------|------|
| 1 | 配置驱动 | 学校、城市、方向、排除名单只来自 profile/config |
| 2 | 证据可追溯 | 求职信项目句必须来自 profile.highlights |
| 3 | 来源可追溯 | 每条 lead 尽量有 source_url |
| 4 | 不编造 | 无证据宁可不写该段 |
| 5 | 默认不发送 | run 结束停在 ready |
| 6 | 屏蔽登录站 | sources.blocked_domains |
| 7 | UTF-8 | 中间 JSON/YAML 无 BOM |
| 8 | 容错 | 单源失败不阻断整流水线 |

---

## 1. 主 Agent 调度流程

```
Setup
  → 确认工作目录为本仓库根
  → 若无 config.yaml：提示复制 config.example.yaml（不要替用户提交密钥）
  → 若无 profile.yaml：运行 parse-resume，再请用户补全 cities/到岗/highlights
  → 读取 profile + config.user_overrides 合并

① Plan
  → python tools/cli.py plan --run-profile {quick|standard|deep}
  → 产出 runs/plan.json
  → 向用户展示查询样例与目标线索数，确认可改 cities/directions

② Collect（多层，尽量多源）
  → L0：按 plan.search_queries 用 WebSearch / tinyfish 等宿主搜索（并行多 query）
  → L1：plan.university_portals、用户给出的 careers URL
  → L2：若 config.searxng.enabled，查询元搜索
  → L3：sources.json 中 job_board/community 模板 URL → fetch 抽邮箱
  → L4：线索不足时用 company_discovery 类 query 拓宽
  → 对每个有价值 URL：python tools/cli.py collect --url URL  或 tools add
  → 本地 imports：双选会 CSV 等
  → 合并去重：同邮箱不重复；已 sent_log 跳过
  → 写出 runs/lead_pool_meta.json 进度

③ Draft（可按线索并行）
  → 优先用本 Skill + profile.highlights 写针对性求职信（优于纯骨架）
  → 骨架兜底：python tools/cli.py draft
  → 每封：引用 JD 要点 + 2~3 条真实 highlights + 到岗信息
  → set-body / draft 后状态 ready

④ QA
  → python tools/cli.py qa
  → list --status ready 给用户审查
  → 用户明确要求发送时才：send --id N --confirm 或 send-all --confirm
```

### 每阶段 prompt 文件

- `prompts/01_plan.md`
- `prompts/02_collect.md`
- `prompts/03_draft.md`
- `prompts/04_qa.md`

派发子 Agent 时把对应 prompt + 必要 JSON 路径粘贴进去。

---

## 2. CLI 速查

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml   # 编辑 SMTP/简历路径/城市
python tools/cli.py parse-resume --pdf ./resume.pdf
# 编辑 profile.yaml：cities、directions、highlights、exclude_companies

python tools/cli.py plan --run-profile standard
python tools/cli.py collect --url "https://example.com/careers"
# … Skill 执行 L0 搜索并 add 线索 …
python tools/cli.py draft
python tools/cli.py qa
python tools/cli.py list --status ready
python tools/cli.py send --id 1 --confirm    # 仅审查后
python tools/cli.py export
python tools/cli.py health
```

---

## 3. 数据源策略（尽可能多，但要真）

**发现公司（小厂）** 与 **解析公开联系方式** 两段式，不要只靠 SEO 搜岗位标题。

| 层 | 谁执行 | 源 |
|----|--------|-----|
| L0 | Skill | WebSearch/tinyfish 多 query |
| L1 | Skill+CLI | 用户配置就业网、已知 careers |
| L2 | CLI/Skill | SearXNG（可选） |
| L3 | CLI+Skill | sources.json 实习僧/应届生/牛客日程/V2EX/GitHub… |
| L4 | Skill | 园区/双选会/融资新闻 → 再找官网邮箱 |

屏蔽：`zhipin.com`、`liepin.com` 等（见 sources.json）。

---

## 4. 简历理解深度

结构化即可，不写人生咨询：

- identity / education / skills / directions
- **highlights**（可检索证据）— 写信只准用这里的事实
- constraints.cities / exclude_* / 到岗

规则解析：`tools/parse_resume.py`  
深化：你（Claude）根据 raw_text_excerpt 改写 profile.yaml

---

## 5. 与 deep-research 的对应

| deep-research | 本项目 |
|---------------|--------|
| outline.json | plan.json |
| data-pool | job_leads + lead_pool_meta |
| 并行章节 | 并行 draft 多条 lead |
| assemble+qa | qa + export report |
| 不自动「发表论文」 | 不自动 send |

---

## 6. 安全与发布

- 密钥仅 config.yaml / 环境变量，已被 gitignore
- 示例用 `examples/demo/`，无真实授权码
- 频率：send 间隔与每日上限见 config.pipeline
- 仅使用公开联系方式；用户对投递行为负责
