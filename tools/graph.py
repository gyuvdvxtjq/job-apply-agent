# -*- coding: utf-8 -*-
"""LangGraph 编排：规划 → 检索 → 抽取 → 匹配评分 → 生成求职信 → 质检（回退重写）→ 人工审批。

- 每条 lead 一个 thread（thread_id = "lead-{id}"），SQLite checkpointer 持久化，
  进程中断/重启后可恢复
- 审批闸门用 interrupt()：图在 finalize 后暂停，人工通过 `graph resume`
  提交 approve/reject 决定；发送动作完全不进图，也不作为任何节点的工具
- 质检不通过回退 draft（携带质检 issues 作为修改指令），最多 max_retries 次；
  用尽后仍停在审批闸门——质检提意见、人工做决定
"""
from __future__ import annotations

import sqlite3
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from draft_llm import draft_cover_letter_llm, qa_cover_letter_llm, qa_cover_letter_rules
from extract_jd import extract_jd_info
from match import match_score
from match_llm import match_lead_with_llm


class PipelineState(TypedDict, total=False):
    lead_id: int
    profile: dict
    lead: dict
    # plan
    search_queries: list[str]
    # retrieve
    retrieved_chunks: list[dict]
    # extract
    jd_info: dict | None
    jd_extract_ok: bool
    # match
    match_verdict: dict | None
    lexical_score: float
    # draft / qa 循环
    draft: str
    qa_issues: list[str]
    qa_passed: bool
    retry_count: int
    max_retries: int
    # 终态
    outcome: str  # awaiting_approval | low_match | llm_failed
    approval: str  # 人工写入 approve | reject
    reject_reason: str
    error: str


def default_graph_cfg(cfg: dict) -> dict:
    g = dict(cfg.get("graph") or {})
    g.setdefault("max_retries", 2)
    g.setdefault("min_match_score", 0.5)
    g.setdefault("retrieve_top_k", 5)
    g.setdefault("db_path", "./data/graph_state.db")
    g.setdefault("collection", (cfg.get("rag") or {}).get("collection") or "jd_chunks")
    return g


def build_pipeline(
    cfg: dict,
    llm: Any,
    retriever: Any,
    leads: Any,
    checkpointer: Any | None = None,
):
    """编译流水线图。llm/retriever/leads 可注入假实现（测试）。"""
    gcfg = default_graph_cfg(cfg)

    # ----------------------------------------------------------- node bodies
    def plan_node(state: PipelineState) -> dict:
        profile, lead = state["profile"], state["lead"]
        directions = profile.get("directions") or []
        queries = []
        title = lead.get("job_title") or ""
        if title:
            queries.append(title)
        for d in directions[:3]:
            queries.append(f"{d} {title}".strip())
        queries.append(f"{lead.get('company') or ''} {title}".strip())
        return {"search_queries": [q for q in queries if q][:5]}

    def retrieve_node(state: PipelineState) -> dict:
        query = " ".join(state.get("search_queries") or [])
        if lead_summary := (state["lead"].get("jd_summary") or "").strip()[:300]:
            query = f"{query} {lead_summary}"
        chunks = retriever.search(query, top_k=int(gcfg["retrieve_top_k"]), mode="hybrid", rerank=False)
        return {"retrieved_chunks": chunks}

    def extract_node(state: PipelineState) -> dict:
        jd_text = state["lead"].get("jd_summary") or ""
        info, stats = extract_jd_info(jd_text, llm, max_retries=int(gcfg["max_retries"]))
        return {
            "jd_info": info.model_dump() if info else None,
            "jd_extract_ok": bool(stats["ok"]),
            "error": "" if stats["ok"] else (stats["errors"][-1] if stats["errors"] else ""),
        }

    def match_node(state: PipelineState) -> dict:
        lead = state["lead"]
        jd_text = lead.get("jd_summary") or ""
        lexical = match_score(state["profile"], f"{lead.get('job_title') or ''}\n{jd_text}")["score"]
        verdict, _stats = match_lead_with_llm(
            state["profile"], jd_text, llm,
            lexical_score=lexical,
            jd_info=state.get("jd_info"),
            max_retries=int(gcfg["max_retries"]),
        )
        update: dict[str, Any] = {"lexical_score": lexical, "match_verdict": verdict.model_dump() if verdict else None}
        if verdict is None:
            update["outcome"] = "llm_failed"
        elif verdict.score < float(gcfg["min_match_score"]):
            update["outcome"] = "low_match"
        return update

    def draft_node(state: PipelineState) -> dict:
        extra = "\n".join(state.get("qa_issues") or []) if state.get("retry_count") else ""
        draft = draft_cover_letter_llm(
            state["profile"], state["lead"],
            jd_info=state.get("jd_info"),
            match_verdict=state.get("match_verdict"),
            retrieved_chunks=state.get("retrieved_chunks"),
            client=llm,
            extra_instructions=extra,
        )
        return {"draft": draft, "qa_issues": [], "qa_passed": False}

    def qa_node(state: PipelineState) -> dict:
        draft = state.get("draft") or ""
        issues = qa_cover_letter_rules(draft, state["lead"])
        verdict, _stats = qa_cover_letter_llm(
            draft, state["profile"], state["lead"].get("jd_summary") or "", llm,
            max_retries=int(gcfg["max_retries"]),
        )
        if verdict is not None:
            issues = issues + list(verdict.issues)
            passed = bool(verdict.passed) and not issues
        else:
            # LLM 质检不可用时退化为纯规则结论（记录在 error）
            passed = not issues
        retry_count = int(state.get("retry_count") or 0)
        update: dict[str, Any] = {
            "qa_issues": issues,
            "qa_passed": passed,
            "retry_count": retry_count + 1,
        }
        return update

    def finalize_node(state: PipelineState) -> dict:
        """把产物写回 lead store；状态置 reviewing，等人工审批。"""
        lead_id = state["lead_id"]
        verdict = state.get("match_verdict") or {}
        leads.update_field(lead_id, "match_score", verdict.get("score", state.get("lexical_score")))
        leads.update_field(lead_id, "jd_info", state.get("jd_info"))
        if state.get("draft"):
            leads.update_field(lead_id, "body", state["draft"])
        leads.update_field(lead_id, "status", "reviewing")
        if state.get("outcome") == "low_match":
            leads.mark_skipped(lead_id, f"匹配分低 {verdict.get('score', 0)} < {gcfg['min_match_score']}")
            leads.update_field(lead_id, "status", "skipped")
        return {"outcome": state.get("outcome") or "awaiting_approval"}

    def approve_node(state: PipelineState) -> dict:
        """人工审批闸门：interrupt() 暂停，图外通过 Command(resume=...) 提交决定。"""
        decision = interrupt(
            {
                "gate": "human_approval",
                "lead_id": state["lead_id"],
                "qa_issues": state.get("qa_issues") or [],
                "qa_passed": state.get("qa_passed"),
                "match_score": (state.get("match_verdict") or {}).get("score"),
            }
        )
        action = (decision or {}).get("action")
        lead_id = state["lead_id"]
        if action == "approve":
            leads.update_field(lead_id, "status", "ready")
            if state.get("qa_issues"):
                leads.update_field(lead_id, "error", "人工强制通过（质检有未解决问题）")
            return {"approval": "approve", "outcome": "approved"}
        reason = (decision or {}).get("reason") or "人工否决"
        leads.mark_skipped(lead_id, reason)
        return {"approval": "reject", "reject_reason": reason, "outcome": "rejected"}

    # ------------------------------------------------------------- routing
    def route_after_match(state: PipelineState) -> str:
        return "finalize" if state.get("outcome") in ("low_match", "llm_failed") else "draft"

    def route_after_qa(state: PipelineState) -> str:
        if state.get("qa_passed"):
            return "finalize"
        if int(state.get("retry_count") or 0) > int(gcfg["max_retries"]):
            return "finalize"
        return "draft"

    # -------------------------------------------------------------- wiring
    g = StateGraph(PipelineState)
    g.add_node("plan", plan_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("extract", extract_node)
    g.add_node("match", match_node)
    g.add_node("draft", draft_node)
    g.add_node("qa", qa_node)
    g.add_node("finalize", finalize_node)
    g.add_node("approve", approve_node)
    g.add_edge(START, "plan")
    g.add_edge("plan", "retrieve")
    g.add_edge("retrieve", "extract")
    g.add_edge("extract", "match")
    g.add_conditional_edges("match", route_after_match, {"draft": "draft", "finalize": "finalize"})
    g.add_edge("draft", "qa")
    g.add_conditional_edges("qa", route_after_qa, {"draft": "draft", "finalize": "finalize"})

    def route_after_finalize(state: PipelineState) -> str:
        # 低分跳过 / LLM 失败直接终态，不进人工闸门
        return "approve" if state.get("outcome") == "awaiting_approval" else END

    g.add_conditional_edges("finalize", route_after_finalize, {"approve": "approve", END: END})
    g.add_edge("approve", END)
    return g.compile(checkpointer=checkpointer)


def make_checkpointer(db_path: str | Any) -> Any:
    """SQLite checkpointer；测试可传 tmp 路径。"""
    from langgraph.checkpoint.sqlite import SqliteSaver

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return SqliteSaver(conn)


def _thread_config(lead_id: int) -> dict:
    return {"configurable": {"thread_id": f"lead-{lead_id}"}}


def run_lead(
    graph: Any,
    leads: Any,
    lead_id: int,
    profile: dict,
    fresh: bool = False,
) -> dict[str, Any]:
    """跑一条 lead 到审批闸门（或终态）。返回最终 state values。"""
    lead = leads.get(lead_id)
    if not lead:
        return {"outcome": "error", "error": f"lead {lead_id} 不存在"}
    config = _thread_config(lead_id)
    if fresh:
        try:
            graph.checkpointer.delete_thread(config["configurable"]["thread_id"])
        except Exception:
            pass
    init: PipelineState = {
        "lead_id": lead_id,
        "profile": profile,
        "lead": lead,
        "retry_count": 0,
        "qa_issues": [],
    }
    result = graph.invoke(init, config)
    # interrupt 时 invoke 返回值带 __interrupt__ 字段；统一取最新快照更稳
    snap = graph.get_state(config)
    values = dict(snap.values) if snap and snap.values else result
    return values


def resume_lead(graph: Any, leads: Any, lead_id: int, decision: dict[str, Any]) -> dict[str, Any]:
    """向审批闸门提交人工决定（approve / reject+reason），跑完剩余节点。"""
    config = _thread_config(lead_id)
    snap = graph.get_state(config)
    if not snap or not snap.next:
        return {"outcome": "error", "error": "该 lead 没有待审批的暂停点"}
    result = graph.invoke(Command(resume=decision), config)
    snap = graph.get_state(config)
    values = dict(snap.values) if snap and snap.values else result
    return values


def graph_status(graph: Any, lead_id: int) -> dict[str, Any]:
    snap = graph.get_state(_thread_config(lead_id))
    if not snap or not snap.values:
        return {"exists": False}
    values = dict(snap.values)
    return {
        "exists": True,
        "next": list(snap.next or []),
        "outcome": values.get("outcome"),
        "retry_count": values.get("retry_count"),
        "qa_passed": values.get("qa_passed"),
        "qa_issues": values.get("qa_issues") or [],
        "match_score": (values.get("match_verdict") or {}).get("score"),
        "has_draft": bool(values.get("draft")),
    }
