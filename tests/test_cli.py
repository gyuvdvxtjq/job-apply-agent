# -*- coding: utf-8 -*-
"""CLI 端到端回归：add → draft → qa → send 闸门与每日限频。

不触网：Mailer 用 FakeMailer 替换；profile/config 均写入 tmp_path。
"""
from __future__ import annotations

from pathlib import Path

import yaml

import cli
from store import JobLeads, SentLog


def make_config(tmp_path, **pipeline_extra) -> Path:
    cfg = {
        "profile_path": "./profile.yaml",
        "pipeline": {"auto_send": False, "require_source_url": False, **pipeline_extra},
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return p


def make_profile(tmp_path) -> Path:
    profile = {
        "schema_version": 1,
        "identity": {"name": "测试同学", "phone": "", "email": "", "github": ""},
        "education": [
            {"school": "测试大学", "major": "计算机", "degree": "", "grade_or_grad_year": ""}
        ],
        "skills": ["Python", "SQL"],
        "directions": ["数据分析"],
        "highlights": [
            {"title": "测试项目", "skills": ["Python"], "metrics": [], "blurb": "完成一个测试项目"}
        ],
        "constraints": {
            "cities": ["测试市"],
            "available_from": "",
            "available_duration": "",
            "exclude_companies": [],
            "exclude_keywords": [],
        },
        "raw_text_excerpt": "",
    }
    p = tmp_path / "profile.yaml"
    p.write_text(yaml.safe_dump(profile, allow_unicode=True), encoding="utf-8")
    return p


class FakeMailer:
    sent: list[str] = []

    def __init__(self, config_path=None, cfg=None):
        pass

    def set_user_name(self, name):
        pass

    def send(self, to_email, company, job_title, body_text, subject=None):
        FakeMailer.sent.append(to_email)
        return True


def test_full_pipeline_add_draft_qa(tmp_path):
    cfg = make_config(tmp_path)
    make_profile(tmp_path)
    data_dir = tmp_path / "data"
    assert cli.main([
        "--config", str(cfg), "add", "--data-dir", str(data_dir),
        "--company", "测试公司", "--job", "数据分析实习生",
        "--email", "hr@test.com", "--jd", "需要 Python 与 SQL",
    ]) == 0
    assert cli.main(["--config", str(cfg), "draft", "--data-dir", str(data_dir)]) == 0
    lead = JobLeads(data_dir).get(1)
    assert lead["status"] == "ready"
    assert "测试同学" in lead["body"]
    assert lead["match_score"] is not None
    assert cli.main(["--config", str(cfg), "qa", "--data-dir", str(data_dir)]) == 0
    assert JobLeads(data_dir).get(1)["status"] == "ready"


def test_qa_skips_invalid_email(tmp_path):
    cfg = make_config(tmp_path)
    make_profile(tmp_path)
    data_dir = tmp_path / "data"
    JobLeads(data_dir).add(company="坏邮箱公司", job_title="x", contact_email="not-an-email")
    assert cli.main(["--config", str(cfg), "qa", "--data-dir", str(data_dir)]) == 0
    assert JobLeads(data_dir).get(1)["status"] == "skipped"


def test_send_requires_confirm(tmp_path):
    cfg = make_config(tmp_path)
    make_profile(tmp_path)
    data_dir = tmp_path / "data"
    JobLeads(data_dir).add(company="A", job_title="B", contact_email="a@b.com", body="x" * 100)
    rc = cli.main(["--config", str(cfg), "send", "--data-dir", str(data_dir), "--id", "1"])
    assert rc == 2


def test_daily_cap_status(tmp_path):
    log = SentLog(tmp_path / "d")
    assert cli.daily_cap_status({"pipeline": {"max_emails_per_day": 3}}, log) == (False, 0, 3)
    log.add("a@b.com", "A", "B")
    assert cli.daily_cap_status({"pipeline": {"max_emails_per_day": 1}}, log)[0] is True
    # 未配置上限 → 不设限
    assert cli.daily_cap_status({}, log)[0] is False


def test_send_success_with_fake_mailer(tmp_path, monkeypatch):
    cfg = make_config(tmp_path, max_emails_per_day=5)
    data_dir = tmp_path / "data"
    JobLeads(data_dir).add(company="A", job_title="B", contact_email="a@b.com", body="x" * 100)
    monkeypatch.setattr(cli, "Mailer", FakeMailer)
    FakeMailer.sent = []
    rc = cli.main([
        "--config", str(cfg), "send", "--data-dir", str(data_dir), "--id", "1", "--confirm",
    ])
    assert rc == 0
    assert FakeMailer.sent == ["a@b.com"]
    assert JobLeads(data_dir).get(1)["status"] == "sent"


def test_send_all_respects_daily_cap(tmp_path, monkeypatch):
    cfg = make_config(tmp_path, max_emails_per_day=1, send_interval_seconds=0)
    data_dir = tmp_path / "data"
    leads = JobLeads(data_dir)
    leads.add(company="A", job_title="B", contact_email="a@test.com", body="x" * 100)
    leads.add(company="C", job_title="D", contact_email="c@test.com", body="y" * 100)
    SentLog(data_dir).add("used@test.com", "P", "J")  # 今日额度已用尽
    monkeypatch.setattr(cli, "Mailer", FakeMailer)
    FakeMailer.sent = []
    rc = cli.main([
        "--config", str(cfg), "send-all", "--data-dir", str(data_dir), "--confirm",
    ])
    assert rc == 2
    assert FakeMailer.sent == []
    assert JobLeads(data_dir).get(1)["status"] == "ready"


def test_send_all_partial_quota(tmp_path, monkeypatch):
    cfg = make_config(tmp_path, max_emails_per_day=2, send_interval_seconds=0)
    data_dir = tmp_path / "data"
    leads = JobLeads(data_dir)
    leads.add(company="A", job_title="B", contact_email="a@test.com", body="x" * 100)
    leads.add(company="C", job_title="D", contact_email="c@test.com", body="y" * 100)
    SentLog(data_dir).add("used@test.com", "P", "J")  # 已发 1 封，剩 1 封额度
    monkeypatch.setattr(cli, "Mailer", FakeMailer)
    FakeMailer.sent = []
    rc = cli.main([
        "--config", str(cfg), "send-all", "--data-dir", str(data_dir), "--confirm",
    ])
    assert rc == 0
    assert FakeMailer.sent == ["a@test.com"]
    assert JobLeads(data_dir).get(1)["status"] == "sent"
    assert JobLeads(data_dir).get(2)["status"] == "ready"


def test_collect_from_imports_demo_csv(tmp_path):
    from collect import collect_from_imports

    csv_path = Path(__file__).resolve().parents[1] / "examples" / "demo" / "sample_import.csv"
    data_dir = tmp_path / "data"
    leads, sent = JobLeads(data_dir), SentLog(data_dir)
    n = collect_from_imports([str(csv_path)], {}, leads, sent)
    assert n == 2
    assert leads.get(1)["company"] == "示例科技"
    # 重复导入按邮箱去重
    n2 = collect_from_imports([str(csv_path)], {}, leads, sent)
    assert n2 == 0


def _fake_llm_client(content: str | Exception):
    """构造可注入 cli 的假 LLMClient（函数内延迟导入从 llm 模块取符号）。"""
    from llm import LLMResponse, Usage

    class FakeClient:
        def __init__(self, cfg=None, **kw):
            pass

        def chat(self, messages, **kw):
            if isinstance(content, Exception):
                raise content
            return LLMResponse(
                content=content, model="fake", usage=Usage(5, 5, 10), latency_ms=1
            )

    return FakeClient


GOOD_EXTRACT = (
    '{"company":"示例科技","job_title":"Python实习生","cities":["深圳"],'
    '"education_requirement":"本科","tech_stack":["Python","RAG"],'
    '"deadline":"2026-12-01","apply_method":"hr@a.com"}'
)


def test_extract_jd_command(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    make_profile(tmp_path)
    data_dir = tmp_path / "data"
    JobLeads(data_dir).add(
        company="", job_title="", contact_email="a@b.com",
        jd_summary="深圳 示例科技 招 Python 实习生，本科，会 RAG，投递 hr@a.com，截止 2026-12-01",
    )
    monkeypatch.setattr("llm.LLMClient", _fake_llm_client(GOOD_EXTRACT))
    rc = cli.main(["--config", str(cfg), "extract-jd", "--data-dir", str(data_dir)])
    assert rc == 0
    lead = JobLeads(data_dir).get(1)
    assert lead["jd_info"]["cities"] == ["深圳"]
    assert lead["jd_info"]["deadline"] == "2026-12-01"

    # 已抽取 → 跳过；--force 重新抽取
    assert cli.main(["--config", str(cfg), "extract-jd", "--data-dir", str(data_dir)]) == 0
    assert cli.main([
        "--config", str(cfg), "extract-jd", "--data-dir", str(data_dir), "--force",
    ]) == 0


def test_extract_jd_command_api_failure(tmp_path, monkeypatch):
    from llm import LLMError

    cfg = make_config(tmp_path)
    make_profile(tmp_path)
    data_dir = tmp_path / "data"
    JobLeads(data_dir).add(
        company="", job_title="", contact_email="a@b.com", jd_summary="某 JD 文本",
    )
    monkeypatch.setattr(
        "llm.LLMClient", _fake_llm_client(LLMError("网络错误"))
    )
    rc = cli.main(["--config", str(cfg), "extract-jd", "--data-dir", str(data_dir)])
    assert rc == 1
    lead = JobLeads(data_dir).get(1)
    assert "jd_info" not in lead
    assert "网络错误" in lead["jd_info_error"]


def test_graph_cli_run_status_resume(tmp_path, monkeypatch):
    import test_graph as tg

    cfg = make_config(tmp_path)
    make_profile(tmp_path)
    data_dir = tmp_path / "data"
    JobLeads(data_dir).add(
        company="甲公司", job_title="大模型应用实习生", contact_email="hr@a.com",
        jd_summary="深圳 甲公司 招大模型应用实习生：负责 RAG 检索增强；要求熟悉 Python，本科。",
        source_url="https://example-a.com/jobs/1",
    )
    monkeypatch.setattr("llm.LLMClient", lambda cfg=None, **kw: tg.ScriptedLLM({
        "jd_extract": [tg.GOOD_EXTRACT],
        "match_score": [tg.MATCH_HIGH],
        "draft_cover_letter": [tg.DRAFT],
        "qa_cover_letter": [tg.QA_PASS],
    }))
    monkeypatch.setattr(cli, "_build_default_retriever", lambda cfg: tg.FakeRetriever())

    rc = cli.main(["--config", str(cfg), "graph", "run", "--lead", "1", "--data-dir", str(data_dir)])
    assert rc == 0
    assert JobLeads(data_dir).get(1)["status"] == "reviewing"

    rc = cli.main(["--config", str(cfg), "graph", "status", "--lead", "1", "--data-dir", str(data_dir)])
    assert rc == 0

    rc = cli.main([
        "--config", str(cfg), "graph", "resume", "--lead", "1", "--approve", "--data-dir", str(data_dir),
    ])
    assert rc == 0
    assert JobLeads(data_dir).get(1)["status"] == "ready"
