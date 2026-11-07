# -*- coding: utf-8 -*-
from extract import (
    domain_from_url,
    email_domain,
    extract_emails_from_text,
    extract_emails_with_context,
    looks_like_public_mail_provider,
    score_email_for_job,
)


def test_extract_basic_and_dedupe():
    text = "投递邮箱 hr@example.com，简历投递 hr@example.com 或 campus@example.com"
    emails = extract_emails_from_text(text)
    assert emails == ["hr@example.com", "campus@example.com"]


def test_recruiting_context_flag():
    out = extract_emails_with_context("招聘联系人 hr@corp.com")
    assert out[0]["has_recruiting_context"] is True
    out2 = extract_emails_with_context("random a@b.io nothing here")
    assert out2[0]["has_recruiting_context"] is False


def test_score_prefers_campus_local_part():
    s = score_email_for_job("campus@corp.com.cn", source_url="https://www.corp.com.cn/jobs")
    assert s > 0.7
    assert looks_like_public_mail_provider("x@qq.com")


def test_domain_helpers():
    assert domain_from_url("https://www.corp.com.cn/jobs") == "corp.com.cn"
    assert email_domain("a@B.com") == "b.com"
