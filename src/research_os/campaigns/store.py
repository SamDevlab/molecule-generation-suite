"""Persistent campaign history, separate from the immutable scientific Ledger."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading
from typing import Any

from research_os.campaigns.models import ResearchCampaign


class CampaignStore:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock, self.connection:
            self.connection.execute("CREATE TABLE IF NOT EXISTS research_campaigns (campaign_id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, payload_json TEXT NOT NULL)")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_research_campaigns_updated ON research_campaigns(updated_at)")

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def save(self, campaign: ResearchCampaign) -> ResearchCampaign:
        payload = json.dumps(campaign.to_dict(), ensure_ascii=False, sort_keys=True, default=str)
        with self._lock, self.connection:
            self.connection.execute("INSERT INTO research_campaigns(campaign_id,status,created_at,updated_at,payload_json) VALUES(?,?,?,?,?) ON CONFLICT(campaign_id) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at,payload_json=excluded.payload_json", (campaign.campaign_id, campaign.status.value, campaign.created_at, campaign.updated_at, payload))
        return campaign

    def get(self, campaign_id: str) -> ResearchCampaign:
        with self._lock:
            row = self.connection.execute("SELECT payload_json FROM research_campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
        if row is None:
            raise KeyError(campaign_id)
        return ResearchCampaign(**json.loads(row["payload_json"]))

    def list(self, *, limit: int = 100) -> tuple[ResearchCampaign, ...]:
        with self._lock:
            rows = self.connection.execute("SELECT payload_json FROM research_campaigns ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return tuple(ResearchCampaign(**json.loads(row["payload_json"])) for row in rows)
