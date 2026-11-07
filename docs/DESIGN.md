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

## 4. 阶段 3：LangGraph 编排

### 4.1 图状态与业务数据分离

每条 lead 一个 thread（`thread_id = "lead-{id}"`），图运行状态（检索结果、
匹配裁决、草稿、质检意见、重试计数）由 SQLite checkpointer 持久化，
**进程重启后 `graph resume` 接着跑**；而 lead 本体（公司/邮箱/正文/发送日志）
仍归原有 JSON store。为什么分离：图状态是「工作流中间态」，生命周期短、
可重放；lead 是「业务事实」，要长期可审计。混在一起会让两边都变脆。

### 4.2 质检回退：规则 + LLM 双层，用尽重试仍到人工闸门

质检 = 规则检查（长度/占位符/套话，免费必查）+ LLM 审稿人（编造证据/
JD 对齐/语气）。不通过时把 **issues 列表作为修改指令回喂给 draft 节点重写**，
最多 `graph.max_retries` 次。重试用尽后不静默丢弃，而是带着完整 issues
停在人工闸门——**质检提意见，人做决定**（可强制通过并留下审计痕迹
`error="人工强制通过"`）。规则层保证 LLM 挂掉时质检仍有底线结论。

### 4.3 审批闸门：interrupt() 而非工具

人工审批用 LangGraph 的 `interrupt()`：图跑到 finalize 后暂停，
决策由图外 `Command(resume={"action": ...})` 注入。关键安全设计：
- 审批**不是模型可调用的工具**，模型没有任何节点能触达发送或修改审批结果；
- 匹配分低于阈值的 lead 在 finalize 直接终态（skipped），根本不进闸门；
- 发送邮件完全在图外（原有 `send --confirm`），闸门只决定 ready 与否。

### 4.4 LLM 匹配评分与词法分的关系

原 match.py 的词法打分降级为「对照信号」：仍会计算并拼进 LLM 评分提示词
（标注"仅供对照"），主判由 LLM 给出结构化 MatchVerdict（分数/理由/JD 原文
证据引用/硬性缺口）。证据引用字段强制模型从 JD 原文摘录，为人工复核提供抓手。

### 4.5 结构化任务的统一循环

抽取/匹配/质检三个 LLM 任务共享 `ask_validated_json`：请求 → 容错解析 →
Pydantic 校验 → 失败把错误信息回喂重试。策略全项目一致，测试一次覆盖三种用途。

## 5. 阶段 4：评测

### 5.1 标注只由人做，工具只预填客观上下文

`make_label_skeletons.py` 生成骨架时只填岗位 id、JD 预览等**客观上下文**，
判断字段全部留空——工具不得替标注者做任何判断。抽取金标准要求**按原文抄写**
（未提及填空串、无法确定填 null=跳过），避免「标注者脑补」与「抽取器超范围」
两个方向的偏差混进指标。示例标注（examples/demo/eval）由脚本作者编写，
明确标注仅供验证脚本流程，其结果不代表系统效果。

### 5.2 三组检索对照本身是设计的一部分

纯向量 / 混合 / 混合+重排不只是三个数字：demo 跑分里出现过
「混合 0.958 < 纯向量 1.000、加重排后回到 1.000」的情形——小语料上 BM25
召回可能把相关块挤出 top-5，重排再把它捞回来。这正是三条通道失效模式
互补的实证，也是把 rerank 做成可配置层的原因。指标在 job 级聚合
（chunk 命中 → 每 job 取其最高排名 chunk，保序去重），与业务语义一致。

### 5.3 流水线评测不需要标注，先出真实数字

质检回退率、平均耗时、token 成本四个指标只依赖系统行为不依赖人工判断，
因此在 43 条真实 JD（V2EX 公开帖，来源可溯）上先跑出真实结果；
匹配准确率、抽取字段准确率、检索 Recall/MRR 三项依赖人工标注，
标注完成前不出数字。token 成本 = 日志 token 数 × config 价格表
（价格默认 0，token 数是客观事实、成本是推论，两者分开）。

### 5.4 采集合规

数据集来源为 V2EX 酷工作等公开、无需登录的页面（服务端渲染可直接解析），
遵守项目「不爬登录墙」规则；每条数据带 source_url 溯源；请求间隔 1.5s 低频抓取。

**实际案例（放弃一次采集）**：曾评估某秋招聚合站作为数据源。探查发现其 robots.txt
带 Cloudflare 内容信号 `search=yes, ai-train=no, use=reference`——即仅允许即时/参考性
使用与搜索索引，明确禁止 AI 训练用途；批量抓取 JD 存入公开仓库做 RAG 语料与评测
数据集，涉及全量复制与再分发，超出「参考使用」授权范围。决定不采集，改用：
a) 人工浏览时逐条复制（reference 用途，合规）；b) 联系站长取得许可；c) 维持
V2EX 公开帖数据源。教训：**robots 的 Content-Signal 是站点的明示权利保留，
「技术上能抓」不等于「被允许用」**；采集前先读 robots.txt 是这个项目的硬规则。

## 6. 阶段 5：服务化

### 6.1 Web 层不拥有任何审批/发送能力

FastAPI 只暴露三个只读/生成端点（search / match / generate），
**没有 send、没有 approve、没有改状态的写端点**——审批留在 CLI 人工闸门，
发送留在 `send --confirm`。Streamlit 看板只读展示线索状态。
原则：对外服务面越大，误触发面越大；有副作用的动作只留一条人工路径。

### 6.2 SSE 流式生成

/generate 用 `chat_stream`（阶段 1 已实现）逐 token 推送 `data: {"delta": ...}`，
结束发 `{"done": true}`，异常发 `{"error": ...}`——流中断也要让前端拿到明确信号。
提示词与 CLI 生成共用 DRAFT_SYSTEM_PROMPT，证据约束（只用 highlights）不因走
服务化而放松。token/耗时记账复用同一 llm_calls.jsonl（purpose=svc_generate）。

### 6.3 工厂模式装配

`create_app(retriever_builder=..., llm_builder=...)` 依赖注入便于测试
（假检索器/假 LLM，8 个用例全离线，含 SSE 解析）；生产入口 `app = create_app()`
惰性构建单例（首次请求才连 Chroma/装 API key），导入轻、启动快。




