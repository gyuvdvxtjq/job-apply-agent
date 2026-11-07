# DESIGN — JobMatch-Agent 设计决策记录

> 项目从「job-apply-agent（Claude Code 宿主 + 规则 CLI）」改造为
> 「JobMatch-Agent：校招岗位匹配与求职信生成 Agent」。
> 本文档记录每个关键设计决策的 why，按阶段追加；面试追问以本文为准。

## 0. 定位与边界

- 定位：简历与岗位的**语义匹配与辅助决策**，不是自动海投工具。
- 邮件发送保留但弱化：必须人工 `--confirm`，审批不作为工具暴露给任何模型。
- 原有 Claude Code 宿主模式（SKILL.md + prompts/）继续可用；新增的 LangGraph
  编排是平行的第二条路径，两者共享 store/adapters 等底层模块。

## 1. 阶段 0：工程基线

### 1.1 测试先行于改造

先建立 22 个全离线回归用例（store 状态机 / match / extract / CLI e2e），
再动任何核心逻辑。原因：改造涉及把规则式流程替换为 LLM 流程，必须有
「改造前行为快照」才能判断哪些行为变了、哪些必须保持。

### 1.2 每日发送限频（修复历史隐患）

`config.pipeline.max_emails_per_day` 原本只声明未执行。现由 `SentLog.count_today()`
+ `cli.daily_cap_status()` 在 `send` / `send-all` 前强制检查：超限拒绝（exit 2），
不足额则截断本次发送量。限频是安全边界，属于代码而非提示词——**硬规则永远不放
在模型可协商的层面**。

## 2. 阶段 1：LLM 接入与结构化抽取

### 2.1 自研轻量客户端（httpx 直连）而非 openai SDK

选择：`tools/llm.py` 约 300 行，直接实现 chat.completions 协议。

- 为什么：a) 依赖极简（httpx 本就是原依赖，SDK 引入子依赖树）；b) 重试策略、
  超时、usage 记账、成本核算全部显式可控，这些恰是本项目评测要统计的数据，
  用 SDK 意味着在回调里反推；c) SSE 流式解析自己写，服务层 /generate 直接复用。
- 代价：协议细节要自己扛（见测试覆盖：SSE usage 在顶层 chunk、4xx 不重试、
  json_object 不被支持时降级）。

### 2.2 连接配置与行为参数分离

- `.env`：`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` —— 换供应商只改三行
  （当前为硅基流动托管的 DeepSeek-V4-Flash，可一键切回官方 DeepSeek）。
- `config.yaml`：temperature / 重试次数 / max_tokens / **价格表**。
  密钥永不进 config，策略永不进 .env。

### 2.3 重试分两层，语义不同

- 网络层（客户端内）：429/5xx/超时 → 指数退避，最多 `max_retries`；
  4xx 参数错误立即失败，不重试（重试无意义且可能放大故障）。
- 业务层（extract_jd 内）：模型输出**不是合法 JSON 或不符合 Schema** →
  把校验错误信息回喂给模型再要一次（最多 `extract_max_retries`）。
  两层不嵌套循环：网络层失败直接判负，避免放大调用次数。

### 2.4 JSON 抽取的容错链

`json_object` 响应模式（端点不支持时自动降级为提示词约束）→
`parse_model_json` 容忍 markdown 围栏/前后缀文本 → Pydantic 严格校验 →
失败回喂重试。每次抽取（成败/尝试数/错误）写 `logs/jd_extract_log.jsonl`，
评测阶段据此统计**抽取失败率**，而不是等评测时再造数据。

### 2.5 token 记账与价格表分离

`logs/llm_calls.jsonl` 只记 model / purpose / prompt_tokens / completion_tokens /
latency_ms / attempts —— 这些是不可变的客观事实。成本 = token × 价格表，
价格表放 config 且可随时修正：价格变动不需要重跑评测，也不污染历史日志。
**日志记事实，成本是推论。**

### 2.6 为什么默认 temperature=0.2、抽取单独更低

抽取是信息还原任务，要确定性；生成（求职信）要一点发散。两者分开配置，
由调用方在每次 chat() 时显式指定，客户端默认值只做兜底。
