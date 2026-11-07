# -*- coding: utf-8 -*-
from store import JobLeads, SentLog


def test_add_defaults_pending(tmp_path):
    leads = JobLeads(tmp_path / "d")
    lid = leads.add(company="A", job_title="B", contact_email="hr@a.com")
    lead = leads.get(lid)
    assert lead["status"] == "pending"
    assert lead["match_score"] is None


def test_body_moves_to_ready(tmp_path):
    leads = JobLeads(tmp_path / "d")
    lid = leads.add(company="A", job_title="B", contact_email="hr@a.com")
    assert leads.set_body(lid, "正文" * 50)
    assert leads.get(lid)["status"] == "ready"


def test_mark_failed_and_counts(tmp_path):
    leads = JobLeads(tmp_path / "d")
    lid = leads.add(company="A", job_title="B", contact_email="hr@a.com")
    leads.mark_failed(lid, "smtp failed")
    assert leads.count_by_status()["failed"] == 1
    assert leads.get(lid)["error"] == "smtp failed"


def test_persistence_across_instances(tmp_path):
    d = tmp_path / "d"
    lid = JobLeads(d).add(company="A", job_title="B", contact_email="hr@a.com")
    assert JobLeads(d).get(lid)["company"] == "A"


def test_find_by_email_case_insensitive(tmp_path):
    leads = JobLeads(tmp_path / "d")
    leads.add(company="A", job_title="B", contact_email="HR@Company.com")
    assert leads.find_by_email("hr@company.com")


def test_sent_log_count_today(tmp_path):
    log = SentLog(tmp_path / "d")
    assert log.count_today() == 0
    log.add("a@b.com", "A", "B")
    assert log.count_today() == 1
    assert log.is_sent("A@B.com")
