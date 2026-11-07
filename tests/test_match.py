# -*- coding: utf-8 -*-
from match import is_excluded_company, match_score

PROFILE = {
    "skills": ["Python", "SQL"],
    "directions": ["数据分析"],
    "highlights": [
        {"title": "数据项目", "skills": ["Python"], "metrics": ["1万条"], "blurb": "完成数据清洗与看板"}
    ],
    "constraints": {"exclude_keywords": ["外包"], "exclude_companies": ["某某大厂"]},
}


def test_score_basic_range_and_skills():
    m = match_score(PROFILE, "数据分析实习生，要求 Python、SQL")
    assert 0.0 <= m["score"] <= 1.0
    assert "Python" in m["matched_skills"]


def test_score_nonnegative_on_empty_jd():
    m = match_score(PROFILE, "")
    assert m["score"] >= 0


def test_exclude_keyword_caps_score():
    m = match_score(PROFILE, "数据分析 外包岗位")
    assert m["score"] <= 0.2


def test_is_excluded_company():
    assert is_excluded_company(PROFILE, "某某大厂招聘")
    assert not is_excluded_company(PROFILE, "其他公司")
