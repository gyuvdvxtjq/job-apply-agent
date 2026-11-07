# -*- coding: utf-8 -*-
from chunker import chunk_jd

SAMPLE = """岗位职责：
1. 参与 RAG 检索增强系统的搭建与调优；
2. 开发基于 LLM 的 Agent 工作流。
任职要求：
1. 本科及以上学历；
2. 熟悉 Python。
其他：
工作地点深圳，简历投递至 hr@example.com。"""


def test_sections_split_by_headers():
    chunks = chunk_jd(SAMPLE, job_id="j1")
    sections = [c["section"] for c in chunks]
    assert sections[0] == "职责"
    assert "要求" in sections
    assert "其他" in sections
    assert all(c["job_id"] == "j1" for c in chunks)
    assert chunks[0]["chunk_id"] == "j1::职责::0"
    assert "RAG" in chunks[0]["text"]


def test_decorative_headers_detected():
    text = "【岗位职责】\n负责数据清洗。\n一、任职要求\n本科在读。"
    chunks = chunk_jd(text, job_id="j2")
    assert [c["section"] for c in chunks] == ["职责", "要求"]


def test_no_headers_single_other_chunk():
    text = "这是一个没有任何标题的短 JD。"
    chunks = chunk_jd(text, job_id="j3")
    assert len(chunks) == 1
    assert chunks[0]["section"] == "其他"


def test_long_section_split_by_sentences():
    body = "。".join(f"第{i}句话描述工作内容" for i in range(80)) + "。"
    text = "岗位职责：\n" + body
    chunks = chunk_jd(text, job_id="j4", max_chars=200)
    assert len(chunks) >= 2
    assert all(c["section"] == "职责" for c in chunks)
    assert all(len(c["text"]) <= 500 for c in chunks)


def test_empty_text_returns_empty():
    assert chunk_jd("", job_id="j5") == []
    assert chunk_jd("   \n  ", job_id="j5") == []


def test_adjacent_same_buckets_merged():
    text = "岗位职责：\n做A。\n工作内容：\n做B。\n任职要求：\n会C。"
    chunks = chunk_jd(text, job_id="j6")
    duty_chunks = [c for c in chunks if c["section"] == "职责"]
    assert len(duty_chunks) == 1
    assert "做A" in duty_chunks[0]["text"] and "做B" in duty_chunks[0]["text"]
