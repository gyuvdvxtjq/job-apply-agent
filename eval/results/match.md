## 匹配评测：LLM 匹配分 vs 人工标注

- 阈值: score ≥ 0.5 判为匹配 | 样本: 124（抽取失败 0 不计入）
- 画像: examples/demo/profile.yaml | 模型: deepseek-ai/DeepSeek-V4-Flash
- 生成时间: 2026-11-07T16:44:09

| 准确率 | 精确率 | 召回率 | F1 | TP | FP | TN | FN |
|---|---|---|---|---|---|---|---|
| 0.927 | 0.455 | 0.625 | 0.526 | 5 | 6 | 110 | 3 |

### 逐条明细

| job_id | 人工 | 预测 | score | 首条理由 |
|---|---|---|---|---|
| v2ex-1214844 | 1 | 0 | 0.4 | 候选人具备Python编程能力，与JD中提到的支持语言之一Python匹配，但项 |
| v2ex-1234409 | 0 | 0 | 0.2 | 候选人仅有校招级项目经历，缺乏JD要求的5年以上研发管理或架构经验 |
| v2ex-1238194 | 0 | 1 | 0.5 | 候选人的技能（Python、SQL、数据分析）与JD中提到的数据相关方向（如搜索 |
| v2ex-1239744 | 0 | 0 | 0.3 | 候选人具备Python、Pandas、SQL等基础数据处理技能，并有AI Age |
| v2ex-1240000 | 0 | 0 | 0.2 | 候选人技能以数据分析与AI Agent为主，缺少JD中强调的搜广推、广告算法或模 |
| v2ex-1240083 | 0 | 0 | 0.25 | 候选人仅有数据分析与AI Agent相关项目，无后端核心模块开发经验，与JD要求 |
| v2ex-1240378 | 0 | 0 | 0.15 | 候选人技能栈为 Python/Pandas/SQL/PyTorch，与岗位要求的 |
| v2ex-1240480 | 0 | 0 | 0.35 | 候选人专业为计算机科学本科，符合学历专业要求，且具备Python、SQL等基础技 |
| v2ex-1240496 | 0 | 0 | 0.25 | 候选人掌握Python，满足JD中后端语言之一的基本要求，但技能集中在数据分析与 |
| v2ex-1240770 | 0 | 0 | 0.15 | 简历技能集中在Python、Pandas、SQL、PyTorch，方向为数据分析 |
| v2ex-1241300 | 0 | 0 | 0.1 | 简历技能（Python、Pandas、SQL、PyTorch）与岗位要求的前端技 |
| v2ex-1241436 | 0 | 0 | 0.1 | 候选人技能栈为 Python、Pandas、SQL、PyTorch，方向为数据分 |
| v2ex-1241903 | 0 | 0 | 0.0 | 简历画像未提供任何候选人信息，无法进行匹配评估 |
| v2ex-1241967 | 0 | 0 | 0.1 | 简历技能集中在Python、Pandas、SQL、PyTorch，属于数据分析与 |
| v2ex-1241978 | 1 | 1 | 0.5 | 候选人具备Python、Pandas、SQL等技能，与数据分析师岗位要求匹配，且 |
| v2ex-1242183 | 0 | 0 | 0.15 | 候选人只有数据分析相关项目经验，未涉及任何后端开发、FastAPI、ComfyU |
| v2ex-1242192 | 0 | 0 | 0.05 | 简历技能为Python、Pandas、SQL、PyTorch，方向为数据分析、A |
| v2ex-1242236 | 0 | 0 | 0.35 | 简历技能集中在 Python/Pandas/SQL/PyTorch，缺少 JD  |
| v2ex-1242340 | 0 | 0 | 0.15 | 学历不满足：JD要求硕士以上学历，简历为本科 |
| v2ex-1242471 | 0 | 0 | 0.25 | 候选人技能栈为Python/Pandas/SQL/PyTorch，而JD核心岗位 |
| v2ex-1242751 | 0 | 0 | 0.3 | 学历不符合硬性要求：JD要求硕士及以上学历，简历为本科。 |
| v2ex-1242765 | 0 | 0 | 0.35 | 候选人具备Python、PyTorch等技能，与岗位要求的AI部署工具链方向有一 |
| v2ex-1242992 | 0 | 0 | 0.45 | 候选人掌握 Python，与 JD 开发工程师岗位技术栈中的 Python 匹配 |
| v2ex-1243473 | 0 | 0 | 0.2 | 候选人仅有基础数据分析与简单Agent工作流项目，缺乏大规模模型训练、后训练或推 |
| v2ex-1243505 | 0 | 0 | 0.1 | 候选人仅有校招级项目经历（数据分析、Agent工作流），无任何互联网产品经理经验 |
| v2ex-1243640 | 0 | 0 | 0.42 | 候选人技能栈（Python、PyTorch）与算法岗有基础契合，且项目涉及AI  |
| v2ex-1243697 | 0 | 0 | 0.3 | 简历仅有校招级的数据分析项目和Agent工作流，缺乏3年以上工程经验，与JD要求 |
| v2ex-1243876 | 0 | 0 | 0.1 | 候选人技能为 Python、Pandas、SQL、PyTorch，方向是数据分析 |
| v2ex-1243965 | 0 | 0 | 0.45 | 候选人的Python技能与JD中软件工程师要求的技术栈Python匹配，且具备数 |
| v2ex-1244185 | 0 | 0 | 0.1 | 简历技能栈为 Python/Pandas/SQL/PyTorch，与 JD 要求 |
| v2ex-1244216 | 0 | 0 | 0.25 | 候选人技能栈以 Python 为主，缺少岗位必需的 Java 后端开发经验及 S |
| v2ex-1244221 | 0 | 0 | 0.25 | 候选人具备Python和PyTorch技能，与岗位要求的部分编程技能匹配，但缺乏 |
| v2ex-1244320 | 0 | 0 | 0.1 | 简历为校招生，技能集中在Python数据分析与AI Agent方向，缺少岗位必备 |
| v2ex-1244352 | 0 | 0 | 0.0 | 未提供候选人简历画像，无法进行任何匹配度评估 |
| v2ex-1244354 | 0 | 0 | 0.0 | 未提供候选人简历画像，无法进行匹配评估 |
| v2ex-1244365 | 1 | 0 | 0.0 | 未提供候选人简历画像，无法进行匹配度评估 |
| v2ex-1244740 | 0 | 0 | 0.1 | 候选人技能为Python、Pandas、SQL、PyTorch，方向为数据分析与 |
| v2ex-1244881 | 0 | 0 | 0.1 | 简历技能为 Python/Pandas/SQL/PyTorch，与 JD 要求的 |
| v2ex-1245372 | 0 | 0 | 0.3 | 候选人具备 Python 和 AI Agent 项目经历，与 JD 中提到的 A |
| v2ex-1245478 | 0 | 0 | 0.15 | 候选人技能栈为 Python/Pandas/PyTorch，与岗位要求的 C++ |
| v2ex-1245635 | 0 | 0 | 0.2 | 候选人技能栈为Python、Pandas、SQL、PyTorch，与岗位要求的R |
| v2ex-1245895 | 0 | 0 | 0.05 | 候选人技能为Python、Pandas、SQL、PyTorch，方向为数据分析与 |
| v2ex-1245910 | 0 | 0 | 0.35 | 候选人具备 Python、Pandas、SQL 等基础数据技能，与 JD 中数据 |
| v2ex-1246063 | 0 | 0 | 0.15 | 候选人技能栈为Python、Pandas、SQL、PyTorch，方向为数据分析 |
| v2ex-1246802 | 0 | 0 | 0.2 | 岗位JD明确要求2年以上相关技术经验，而候选人为校招生，无工作经验 |
| v2ex-1246998 | 1 | 1 | 0.55 | 候选人计算机相关专业，符合岗位硬性学历要求。 |
| v2ex-1247150 | 0 | 0 | 0.25 | 候选人技能栈为Python、Pandas、SQL、PyTorch，方向为数据分析 |
| v2ex-1247345 | 0 | 0 | 0.15 | 候选人技术栈为Python、Pandas、SQL、PyTorch，与岗位要求的G |
| v2ex-1247404 | 0 | 0 | 0.45 | 候选人具备Python技能，满足JD中后端要求'熟悉Rust/Go/Java/P |
| v2ex-1247418 | 0 | 0 | 0.1 | 候选人技能与项目经历集中在数据分析与AI Agent，与JD中所有岗位的核心技能 |
| v2ex-1247441 | 0 | 0 | 0.35 | 候选人具备Python、PyTorch等算法基础技能，与岗位要求的算法基础有一定 |
| v2ex-1247575 | 0 | 0 | 0.15 | 简历技能栈为 Python、Pandas、SQL、PyTorch，方向为数据分析 |
| v2ex-1247600 | 0 | 0 | 0.35 | 技能栈包含 Python，与 JD 中技术栈 Python 匹配 |
| v2ex-1247678 | 0 | 0 | 0.45 | 候选人具备 Python 和 PyTorch 技能，且有 Agent 工作流项目 |
| v2ex-1247695 | 0 | 0 | 0.25 | 候选人技能集中在数据分析与AI Agent（Python、Pandas、SQL、 |
| v2ex-1247753 | 0 | 0 | 0.1 | 候选人技能为Python、Pandas、SQL、PyTorch，方向为数据分析与 |
| v2ex-1248166 | 0 | 0 | 0.3 | 简历中有 Agent 工作流项目，使用 Python 和 Prompt，与岗位要 |
| v2ex-1248181 | 0 | 0 | 0.15 | JD要求3年以上AI Agent/AI应用开发经验及全栈工程能力，简历为应届生且 |
| v2ex-1248322 | 0 | 0 | 0.2 | 候选人具备Python和AI Agent项目经历，但岗位核心是质量保障与测试体系 |
| v2ex-1248334 | 0 | 0 | 0.35 | 简历具备Python、Pandas、SQL等数据分析技能，与岗位中LLM Dat |
| v2ex-1248501 | 0 | 1 | 0.5 | 本科学历为计算机科学，符合岗位学历要求 |
| v2ex-1248715 | 0 | 0 | 0.12 | 候选人技术栈为 Python/Pandas/PyTorch，与岗位要求的 Jav |
| v2ex-1248790 | 0 | 0 | 0.45 | 候选人方向包含 AI Agent，并有 Agent 工作流项目经历，与 JD 中 |
| v2ex-1248881 | 0 | 0 | 0.35 | 候选人技能以Python、Pandas、SQL、PyTorch为主，与岗位要求的 |
| v2ex-1248933 | 1 | 1 | 0.62 | 候选人专业为计算机科学本科，符合JD中“计算机或地理信息相关专业”的要求。 |
| v2ex-1249034 | 0 | 0 | 0.08 | 简历技能集中在Python、Pandas、SQL、PyTorch，无任何前端开发 |
| v2ex-1249103 | 0 | 0 | 0.1 | 简历技能栈为 Python、Pandas、SQL、PyTorch，与岗位核心要求 |
| v2ex-1249116 | 0 | 0 | 0.1 | 简历技能为 Python、Pandas、SQL、PyTorch，与岗位要求的现代 |
| v2ex-1249338 | 0 | 1 | 0.55 | 候选人具备Python技能，与岗位JD中软件开发工程师的技术栈Python匹配 |
| v2ex-1249364 | 0 | 0 | 0.15 | 候选人技能和项目经历聚焦于数据分析与AI Agent，完全没有信息安全相关经验， |
| v2ex-1249382 | 0 | 0 | 0.1 | 候选人技能栈为Python、Pandas、SQL、PyTorch，方向是数据分析 |
| v2ex-1249442 | 0 | 0 | 0.1 | 候选人技能栈为 Python/Pandas/SQL/PyTorch，方向为数据分 |
| v2ex-1249598 | 0 | 0 | 0.35 | 候选人具备Python、Pandas、SQL等数据分析技能，与JD中数据/数仓方 |
| v2ex-1249926 | 0 | 0 | 0.1 | 候选人技能栈为 Python、Pandas、PyTorch，与岗位要求的 .NE |
| v2ex-1250045 | 0 | 0 | 0.1 | 简历仅有数据分析项目经历，未体现3年以上软件开发经验，不满足硬性年限要求 |
| v2ex-1250192 | 0 | 0 | 0.1 | 候选人技能为Python、Pandas、SQL、PyTorch，方向为数据分析和 |
| v2ex-1250716 | 0 | 0 | 0.1 | 岗位要求3年及以上服务端开发经验，且为高级岗位（5年+），候选人无任何工作经验， |
| v2ex-1250726 | 0 | 0 | 0.2 | 简历技能集中在数据分析与AI Agent，缺乏AIGC图像/视频生成相关经验 |
| v2ex-1250841 | 0 | 0 | 0.1 | 候选人简历仅涉及 Python/Pandas 等数据分析技能，完全没有 Gola |
| v2ex-1250883 | 0 | 0 | 0.05 | 候选人技能为Python、Pandas、SQL、PyTorch，方向为数据分析与 |
| v2ex-1250894 | 0 | 0 | 0.1 | 候选人技能集中在Python/Pandas/SQL/PyTorch，方向为数据分 |
| v2ex-1251134 | 0 | 0 | 0.35 | 候选人具备 Python 编程能力和 AI Agent 项目经历，与 JD 中‘ |
| v2ex-1251159 | 1 | 0 | 0.35 | 简历技能包含 Python、SQL、PyTorch，与岗位基础技术栈有一定重合， |
| v2ex-1251326 | 0 | 1 | 0.55 | 候选人掌握 Python，与软件工程师岗位技术栈中的 Python 匹配 |
| v2ex-1251346 | 0 | 0 | 0.1 | 候选人技能栈为Python、Pandas、SQL、PyTorch，属于数据分析/ |
| v2ex-1251510 | 0 | 0 | 0.25 | 候选人技能栈为 Python/Pandas/PyTorch，与岗位要求的 Jav |
| v2ex-1251531 | 0 | 0 | 0.45 | 候选人具备Python技能和AI Agent项目经历，与JD中要求的语言和加分项 |
| v2ex-1251611 | 0 | 0 | 0.35 | 候选人具备Python、Pandas、SQL等基础技能，但岗位要求熟悉async |
| v2ex-1252035 | 0 | 0 | 0.15 | 简历技能为Python、Pandas、SQL、PyTorch，无Java开发经验 |
| v2ex-1252151 | 0 | 0 | 0.25 | 候选人具备Python、PyTorch等基础技能，但岗位要求生产级GPU推理或大 |
| v2ex-1252175 | 0 | 1 | 0.55 | 候选人具备Python、Pandas、SQL等数据处理技能，并有AI Agent |
| v2ex-1252375 | 0 | 0 | 0.2 | 候选人技能栈为Python/Pandas/SQL/PyTorch，方向为数据分析 |
| v2ex-1252412 | 0 | 0 | 0.1 | 候选人技能集中在数据分析与AI Agent，与弱电设计所需的KNX、网络、监控等 |
| v2ex-1252484 | 0 | 0 | 0.15 | 候选人技能栈为 Python、Pandas、SQL、PyTorch，方向是数据分 |
| v2ex-1252499 | 0 | 0 | 0.2 | 候选人具备Python、PyTorch基础，且有Agent工作流项目经历，与岗位 |
| v2ex-1252526 | 1 | 1 | 0.68 | 候选人具备 Python 编程能力和 AI Agent 项目经历，直接匹配 JD |
| v2ex-1252554 | 0 | 0 | 0.2 | 简历为校招生，无3年以上软件开发经验，不满足JD硬性要求第1条 |
| v2ex-1252864 | 0 | 0 | 0.1 | 候选人技能栈为 Python、Pandas、SQL、PyTorch，方向为数据分 |
| v2ex-1252876 | 0 | 0 | 0.45 | 候选人具备 Python、PyTorch 和 Agent 工作流经验，与 JD  |
| v2ex-1252914 | 0 | 0 | 0.15 | 候选人技能以 Python/Pandas/PyTorch 为主，缺少 JD 要求 |
| v2ex-1252953 | 0 | 0 | 0.1 | 候选人技能为Python、Pandas、SQL、PyTorch，而岗位要求精通R |
| v2ex-1253074 | 0 | 1 | 0.55 | 候选人掌握Python，符合JD中至少一种语言的要求（Golang、Python |
| v2ex-1253103 | 0 | 0 | 0.2 | 简历技能以数据分析与AI Agent为主，与JD中要求的K8s运维、后端开发（G |
| v2ex-1253233 | 0 | 0 | 0.4 | 候选人具备Python编程能力，符合JD中“熟练掌握至少一门主流编程语言”的要求 |
| v2ex-1253279 | 1 | 1 | 0.58 | 候选人具备Python、SQL技能，且有数据分析项目经历，与JD中'熟悉Pyth |
| v2ex-1253785 | 0 | 0 | 0.08 | 候选人无任何全职算法工作经验，不满足JD中“3年以上算法相关工作经验”的硬性要求 |
| v2ex-1253828 | 0 | 0 | 0.45 | 候选人研究方向为AI Agent与数据分析，与岗位核心方向AI Agent应用开 |
| v2ex-1253849 | 0 | 0 | 0.2 | 简历技能为Python、Pandas、SQL、PyTorch，而JD优先要求Ru |
| v2ex-1253866 | 0 | 0 | 0.25 | 候选人技能以 Python/Pandas/SQL/PyTorch 为主，方向是数 |
| v2ex-1254085 | 0 | 0 | 0.25 | 候选人仅有数据分析与简单Agent工作流项目，未体现复杂后端系统或基础设施研发经 |
| v2ex-1254137 | 0 | 0 | 0.25 | 候选人技能以 Python、Pandas、SQL、PyTorch 为主，缺少岗位 |
| v2ex-1254210 | 0 | 0 | 0.1 | 简历方向为数据分析与AI Agent，与JD中的Flutter/Web前端、Go |
| v2ex-1254277 | 0 | 0 | 0.15 | 简历技能为Python、Pandas、SQL、PyTorch，方向为数据分析与A |
| v2ex-1254471 | 0 | 0 | 0.4 | 候选人具备Python、SQL、Pandas等数据分析技能，与岗位对数据相关能力 |
| v2ex-1254493 | 0 | 0 | 0.15 | 候选人技能为Python、Pandas、SQL、PyTorch，方向是数据分析与 |
| v2ex-1254512 | 0 | 0 | 0.2 | 候选人技术栈为 Python/Pandas/SQL/PyTorch，与岗位要求的 |
| v2ex-1254553 | 0 | 0 | 0.32 | 候选人具备计算机科学本科学历和Python、SQL等技能，符合学历专业基本要求， |
| v2ex-1254613 | 0 | 0 | 0.35 | 候选人具备Python、Pandas、SQL等数据分析技能，与JD中部分技术岗位 |
| v2ex-1254673 | 0 | 0 | 0.25 | 候选人学历专业符合岗位要求（统招本科计算机相关专业），但缺乏岗位核心要求的 Ja |
| v2ex-1254730 | 0 | 0 | 0.15 | 简历技能集中在Python/Pandas/SQL/PyTorch，方向为数据分析 |
| v2ex-1254733 | 0 | 0 | 0.1 | JD明确要求‘多年大厂研发经验’和‘资深工程师’，而候选人为校招应届生，缺乏工程 |
| v2ex-1254818 | 0 | 0 | 0.1 | 候选人技能为Python、Pandas、SQL、PyTorch，方向为数据分析与 |
| v2ex-1254890 | 0 | 0 | 0.1 | 候选人技能为Python、Pandas、SQL、PyTorch，方向为数据分析与 |
| v2ex-1255084 | 0 | 0 | 0.35 | 候选人具备Python和PyTorch基础，符合岗位对编程语言和机器学习框架的基 |
