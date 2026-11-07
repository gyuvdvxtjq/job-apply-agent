# -*- coding: utf-8 -*-
"""
job-apply-agent CLI

子命令:
  parse-resume  PDF → profile.yaml
  plan          生成 runs/plan.json
  collect       导入/URL 采集（L0 搜索由 Skill 做）
  draft         为 pending 线索生成求职信骨架 → ready
  qa            验收过滤
  status/list/add/set-body
  send / send-all   显式发送（默认需 --confirm）
  export        Markdown 报告
  health        源健康检查
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# tools/ as sys.path root when executed as python tools/cli.py
_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from common import ensure_utf8_stdio, repo_root, write_text
from config_loader import load_config, resolve_path
from draft import build_cover_letter
from mailer import Mailer
from match import match_score
from profile_io import apply_overrides, load_profile, profile_summary, validate_profile
from registry import SourceRegistry
from store import JobLeads, SentLog


STATUS_EMOJI = {
    "pending": "⏳",
    "ready": "📝",
    "sent": "✅",
    "failed": "❌",
    "skipped": "⏭",
}


def cmd_parse_resume(args):
    from parse_resume import parse_resume
    cfg = None
    out = args.out
    if not out:
        try:
            cfg = load_config(args.config)
            out = str(resolve_path(cfg, cfg.get("profile_path") or "profile.yaml"))
        except Exception:
            out = "profile.yaml"
    parse_resume(args.pdf, out)
    return 0


def cmd_plan(args):
    from plan import main as plan_main
    argv = []
    if args.config:
        argv += ["--config", args.config]
    if args.run_profile:
        argv += ["--run-profile", args.run_profile]
    if args.out:
        argv += ["--out", args.out]
    return plan_main(argv)


def cmd_collect(args):
    from collect import main as collect_main
    argv = []
    if args.config:
        argv += ["--config", args.config]
    if args.plan:
        argv += ["--plan", args.plan]
    for u in args.url or []:
        argv += ["--url", u]
    return collect_main(argv)


def cmd_draft(args):
    cfg = load_config(args.config)
    profile_path = resolve_path(cfg, cfg.get("profile_path") or "profile.yaml")
    profile = apply_overrides(load_profile(profile_path), cfg.get("user_overrides"))
    leads = JobLeads(resolve_path(cfg, args.data_dir))
    targets = leads.list("pending")
    if args.id:
        one = leads.get(args.id)
        targets = [one] if one else []
    n = 0
    for lead in targets:
        if not lead:
            continue
        body = build_cover_letter(
            profile,
            company=lead.get("company") or "",
            job_title=lead.get("job_title") or "",
            jd_summary=lead.get("jd_summary") or "",
            source_hint=lead.get("source_url") or "",
        )
        m = match_score(profile, f"{lead.get('job_title')}\n{lead.get('jd_summary')}")
        leads.set_body(lead["id"], body)
        leads.update_field(lead["id"], "match_score", m["score"])
        print(f"📝 #{lead['id']} → ready (score={m['score']})")
        n += 1
    print(f"✅ 生成 {n} 封求职信骨架。请审查后 send。")
    return 0


def cmd_qa(args):
    from qa import main as qa_main
    argv = []
    if args.config:
        argv += ["--config", args.config]
    if args.data_dir:
        argv += ["--data-dir", args.data_dir]
    return qa_main(argv)


def cmd_status(args):
    cfg = load_config(args.config)
    data_dir = resolve_path(cfg, args.data_dir)
    leads = JobLeads(data_dir)
    sent = SentLog(data_dir)
    counts = leads.count_by_status()
    total = sum(counts.values())
    print(
        f"📊 线索 {total} "
        f"(pending:{counts.get('pending',0)}, ready:{counts.get('ready',0)}, "
        f"sent:{counts.get('sent',0)}, failed:{counts.get('failed',0)}, "
        f"skipped:{counts.get('skipped',0)}) | 发送日志 {sent.count()}"
    )
    # profile summary if exists
    try:
        pp = resolve_path(cfg, cfg.get("profile_path") or "profile.yaml")
        if pp.exists():
            print(f"👤 {profile_summary(apply_overrides(load_profile(pp), cfg.get('user_overrides')))}")
    except Exception:
        pass
    return 0


def cmd_list(args):
    cfg = load_config(args.config)
    leads = JobLeads(resolve_path(cfg, args.data_dir))
    items = leads.list(args.status)
    print(f"{'ID':>4} | {'状态':^8} | {'公司':<16} | {'岗位':<18} | 邮箱")
    print("-" * 90)
    for x in items:
        st = x.get("status") or ""
        em = STATUS_EMOJI.get(st, "")
        print(
            f"{x.get('id', 0):>4} | {em}{st:<6} | "
            f"{(x.get('company') or '')[:16]:<16} | "
            f"{(x.get('job_title') or '')[:18]:<18} | "
            f"{x.get('contact_email') or ''}"
        )
    print(f"\n共 {len(items)} 条")
    return 0


def cmd_add(args):
    cfg = load_config(args.config)
    leads = JobLeads(resolve_path(cfg, args.data_dir))
    lid = leads.add(
        company=args.company,
        job_title=args.job,
        contact_email=args.email,
        jd_summary=args.jd or "",
        source_url=args.source or "",
        body=args.body or "",
        source_type=args.source_type or "manual",
    )
    print(f"✅ 添加线索 #{lid}: {args.company} - {args.job}")
    return 0


def cmd_set_body(args):
    cfg = load_config(args.config)
    leads = JobLeads(resolve_path(cfg, args.data_dir))
    if not leads.set_body(args.id, args.body):
        print(f"❌ 未找到 #{args.id}")
        return 1
    print(f"✅ #{args.id} 已更新 body → ready")
    return 0


def daily_cap_status(cfg: dict, sent_log: SentLog) -> tuple[bool, int, int]:
    """每日发送限频。返回 (是否已超限, 今日已发, 每日上限)。cap<=0 视为不设限。"""
    cap = int((cfg.get("pipeline") or {}).get("max_emails_per_day") or 0)
    used = sent_log.count_today()
    return (cap > 0 and used >= cap), used, cap


def cmd_send(args):
    if not args.confirm:
        print("❌ 发送需显式 --confirm（默认只准备 ready，不自动发）")
        return 2
    cfg = load_config(args.config)
    data_dir = resolve_path(cfg, args.data_dir)
    leads = JobLeads(data_dir)
    sent_log = SentLog(data_dir)
    lead = leads.get(args.id)
    if not lead:
        print(f"❌ 未找到 #{args.id}")
        return 1
    if args.body:
        leads.set_body(args.id, args.body)
        lead = leads.get(args.id)
    if not lead.get("body"):
        print("❌ 无求职信正文，先 draft / set-body")
        return 1
    if sent_log.is_sent(lead["contact_email"]):
        print("⚠️ 该邮箱已在发送日志中，跳过")
        return 0
    exceeded, used, cap = daily_cap_status(cfg, sent_log)
    if exceeded:
        print(f"❌ 已达每日发送上限（上限 {cap}，今日已发 {used}），拒绝发送")
        return 2
    mailer = Mailer(cfg=cfg)
    try:
        pp = resolve_path(cfg, cfg.get("profile_path") or "profile.yaml")
        if pp.exists():
            mailer.set_user_name(load_profile(pp).get("identity", {}).get("name") or "")
    except Exception:
        pass
    ok = mailer.send(
        to_email=lead["contact_email"],
        company=lead.get("company") or "",
        job_title=lead.get("job_title") or "",
        body_text=lead["body"],
    )
    if ok:
        leads.mark_sent(args.id)
        sent_log.add(lead["contact_email"], lead.get("company") or "", lead.get("job_title") or "")
        return 0
    leads.mark_failed(args.id, "smtp failed")
    return 1


def cmd_send_all(args):
    if not args.confirm:
        print("❌ 批量发送需显式 --confirm")
        return 2
    cfg = load_config(args.config)
    data_dir = resolve_path(cfg, args.data_dir)
    leads = JobLeads(data_dir)
    sent_log = SentLog(data_dir)
    ready = leads.list("ready")
    if not ready:
        print("没有 ready 线索")
        return 0
    exceeded, used, cap = daily_cap_status(cfg, sent_log)
    if exceeded:
        print(f"❌ 已达每日发送上限（上限 {cap}，今日已发 {used}），拒绝批量发送")
        return 2
    remaining = (cap - used) if cap > 0 else len(ready)
    if remaining < len(ready):
        print(f"⚠️ 今日剩余额度 {remaining} 封（上限 {cap}，已发 {used}），只发送前 {remaining} 封")
    print(f"将发送 {min(len(ready), remaining)} 封，请再次确认列表：")
    for x in ready[:remaining]:
        print(f"  #{x['id']} {x.get('company')} <{x.get('contact_email')}>")
    mailer = Mailer(cfg=cfg)
    try:
        pp = resolve_path(cfg, cfg.get("profile_path") or "profile.yaml")
        if pp.exists():
            mailer.set_user_name(load_profile(pp).get("identity", {}).get("name") or "")
    except Exception:
        pass
    interval = int((cfg.get("pipeline") or {}).get("send_interval_seconds") or 5)
    sent_this_run = 0
    for lead in ready:
        if sent_this_run >= remaining:
            print("已达本次额度，停止发送")
            break
        if sent_log.is_sent(lead["contact_email"]):
            print(f"跳过已发送 {lead['contact_email']}")
            continue
        ok = mailer.send(
            to_email=lead["contact_email"],
            company=lead.get("company") or "",
            job_title=lead.get("job_title") or "",
            body_text=lead.get("body") or "",
        )
        if ok:
            leads.mark_sent(lead["id"])
            sent_log.add(lead["contact_email"], lead.get("company") or "", lead.get("job_title") or "")
            sent_this_run += 1
        else:
            leads.mark_failed(lead["id"], "smtp failed")
        time.sleep(interval)
    return 0


def cmd_export(args):
    cfg = load_config(args.config)
    leads = JobLeads(resolve_path(cfg, args.data_dir))
    counts = leads.count_by_status()
    lines = [
        "# 求职线索报告",
        "",
        f"总计：{sum(counts.values())} | " + " | ".join(f"{k} {v}" for k, v in counts.items()),
        "",
        "| ID | 状态 | 公司 | 职位 | 邮箱 | 来源 |",
        "|----|------|------|------|------|------|",
    ]
    for x in leads.list():
        lines.append(
            f"| {x.get('id')} | {x.get('status')} | {x.get('company')} | "
            f"{x.get('job_title')} | {x.get('contact_email')} | {x.get('source_url') or ''} |"
        )
    out = Path(args.out) if args.out else resolve_path(cfg, args.data_dir) / "report.md"
    write_text(out, "\n".join(lines) + "\n")
    print(f"✅ 导出 {out}")
    return 0


def cmd_health(args):
    reg = SourceRegistry()
    results = reg.health_check()
    ok_n = sum(1 for r in results if r.get("ok"))
    print(f"源健康检查: {ok_n}/{len(results)} 可用")
    for r in results:
        flag = "OK" if r.get("ok") else "DEAD"
        extra = r.get("status_code") or r.get("error") or ""
        print(f"  [{flag}] {r.get('id')}: {extra} ({r.get('ms')}ms)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="job-apply", description="job-apply-agent CLI")
    p.add_argument("--config", default=None, help="config.yaml path")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("parse-resume", help="PDF → profile.yaml")
    sp.add_argument("--pdf", required=True)
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_parse_resume)

    sp = sub.add_parser("plan", help="Build plan.json")
    sp.add_argument("--run-profile", default=None)
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_plan)

    sp = sub.add_parser("collect", help="Collect from imports/URLs")
    sp.add_argument("--plan", default=None)
    sp.add_argument("--url", action="append", default=[])
    sp.set_defaults(func=cmd_collect)

    sp = sub.add_parser("draft", help="Generate cover letter skeletons")
    sp.add_argument("--data-dir", default="data")
    sp.add_argument("--id", type=int, default=None)
    sp.set_defaults(func=cmd_draft)

    sp = sub.add_parser("qa", help="QA filter")
    sp.add_argument("--data-dir", default="data")
    sp.set_defaults(func=cmd_qa)

    sp = sub.add_parser("status")
    sp.add_argument("--data-dir", default="data")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("list")
    sp.add_argument("--data-dir", default="data")
    sp.add_argument("--status", default="all")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("add")
    sp.add_argument("--data-dir", default="data")
    sp.add_argument("--company", required=True)
    sp.add_argument("--job", required=True)
    sp.add_argument("--email", required=True)
    sp.add_argument("--jd", default="")
    sp.add_argument("--source", default="")
    sp.add_argument("--body", default="")
    sp.add_argument("--source-type", default="manual")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("set-body")
    sp.add_argument("--data-dir", default="data")
    sp.add_argument("--id", type=int, required=True)
    sp.add_argument("--body", required=True)
    sp.set_defaults(func=cmd_set_body)

    sp = sub.add_parser("send", help="Send one lead (requires --confirm)")
    sp.add_argument("--data-dir", default="data")
    sp.add_argument("--id", type=int, required=True)
    sp.add_argument("--body", default=None)
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_send)

    sp = sub.add_parser("send-all", help="Send all ready (requires --confirm)")
    sp.add_argument("--data-dir", default="data")
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_send_all)

    sp = sub.add_parser("export")
    sp.add_argument("--data-dir", default="data")
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("health", help="Health-check curated sources")
    sp.set_defaults(func=cmd_health)

    return p


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
