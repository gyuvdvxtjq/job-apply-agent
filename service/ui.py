# -*- coding: utf-8 -*-
"""JobMatch-Agent 演示页面（Streamlit）。

运行：先起 API 服务（uvicorn service.app:app --port 8000），再
`streamlit run service/ui.py`。看板为只读：审批与发送只在 CLI 人工闸门进行。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import httpx
import streamlit as st

SERVICE = os.environ.get("JM_SERVICE_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="JobMatch-Agent", page_icon="🎯", layout="wide")
st.title("🎯 JobMatch-Agent — 校招岗位匹配与求职信生成")
st.caption("定位：语义匹配与辅助决策。发送/审批不经过本页面。")

tabs = st.tabs(["🔎 岗位检索", "✍️ 匹配与求职信生成", "📋 线索看板（只读）"])


def read_sse(resp) -> str:
    full = ""
    box = st.empty()
    for line in resp.iter_lines():
        if not line.startswith("data:"):
            continue
        try:
            payload = json.loads(line[len("data:"):].strip())
        except json.JSONDecodeError:
            continue
        if "delta" in payload:
            full += payload["delta"]
            box.markdown(full + "▌")
        elif payload.get("error"):
            st.error(f"生成失败: {payload['error']}")
        elif payload.get("done"):
            box.markdown(full)
            st.success("生成完成")
    return full


with tabs[0]:
    query = st.text_input("自然语言查询", "深圳有哪些要求 RAG 经验的校招岗")
    c1, c2, c3 = st.columns(3)
    top_k = c1.slider("Top K", 1, 20, 5)
    mode = c2.selectbox("召回模式", ["hybrid", "vector", "bm25"])
    rerank = c3.checkbox("启用重排", value=True)
    if st.button("检索", type="primary"):
        try:
            with httpx.Client(timeout=90) as client:
                r = client.post(
                    f"{SERVICE}/search",
                    json={"query": query, "top_k": top_k, "mode": mode,
                          "rerank": True if rerank else False},
                )
                r.raise_for_status()
                rows = r.json()["results"]
            if not rows:
                st.warning("无结果（先在 CLI 执行 rag-ingest 入库）")
            for i, row in enumerate(rows, 1):
                score = (row.get("rerank_score") or row.get("rrf_score")
                         or row.get("vector_score") or row.get("bm25_score") or 0)
                with st.expander(
                    f"{i}. [{row.get('section')}] {row.get('company') or '?'} · "
                    f"{row.get('job_title') or '?'}（{row.get('city') or '?'}）score={score}"
                ):
                    st.write(row.get("text"))
                    st.caption(f"job_id={row.get('job_id')} chunk={row.get('chunk_id')}")
        except Exception as e:
            st.error(f"服务不可用: {e}")

with tabs[1]:
    st.write("先匹配评估，再流式生成求职信。证据只来自演示画像，实际使用请替换 profile。")
    profile_path = st.text_input("画像路径（可选，默认演示画像）", "")
    c1, c2 = st.columns(2)
    company = c1.text_input("公司", "示例科技")
    job_title = c2.text_input("岗位", "大模型应用开发实习生")
    jd = st.text_area("JD 文本", "岗位职责：参与 RAG 检索增强系统的搭建与优化；任职要求：熟悉 Python…", height=160)
    if st.button("① 匹配评估", type="secondary"):
        try:
            with httpx.Client(timeout=120) as client:
                r = client.post(f"{SERVICE}/match",
                                json={"job_text": jd, "profile_path": profile_path})
                r.raise_for_status()
                v = r.json()["verdict"]
            st.metric("匹配分", f"{v['score']:.2f}")
            st.write("**理由**：" + "；".join(v.get("reasons") or []))
            if v.get("evidence_quotes"):
                st.caption("JD 原文证据：" + " / ".join(v["evidence_quotes"][:3]))
            if v.get("hard_gaps"):
                st.warning("硬性缺口：" + "；".join(v["hard_gaps"]))
        except Exception as e:
            st.error(f"服务不可用: {e}")
    if st.button("② 流式生成求职信", type="primary"):
        try:
            with httpx.Client(timeout=300) as client:
                with client.stream(
                    "POST", f"{SERVICE}/generate",
                    json={"company": company, "job_title": job_title, "jd_text": jd,
                          "profile_path": profile_path},
                ) as resp:
                    resp.raise_for_status()
                    read_sse(resp)
        except Exception as e:
            st.error(f"服务不可用: {e}")

with tabs[2]:
    data_file = Path(__file__).resolve().parents[1] / "data" / "job_leads.json"
    if not data_file.exists():
        st.info("暂无线索数据（data/job_leads.json）")
    else:
        data = json.loads(data_file.read_text(encoding="utf-8"))
        leads = data.get("leads") or []
        counts: dict[str, int] = {}
        for x in leads:
            counts[x.get("status") or "pending"] = counts.get(x.get("status") or "pending", 0) + 1
        cols = st.columns(len(counts) or 1)
        for col, (status, n) in zip(cols, sorted(counts.items())):
            col.metric(status, n)
        st.dataframe(
            [
                {
                    "ID": x.get("id"), "状态": x.get("status"),
                    "公司": x.get("company"), "岗位": x.get("job_title"),
                    "匹配分": x.get("match_score"),
                    "来源": x.get("source_url"),
                }
                for x in leads
            ],
            use_container_width=True,
        )
        st.info("审批在 CLI 人工闸门进行：`python tools/cli.py graph resume --lead N --approve`；"
                "发送需 `send --confirm`。本页面不提供任何写操作。")
