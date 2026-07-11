# -*- coding: utf-8 -*-
"""SMTP mailer. Secrets from config/env only — never hardcode."""
from __future__ import annotations

import smtplib
import time
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from config_loader import load_config, resolve_path


class Mailer:
    def __init__(self, config_path: str | None = None, cfg: dict | None = None):
        self._cfg = cfg or load_config(config_path)
        smtp = self._cfg.get("smtp") or {}
        self._server = smtp.get("server") or ""
        self._port = int(smtp.get("port") or 465)
        self._email = smtp.get("email") or ""
        self._password = smtp.get("password") or ""
        self._use_ssl = bool(smtp.get("use_ssl", True))

        resume_cfg = self._cfg.get("resume") or {}
        resume_raw = resume_cfg.get("path") or ""
        self._resume_path = resolve_path(self._cfg, resume_raw) if resume_raw else None
        self._resume_display = resume_cfg.get("display_name") or (
            self._resume_path.name if self._resume_path else "resume.pdf"
        )

        # Prefer profile name if present later; fallback empty
        self._user_name = ""
        overrides = self._cfg.get("user_overrides") or {}
        if overrides.get("name"):
            self._user_name = overrides["name"]

        if not self._email or not self._password:
            raise ValueError("SMTP email/password 未配置（config.yaml 或 SMTP_PASSWORD 环境变量）")
        if self._resume_path and not self._resume_path.exists():
            raise FileNotFoundError(f"简历不存在: {self._resume_path}")

    def set_user_name(self, name: str) -> None:
        self._user_name = name or self._user_name

    def send(
        self,
        to_email: str,
        company: str,
        job_title: str,
        body_text: str,
        subject: str | None = None,
    ) -> bool:
        if subject is None:
            who = self._user_name or "候选人"
            subject = f"实习投递_{who}_{job_title}_{company}"
        for attempt in range(1, 3):
            try:
                self._do_send(to_email, subject, body_text)
                print(f"[成功] {company} ({to_email})")
                return True
            except Exception as exc:
                if attempt == 1:
                    print(f"[重试] {company} ({to_email}) — {exc}")
                    time.sleep(3)
                else:
                    print(f"[失败] {company} ({to_email}) — {exc}")
                    return False
        return False

    def send_batch(self, leads_list: list, interval: int = 5) -> dict:
        results = {"sent": 0, "failed": 0, "details": []}
        total = len(leads_list)
        for idx, lead in enumerate(leads_list, 1):
            to_email = lead.get("to_email") or lead.get("contact_email") or ""
            company = lead.get("company", "")
            job_title = lead.get("job_title", "")
            body = lead.get("body", "")
            print(f"--- 发送 {idx}/{total}: {company} ---")
            detail = {"company": company, "email": to_email, "ok": False, "error": ""}
            ok = self.send(to_email, company, job_title, body)
            detail["ok"] = ok
            if ok:
                results["sent"] += 1
            else:
                results["failed"] += 1
                detail["error"] = "发送失败"
            results["details"].append(detail)
            if idx < total:
                time.sleep(interval)
        print(f"\n批量发送完成: 成功 {results['sent']}, 失败 {results['failed']}")
        return results

    def _build_message(self, to_email: str, subject: str, body_text: str) -> MIMEMultipart:
        msg = MIMEMultipart()
        msg["From"] = self._email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if self._resume_path and self._resume_path.exists():
            with open(self._resume_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{self._resume_display}"',
            )
            msg.attach(part)
        return msg

    def _do_send(self, to_email: str, subject: str, body_text: str) -> None:
        msg = self._build_message(to_email, subject, body_text)
        if self._use_ssl:
            with smtplib.SMTP_SSL(self._server, self._port, timeout=30) as smtp:
                smtp.login(self._email, self._password)
                smtp.sendmail(self._email, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(self._server, self._port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(self._email, self._password)
                smtp.sendmail(self._email, [to_email], msg.as_string())
