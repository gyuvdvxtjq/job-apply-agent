# -*- coding: utf-8 -*-
"""LangGraph 流水线测试：脚本化 LLM + 假检索器 + 真 SQLite checkpointer，全离线。"""
from __future__ import annotations

import json

from graph import (
    build_pipeline,
    default_graph_cfg,
    graph_status,
    make_checkpointer,
    resume_lead,
    run_lead,
)
from llm import LLMResponse, Usage
from store import JobLeads

GOOD_EXTRACT = json.dumps({
    "company": "甲公司", "job_title": "大模型应用实习生", "cities": ["深圳"],
    "education_requirement": "本科", "tech_stack": ["Python", "RAG"],
    "deadline": "", "apply_method": "hr@a.com",
}, ensure_ascii=False)

MATCH_HIGH = json.dumps({
    "score": 0.8, "reasons": ["技能匹配：Python/RAG", "方向一致"],
    "evidence_quotes": ["熟悉 Python"], "hard_gaps": [],
}, ensure_ascii=False)
MATCH_LOW = json.dumps({
    "score": 0.2, "reasons": ["方向不符"], "evidence_quotes": [], "hard_gaps": ["无 RAG 经历"],
}, ensure_ascii=False)

DRAFT = (
    "甲公司招聘负责人您好：\n\n"
    "我是测试大学计算机专业的测试同学，在贵司招聘页面看到大模型应用实习生岗位，特此投递。\n"
    "JD 中要求熟悉 Python 与 RAG 检索，我曾完成一个检索增强项目：搭建了向量检索链路并优化召回，"
    "与岗位要求直接对应。\n我可在近期到岗，实习周期 3-6 个月。\n\n"
    "简历见附件，感谢阅读。\n\n测试同学"
)
DRAFT_2 = DRAFT + "\n（第二稿：已补充对 JD 第二条要求的呼应。）"

QA_PASS = json.dumps({"passed": True, "issues": [], "severity": "low"}, ensure_ascii=False)
QA_FAIL = json.dumps({
    "passed": False, "issues": ["空话套话: 第二段缺乏具体证据"], "severity": "high",
}, ensure_ascii=False)


class ScriptedLLM:
    """按 purpose 出队回复；记录每次调用的 messages 快照。"""

    def __init__(self, script: dict[str, list[str]]):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: dict[str, list[list[dict]]] = {}

    def chat(self, messages, purpose="", json_mode=False, **kw):
        self.calls.setdefault(purpose, []).append([dict(m) for m in messages])
        content = self.script.get(purpose, ["{}"]).pop(0)
        return LLMResponse(content=content, model="fake", usage=Usage(1, 1, 2), latency_ms=0)


class FakeRetriever:
    def search(self, query, top_k=5, mode="hybrid", rerank=None):
        return [
            {
                "chunk_id": "demo::职责::0", "job_id": "demo", "section": "职责",
                "text": "参与 RAG 检索增强系统的搭建与调优",
                "company": "甲公司", "job_title": "大模型应用实习生", "city": "深圳",
                "rrf_score": 0.05,
            }
        ][:top_k]


def make_profile() -> dict:
    return {
        "identity": {"name": "测试同学", "phone": "13800000000", "email": "", "github": ""},
        "education": [{"school": "测试大学", "major": "计算机", "degree": "本科", "grade_or_grad_year": ""}],
        "skills": ["Python", "RAG"],
        "directions": ["AI Agent"],
        "highlights": [
            {"title": "检索增强项目", "skills": ["Python"], "metrics": [], "blurb": "搭建向量检索链路并优化召回"}
        ],
        "constraints": {"cities": ["深圳"], "available_from": "近期", "available_duration": "3-6 个月",
                        "exclude_companies": [], "exclude_keywords": []},
        "raw_text_excerpt": "",
    }


def make_leads(tmp_path) -> JobLeads:
    leads = JobLeads(tmp_path / "data")
    leads.add(
        company="甲公司", job_title="大模型应用实习生", contact_email="hr@a.com",
        jd_summary="深圳 甲公司 招大模型应用实习生：负责 RAG 检索增强系统；要求熟悉 Python，本科。",
        source_url="https://example-a.com/jobs/1",
    )
    return leads


def build(cfg_extra=None, checkpointer_db=None):
    cfg = {"graph": cfg_extra or {}}
    return cfg


def test_happy_path_runs_to_approval_gate_and_resume(tmp_path):
    leads = make_leads(tmp_path)
    llm = ScriptedLLM({
        "jd_extract": [GOOD_EXTRACT],
        "match_score": [MATCH_HIGH],
        "draft_cover_letter": [DRAFT],
        "qa_cover_letter": [QA_PASS],
    })
    graph = build_pipeline(
        build(), llm, FakeRetriever(), leads,
        checkpointer=make_checkpointer(tmp_path / "state.db"),
    )
    values = run_lead(graph, leads, 1, make_profile())
    assert values["outcome"] == "awaiting_approval"
    assert values["qa_passed"] is True
    st = graph_status(graph, 1)
    assert st["next"] == ["approve"]
    lead = leads.get(1)
    assert lead["status"] == "reviewing"
    assert lead["body"] == DRAFT
    assert lead["jd_info"]["cities"] == ["深圳"]
    assert lead["match_score"] == 0.8

    # 人工批准 → ready
    values = resume_lead(graph, leads, 1, {"action": "approve"})
    assert values["outcome"] == "approved"
    assert leads.get(1)["status"] == "ready"


def test_qa_failure_triggers_rewrite_with_instructions(tmp_path):
    leads = make_leads(tmp_path)
    llm = ScriptedLLM({
        "jd_extract": [GOOD_EXTRACT],
        "match_score": [MATCH_HIGH],
        "draft_cover_letter": [DRAFT, DRAFT_2],
        "qa_cover_letter": [QA_FAIL, QA_PASS],
    })
    graph = build_pipeline(
        build(), llm, FakeRetriever(), leads,
        checkpointer=make_checkpointer(tmp_path / "state.db"),
    )
    values = run_lead(graph, leads, 1, make_profile())
    assert values["outcome"] == "awaiting_approval"
    assert values["retry_count"] == 2
    # 第二稿写入 store；第二次 draft 调用带上了质检修改指令
    assert leads.get(1)["body"] == DRAFT_2
    second_call = llm.calls["draft_cover_letter"][1]
    assert "质检" in second_call[-1]["content"]


def test_qa_exhausted_still_goes_to_human_gate(tmp_path):
    leads = make_leads(tmp_path)
    llm = ScriptedLLM({
        "jd_extract": [GOOD_EXTRACT],
        "match_score": [MATCH_HIGH],
        "draft_cover_letter": [DRAFT, DRAFT],
        "qa_cover_letter": [QA_FAIL, QA_FAIL],
    })
    graph = build_pipeline(
        build({"max_retries": 1}), llm, FakeRetriever(), leads,
        checkpointer=make_checkpointer(tmp_path / "state.db"),
    )
    values = run_lead(graph, leads, 1, make_profile())
    assert values["outcome"] == "awaiting_approval"
    assert values["qa_passed"] is False
    assert len(values["qa_issues"]) >= 1
    # 人工可强制通过（质检提意见、人做决定）
    values = resume_lead(graph, leads, 1, {"action": "approve"})
    assert values["outcome"] == "approved"
    lead = leads.get(1)
    assert lead["status"] == "ready"
    assert "人工强制通过" in lead["error"]


def test_low_match_skips_without_gate(tmp_path):
    leads = make_leads(tmp_path)
    llm = ScriptedLLM({
        "jd_extract": [GOOD_EXTRACT],
        "match_score": [MATCH_LOW],
    })
    graph = build_pipeline(
        build({"min_match_score": 0.5}), llm, FakeRetriever(), leads,
        checkpointer=make_checkpointer(tmp_path / "state.db"),
    )
    values = run_lead(graph, leads, 1, make_profile())
    assert values["outcome"] == "low_match"
    lead = leads.get(1)
    assert lead["status"] == "skipped"
    assert "匹配分低" in lead["error"]
    # 没有暂停点可恢复
    values = resume_lead(graph, leads, 1, {"action": "approve"})
    assert values["outcome"] == "error"


def test_reject_marks_skipped(tmp_path):
    leads = make_leads(tmp_path)
    llm = ScriptedLLM({
        "jd_extract": [GOOD_EXTRACT],
        "match_score": [MATCH_HIGH],
        "draft_cover_letter": [DRAFT],
        "qa_cover_letter": [QA_PASS],
    })
    graph = build_pipeline(
        build(), llm, FakeRetriever(), leads,
        checkpointer=make_checkpointer(tmp_path / "state.db"),
    )
    run_lead(graph, leads, 1, make_profile())
    values = resume_lead(graph, leads, 1, {"action": "reject", "reason": "城市不符"})
    assert values["outcome"] == "rejected"
    lead = leads.get(1)
    assert lead["status"] == "skipped"
    assert "城市不符" in lead["error"]


def test_state_survives_new_graph_instance(tmp_path):
    """中断恢复：换一个图实例（模拟进程重启）后仍能从闸门继续。"""
    leads = make_leads(tmp_path)
    db = tmp_path / "state.db"
    llm = ScriptedLLM({
        "jd_extract": [GOOD_EXTRACT],
        "match_score": [MATCH_HIGH],
        "draft_cover_letter": [DRAFT],
        "qa_cover_letter": [QA_PASS],
    })
    graph1 = build_pipeline(build(), llm, FakeRetriever(), leads, checkpointer=make_checkpointer(db))
    run_lead(graph1, leads, 1, make_profile())
    del graph1

    graph2 = build_pipeline(build(), llm, FakeRetriever(), leads, checkpointer=make_checkpointer(db))
    st = graph_status(graph2, 1)
    assert st["next"] == ["approve"]
    values = resume_lead(graph2, leads, 1, {"action": "approve"})
    assert values["outcome"] == "approved"
    assert leads.get(1)["status"] == "ready"


def test_extract_llm_failure_does_not_crash_pipeline(tmp_path):
    leads = make_leads(tmp_path)
    llm = ScriptedLLM({
        "jd_extract": ["不是JSON", "还不是JSON", "依然不是"],
        "match_score": [MATCH_HIGH],
        "draft_cover_letter": [DRAFT],
        "qa_cover_letter": [QA_PASS],
    })
    graph = build_pipeline(
        build(), llm, FakeRetriever(), leads,
        checkpointer=make_checkpointer(tmp_path / "state.db"),
    )
    values = run_lead(graph, leads, 1, make_profile())
    # 抽取失败不阻断：jd_info 为空但流程继续到审批闸门
    assert values["outcome"] == "awaiting_approval"
    assert values["jd_extract_ok"] is False
    assert leads.get(1)["jd_info"] is None
