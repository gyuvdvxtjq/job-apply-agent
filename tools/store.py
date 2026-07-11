# -*- coding: utf-8 -*-
"""Job leads store and sent-log (JSON, UTF-8)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from common import read_json, write_json


class SentLog:
    def __init__(self, data_dir: str | Path = "data"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file_path = self._data_dir / "sent_log.json"
        self._records: list[dict] = read_json(self._file_path, default=[]) or []

    def add(self, email: str, company: str, job_title: str) -> None:
        self._records.append({
            "email": email,
            "company": company,
            "job_title": job_title,
            "sent_at": datetime.now().isoformat(),
        })
        write_json(self._file_path, self._records)

    def is_sent(self, email: str) -> bool:
        el = email.lower()
        return any(r.get("email", "").lower() == el for r in self._records)

    def get_all(self) -> list[dict]:
        return list(self._records)

    def count(self) -> int:
        return len(self._records)


class JobLeads:
    """pending → ready → sent | failed | skipped"""

    def __init__(self, data_dir: str | Path = "data"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file_path = self._data_dir / "job_leads.json"
        self._leads: list[dict] = []
        self._next_id = 1
        self._load()

    def _load(self) -> None:
        raw = read_json(self._file_path, default=None)
        if raw is None:
            self._leads, self._next_id = [], 1
            return
        if isinstance(raw, dict) and "leads" in raw:
            self._leads = list(raw.get("leads") or [])
            self._next_id = int(raw.get("next_id") or (max((x.get("id", 0) for x in self._leads), default=0) + 1))
        elif isinstance(raw, list):
            self._leads = raw
            self._next_id = max((x.get("id", 0) for x in self._leads), default=0) + 1
        else:
            self._leads, self._next_id = [], 1

    def _save(self) -> None:
        write_json(self._file_path, {"next_id": self._next_id, "leads": self._leads})

    def add(
        self,
        company: str,
        job_title: str,
        contact_email: str,
        jd_summary: str = "",
        source_url: str = "",
        body: str = "",
        source_type: str = "",
        match_score: float | None = None,
        confidence: float | None = None,
        extra: dict | None = None,
    ) -> int:
        lead_id = self._next_id
        self._next_id += 1
        status = "ready" if body else "pending"
        lead: dict[str, Any] = {
            "id": lead_id,
            "company": company,
            "job_title": job_title,
            "contact_email": contact_email,
            "jd_summary": jd_summary,
            "source_url": source_url,
            "source_type": source_type,
            "body": body,
            "status": status,
            "match_score": match_score,
            "confidence": confidence,
            "created_at": datetime.now().isoformat(),
            "sent_at": "",
            "error": "",
        }
        if extra:
            lead.update(extra)
        self._leads.append(lead)
        self._save()
        return lead_id

    def get(self, lead_id: int) -> dict | None:
        for lead in self._leads:
            if lead.get("id") == lead_id:
                return lead
        return None

    def list(self, status: str | None = None) -> list[dict]:
        if not status or status == "all":
            return list(self._leads)
        return [x for x in self._leads if x.get("status") == status]

    def set_body(self, lead_id: int, body: str) -> bool:
        lead = self.get(lead_id)
        if not lead:
            return False
        lead["body"] = body
        if body and lead.get("status") in ("pending", "skipped"):
            lead["status"] = "ready"
        self._save()
        return True

    def mark_sent(self, lead_id: int) -> bool:
        lead = self.get(lead_id)
        if not lead:
            return False
        lead["status"] = "sent"
        lead["sent_at"] = datetime.now().isoformat()
        lead["error"] = ""
        self._save()
        return True

    def mark_failed(self, lead_id: int, error: str) -> bool:
        lead = self.get(lead_id)
        if not lead:
            return False
        lead["status"] = "failed"
        lead["error"] = error
        self._save()
        return True

    def mark_skipped(self, lead_id: int, reason: str = "") -> bool:
        lead = self.get(lead_id)
        if not lead:
            return False
        lead["status"] = "skipped"
        lead["error"] = reason
        self._save()
        return True

    def count_by_status(self) -> dict[str, int]:
        keys = ["pending", "ready", "sent", "failed", "skipped"]
        counts = {k: 0 for k in keys}
        for lead in self._leads:
            s = lead.get("status") or "pending"
            counts[s] = counts.get(s, 0) + 1
        return counts

    def find_by_email(self, email: str) -> list[dict]:
        el = email.lower()
        return [x for x in self._leads if (x.get("contact_email") or "").lower() == el]
