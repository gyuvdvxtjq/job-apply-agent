# JobMatch-Agent 🎯

**校招岗位匹配与求职信生成 Agent** —— 简历与岗位的语义匹配、辅助投递决策。

> 定位是**匹配与辅助决策**，不是自动海投工具：邮件发送保留但弱化，
> 必须人工确认（`send --confirm`），审批闸门不暴露给模型作为工具。

由旧项目 [job-apply-agent](https://github.com/gyuvdvxtjq/job-apply-agent)（Claude Code 宿主 + 规则 CLI）改造而来，保留原 CLI 可用，新能力以新模块加入。设计决策与面试追问点见 [docs/DESIGN.md](docs/DESIGN.md)。

---

## 核心能力

| 能力 | 实现 | 入口 |
|---|---|---|
| 自研 Agent 编排 | LangGraph 状态图：规划→检索→抽取→匹配评分→生成→质检，质检不过回退重写（上限可配），SQLite checkpointer 持久化、中断恢复，人工审批 interrupt 闸门 | `tools/cli.py graph run/resume/status` |
| 岗位 RAG | 按「职责/要求/其他」语义分块 → bge-m3 向量入 Chroma → BM25(jieba) 混合召回 + RRF 融合 → bge-reranker-v2-m3 重排（可配置关） | `tools/cli.py rag-ingest / search` |
| 结构化抽取 | 七字段（公司/岗位/城市/学历/技术栈/截止/投递方式），Pydantic 校验，校验错误回喂重试，失败率入日志 | `tools/cli.py extract-jd` |
| 评测 | 43 条真实公开 JD 数据集 + 人工标注工具 + 四个脚本（Recall@5/MRR 三组对比、匹配 P/R/F1、字段准确率、质检回退率/耗时/token 成本） | `eval/`（见 eval/README.md） |
| 服务化 | FastAPI（search / match / **SSE 流式生成**）+ Streamlit 演示页；每次模型调用记录 token/耗时 | `service/` |
| 安全 | 发送需显式 `--confirm` + 每日限频强制执行；审批是 LangGraph interrupt 而非模型工具；Web 层无任何写端点；密钥只进 `.env` | — |

## 架构

```
                ┌────────────────────────────────────────────┐
   简历 PDF ──▶ │ parse_resume → profile.yaml（技能/方向/证据） │
                └────────────────────────────────────────────┘
                                   │
   公开 JD ──▶ collect ──▶ rag-ingest ──▶ Chroma ◀── jieba BM25
                                   │              │
                ┌──────────────────▼──────────────▼─────────┐
                │        LangGraph 流水线（tools/graph.py）     │
                │  plan → retrieve → extract → match(LLM)     │
                │        ↓ (低分→跳过)                          │
                │       draft ──▶ qa ──┬─ 不过→回退 draft(≤N次) │
                │                      └─ 通过→ finalize       │
                │             interrupt ▼                     │
                │      人工审批（CLI graph resume）             │
                └──────────────────┬─────────────────────────┘
                                   │ ready（仍需 send --confirm）
                ┌──────────────────▼─────────────────────────┐
                │  FastAPI: /search /match /generate(SSE)     │
                │  Streamlit 演示页（只读看板）                  │
                └────────────────────────────────────────────┘
```

默认模型：DeepSeek（OpenAI 兼容协议，自研 httpx 客户端，不引 SDK）；
embedding/rerank：硅基流动 `bge-m3` / `bge-reranker-v2-m3`。全部走 `.env` 配置，可一键切换供应商。

## 快速开始

```bash
# Python 3.10+（注意：用官方/uv 管理的干净解释器，Anaconda 父解释器
# 会导致 chromadb 的 Rust 扩展段错误，见 DESIGN.md §3.4）
python -m venv .venv && pip install -r requirements.txt

cp .env.example .env        # 填 LLM_API_KEY / SILICONFLOW_API_KEY
cp config.example.yaml config.yaml

# 1) 岗位入库 + 自然语言检索
python tools/cli.py rag-ingest --file examples/demo/jobs.jsonl --reset
python tools/cli.py search "深圳有哪些要求 RAG 经验的校招岗"

# 2) 加一条线索，跑完整 Agent 流水线（到人工审批闸门停下）
python tools/cli.py add --company "某公司" --job "LLM应用实习生" \
    --email hr@example.com --source https://... --jd "岗位职责：..."
python tools/cli.py graph run --lead 1
python tools/cli.py graph resume --lead 1 --approve    # 人工决定

# 3) 审查后发送（仍需显式确认，受每日限频约束）
python tools/cli.py send --id 1 --confirm

# 4) 服务化演示
python -m uvicorn service.app:app --port 8000          # 终端 1
streamlit run service/ui.py                            # 终端 2
```

## 评测（数字全部脚本实跑）

**流水线评测**（10 条真实公开 JD，`python eval/scripts/run_pipeline.py --limit 10`）：

| 指标 | 数值 |
|---|---|
| 经历质检回退重写 | 1/10（10%） |
| 匹配分低被正确跳过 | 9/10（90%，学生画像 vs 社招岗） |
| LLM 调用总次数 / token 总量 | 36 次 / 47,058（prompt 24,226 + completion 22,832） |
| 平均每条端到端耗时 | ~61 s |

**检索三组对比、匹配准确率、抽取字段准确率**依赖人工标注（绝不编造）：
标注工具与指南见 **[eval/README.md](eval/README.md)**（预计 30~60 分钟），
完成后运行 `eval/scripts/run_retrieval.py` 等脚本即可生成结果表到 `eval/results/`。
`--demo` 模式用内置示例标注（明确标记为演示数据，不代表系统效果）可先验证脚本流程。

## 与旧版（Claude Code 宿主模式）的关系

`SKILL.md + prompts/` 宿主模式**继续可用**：Claude 读 SKILL.md 调度 CLI 完成
plan → collect → draft → qa 的多源采集与准备。LangGraph 流水线是平行的第二条路径，
两者共享 store / adapters / RAG 等底层模块。

## 安全与合规

- 发送三重闸门：QA 规则检查 → 人工审批 interrupt → `send --confirm`；每日限频强制执行
- 模型没有任何节点/工具能触达发送或审批
- 采集只走公开页面，屏蔽登录墙站点（BOSS/猎聘等，见 sources.json）
- 求职信证据只能来自简历画像；质检明确检查「编造证据」
- 密钥只进 `.env`（已 gitignore），token/耗时全部记账到 `logs/llm_calls.jsonl`

## License

MIT
