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
