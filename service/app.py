# -*- coding: utf-8 -*-
"""JobMatch-Agent FastAPI 服务。

端点：
- GET  /health    健康检查（含向量库规模）
- POST /search    自然语言检索 {query, top_k, mode, rerank}
- POST /match     简历画像 × JD → LLM 匹配裁决 {job_text, profile_path?}
- POST /generate  SSE 流式生成求职信 {company, job_title, jd_text}

安全边界：**不提供任何发送/审批端点**——投递审批只存在于 CLI 的人工闸门
（tools/graph.py interrupt），Web 层不可触达。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from common import repo_root

load_dotenv(repo_root() / ".env", override=False)

_DEFAULT_PROFILE = repo_root() / "examples" / "demo" / "profile.yaml"


class SearchReq(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    mode: Literal["hybrid", "vector", "bm25"] = "hybrid"
    rerank: bool | None = None


class MatchReq(BaseModel):
    job_text: str
    profile_path: str = ""


class GenerateReq(BaseModel):
    company: str = ""
    job_title: str = ""
    jd_text: str
    profile_path: str = ""


def create_app(
    retriever_builder: Callable[[], Any] | None = None,
    llm_builder: Callable[[], Any] | None = None,
) -> FastAPI:
    app = FastAPI(title="JobMatch-Agent", version="0.2.0")
    state: dict[str, Any] = {}

    def get_retriever() -> Any:
        if "retriever" not in state:
            from cli import _build_default_retriever  # 复用 CLI 的装配逻辑
            from config_loader import load_config

            state["retriever"] = (
                retriever_builder() if retriever_builder
                else _build_default_retriever(load_config())
            )
        return state["retriever"]

    def get_llm() -> Any:
        if "llm" not in state:
            from llm import LLMClient
            from config_loader import load_config

            state["llm"] = llm_builder() if llm_builder else LLMClient(cfg=dict(load_config().get("llm") or {}))
        return state["llm"]

    def load_profile(profile_path: str) -> dict:
        path = Path(profile_path) if profile_path else _DEFAULT_PROFILE
        if not path.is_absolute():
            path = repo_root() / path
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"profile 不存在: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @app.get("/health")
    def health() -> dict:
        info: dict[str, Any] = {"status": "ok", "version": "0.2.0"}
        try:
            info["chunks_indexed"] = get_retriever().store.count()
        except Exception as e:  # 未 ingest 时也能报告
            info["chunks_indexed"] = None
            info["retriever_note"] = str(e)[:120]
        return info

    @app.post("/search")
    def search(req: SearchReq) -> dict:
        try:
            hits = get_retriever().search(
                req.query, top_k=req.top_k, mode=req.mode, rerank=req.rerank
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"query": req.query, "results": hits}

    @app.post("/match")
    def match(req: MatchReq) -> dict:
        from match import match_score
        from match_llm import match_lead_with_llm

        profile = load_profile(req.profile_path)
        if not req.job_text.strip():
            raise HTTPException(status_code=400, detail="job_text 不能为空")
        lexical = match_score(profile, req.job_text)["score"]
        verdict, stats = match_lead_with_llm(profile, req.job_text, get_llm(), lexical_score=lexical)
        if verdict is None:
            raise HTTPException(status_code=502, detail=f"匹配评分失败: {stats['errors'][-1:]}")
        return {"verdict": verdict.model_dump(), "lexical_score": lexical, "attempts": stats["attempts"]}

    @app.post("/generate")
    def generate(req: GenerateReq) -> StreamingResponse:
        from draft_llm import draft_cover_letter_llm  # 校验 profile 存在

        profile = load_profile(req.profile_path)
        if not req.jd_text.strip():
            raise HTTPException(status_code=400, detail="jd_text 不能为空")
        llm = get_llm()
        lead = {
            "company": req.company,
            "job_title": req.job_title,
            "jd_summary": req.jd_text,
            "source_url": "",
        }

        def event_stream() -> Iterator[str]:
            # 复用 draft_llm 的提示词构造，但走流式；证据约束不变
            from draft_llm import DRAFT_SYSTEM_PROMPT

            hl_lines = "\n".join(
                f"- {h.get('title', '')}：{h.get('blurb', '')}"
                for h in (profile.get("highlights") or [])[:6]
            ) or "（无）"
            user = (
                f"【申请信息】\n公司: {req.company or '贵司'}\n岗位: {req.job_title or '实习生'}\n\n"
                f"【项目经历（证据只能来自这里）】\n{hl_lines}\n\n"
                f"【岗位 JD 要点】\n{req.jd_text[:2000]}"
            )
            try:
                for delta in llm.chat_stream(
                    [
                        {"role": "system", "content": DRAFT_SYSTEM_PROMPT},
                        {"role": "user", "content": user},
                    ],
                    purpose="svc_generate",
                    temperature=0.4,
                ):
                    yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
            except Exception as e:  # 流中断也要告诉客户端
                yield f"data: {json.dumps({'error': str(e)[:200]})}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
