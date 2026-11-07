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

## 3. 阶段 2：岗位 RAG

### 3.1 按标题语义分块，而非固定滑动窗口

JD 是高度模板化文本，「岗位职责 / 任职要求 / 福利地点」标题本身就是语义边界。
按标题切分保证每个 chunk 自成一个可检索、可展示的语义单元——**检索粒度 = 展示粒度**，
命中后直接把该段原文给用户看。固定窗口会把一句要求拦腰截断，两类查询（职责类、
门槛类）都会被噪声稀释。

标题判定做了精度保护：命中关键词后**残余必须只剩标点/空白**才算标题行，
因此「工作地点深圳，简历投递至 hr@x.com」这类含关键词的正文不会误切，
「工作地点：深圳」这类 KV 行保留为正文不丢内容。无标题 JD 整体归入「其他」，
超长段按句切分（默认 500 字符），保证 chunk 上界。

### 3.2 为什么混合检索（向量 + BM25）

两条通道的失效模式互补：

- **向量（bge-m3）**：语义泛化强，「有检索经验的岗」能召回写了「RAG/向量数据库」
  的 JD；但低频专有名词（LangGraph、Flink、DolphinScheduler）在嵌入空间里区分度弱。
- **BM25（jieba 分词）**：精确关键词召回，框架名/模型名这类低频词是它的强项；
  但完全无法处理同义改写。

只用任何一条，另一类的查询必挂。融合用 **RRF（Reciprocal Rank Fusion）**：
score = Σ 1/(k+rank)，只用两路的排名不用分数，避免余弦相似度与 BM25 分数
量纲不可比的问题。评测阶段做「纯向量 / 混合 / 混合+重排」三组对照
（`search --mode vector|bm25|hybrid` + `rerank.enabled` 开关就是为对照准备的）。

### 3.3 重排作为可选层

cross-encoder 重排（bge-reranker-v2-m3）对 top 候选做逐 pair 精排，
精度最高但延迟与费用线性增长。设计为可配置层（`rag.rerank.enabled`）：
默认开启用于线上质量；评测对照组关闭。向量库规模为百级 chunk，
BM25 索引每次查询毫秒级重建，**不做持久化**——省掉一份索引文件的一致性维护。

### 3.4 环境排查记录（面试素材：Rust 原生扩展段错误）

chromadb 1.x 的 Rust 绑定在本机持续 segfault（`add` 阶段，faulthandler 定位）。
逐层排查：换 chromadb 版本（1.0–1.5 全崩）→ 关遥测（无效）→ 排查发现
**0.6.x 需要 C++ 编译器且 chroma-hnswlib 无 cp312 Windows wheel** →
最终定位为 **venv 父解释器是 Anaconda，其捆绑的 MKL/DLL 与 Rust 扩展冲突**。
换用 uv 管理的干净 CPython 3.13.9 重建 venv 后完全正常。
教训：原生扩展出问题时，先隔离「解释器来源」这个变量，再怀疑包本身。

### 3.5 chromadb EphemeralClient 的进程内共享陷阱

同一进程内多个 `EphemeralClient()` 共享同一个 System（按 settings 缓存），
测试里会出现「新建的空库读到了前面用例的数据」。测试用每用例唯一集合名隔离；
生产用 PersistentClient（按路径隔离）不受影响。

