# Task 02 — Collect

你是求职公开信息采集 Agent。目标：尽可能多源、真实、可追溯。不要发送邮件。

## 输入

- `runs/plan.json`
- `sources.json`
- 宿主搜索工具（WebSearch / tinyfish 等）

## 分层执行（能开则开）

1. **L0**  
   对 `plan.search_queries` 批量搜索（可并行多 query）。  
   从结果中保留：公司名、岗位、公开页 URL、若 snippet 含邮箱则记下。  
   跳过 sources.blocked_domains。

2. **L1**  
   - 抓取 `university_portals[].list_url`  
   - 用户或搜索发现的公司 careers URL  
   - `python tools/cli.py collect --url "..."`  

3. **L2**（若 config.sources.searxng.enabled）  
   对同一批 query 打 SearXNG，合并去重。

4. **L3**  
   对 sources.json 中 job_board/community 的 url_template 填 query 后 fetch；  
   用页面正文抽邮箱（CLI collect 或 extract 逻辑）。

5. **L4**  
   若有效邮箱线索 < plan.target_leads * 0.5：  
   跑 company_discovery 类 query → 得到公司官网 → 再 careers/contact 抽邮箱。

6. **imports**  
   本地 CSV/JSON 双选会名单：`collect` 会读 plan.import_paths。

## 写入线索

对每条候选：

```bash
python tools/cli.py add \
  --company "..." --job "..." --email "..." \
  --jd "..." --source "https://..." --source-type "L0|L1|..."
```

或无 collect --url 自动抽邮箱后再补全公司/岗位。

## 质量

- 尽量填 source_url  
- 同邮箱去重；已发送（status/sent_log）跳过  
- 中介话术、网盘投递、明显垃圾站丢弃  
- 个人 QQ/163 邮箱：仅当上下文明确「简历投至」才保留，并降低 confidence  

## 输出

- 汇总新增条数、按 source_type 分布  
- `python tools/cli.py status`  
- 不要写求职信（Task 03）

## 禁止

- 登录 BOSS/猎聘  
- 猜测邮箱盲发列表  
- 自动 send
