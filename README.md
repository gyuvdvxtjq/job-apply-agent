# job-apply-agent

简历画像驱动的求职线索准备工具：**Claude Code Skill + Python CLI**。  
多层公开信息源采集 → 匹配 JD → 生成求职信 → **默认只到 `ready`，审查后再发送**。

架构学习自 [hoolulu/deep-research](https://github.com/hoolulu/deep-research) 的分阶段多 Agent 流程（Plan → Collect → Draft → QA），业务改为求职而非研报。

## 功能

- **不写死个人**：学校 / 城市 / 方向 / 项目证据来自 `profile.yaml`
- **多源采集**：宿主搜索（L0）+ 就业网/careers（L1）+ 可选 SearXNG（L2）+ `sources.json`（L3）+ 小公司发现（L4）+ 本地双选会 CSV
- **屏蔽登录墙站**：默认不把 BOSS/猎聘等当数据源
- **SMTP 发送可选**：`send --confirm` 才发，附带简历 PDF
- **可发布**：示例与密钥分离，`.gitignore` 已忽略隐私文件

## 快速开始

```bash
git clone https://github.com/<you>/job-apply-agent.git
cd job-apply-agent
pip install -r requirements.txt
cp config.example.yaml config.yaml
# 编辑 config.yaml：smtp、resume.path、user_overrides.cities 等
# 推荐: 环境变量 SMTP_PASSWORD=你的授权码
```

### 1. 解析简历 → 画像

```bash
python tools/cli.py parse-resume --pdf ./你的简历.pdf
# 编辑 profile.yaml：补全 cities、directions、highlights（证据）
```

### 2. 规划

```bash
python tools/cli.py plan --run-profile standard
# 查看 runs/plan.json
```

### 3. 采集（CLI 部分 + Claude Skill 做 L0 搜索）

```bash
# 本地双选会名单
# 在 config.yaml sources.imports.paths 填 CSV 路径，或:
python tools/cli.py collect --url "https://某公司/careers"

# 手动添加
python tools/cli.py add --company "公司" --job "岗位" --email "hr@x.com" \
  --jd "摘要" --source "https://..."
```

在 **Claude Code** 中加载本仓库 `SKILL.md`，按四阶段执行完整多源搜索与写信。

### 4. 求职信与验收

```bash
python tools/cli.py draft    # 骨架；Skill 可写得更好后 set-body
python tools/cli.py qa
python tools/cli.py list --status ready
```

### 5. 审查后发送（可选）

```bash
python tools/cli.py send --id 1 --confirm
# 或
python tools/cli.py send-all --confirm
```

## 目录

```
SKILL.md              # Claude 主调度契约
prompts/              # 01_plan … 04_qa
profiles.json         # quick / standard / deep
sources.json          # 公开源注册 + 屏蔽域
config.example.yaml
tools/                # CLI 与库
  cli.py
  parse_resume.py
  plan.py / collect.py / draft.py / qa.py
  store.py / mailer.py / match.py / extract.py
  registry.py
  adapters/
examples/demo/        # 脱敏示例
```

## 配置要点

| 项 | 说明 |
|----|------|
| `smtp.*` / `SMTP_PASSWORD` | 发信；勿提交真密码 |
| `resume.path` | PDF 路径 |
| `profile_path` | 默认 `./profile.yaml` |
| `user_overrides.cities` | 覆盖简历推断的城市 |
| `sources.university_career.portals` | **你的**学校就业网 URL 列表 |
| `sources.imports.paths` | 双选会/园区 CSV |
| `pipeline.auto_send` | 必须为 false |

## 设计说明

### 简历要理解多深？

结构化到可检索：**技能、项目证据（highlights）、教育、约束**。  
不做性格测评。求职信只能引用 highlights 里的事实。

### 别人学校/地区不同？

只改 `profile.yaml` + `config.yaml` 的 portals/cities/imports，代码不变。

### 与 deep-research 的映射

| deep-research | job-apply-agent |
|---------------|-----------------|
| outline | plan.json |
| data-pool | job_leads.json |
| 并行写章节 | 并行写求职信 |
| QA 装配报告 | qa + export + 用户审查 |
| 源五层 | L0–L4 求职域源 |

## 合规

- 仅使用**公开**页面与公开邮箱
- 控制发送频率，避免骚扰
- 投递后果由使用者自负
- 本工具不绕过网站登录/验证码

## License

MIT
