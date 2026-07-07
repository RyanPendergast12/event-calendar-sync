"""Core data models, settings loading, and dedup helpers for event-calendar-sync.

This module didn't exist in the original repo, even though main.py,
calendar_client.py, and both test files all imported from it
(`event_sync.models`). Event, Settings, event_uid, normalize_text,
has_duplicate, and send_discord_summary are defined here so those imports
resolve.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
import yaml


@dataclass
class Event:
    """A single event pulled from any provider, normalized to a common shape."""

    title: str
    start: datetime
    source: str = "unknown"
    url: str = ""
    location: str = ""
    description: str = ""

    @property
    def display_title(self) -> str:
        return self.title.strip()

    @property
    def best_url(self) -> str:
        return self.url


@dataclass
class Settings:
    dry_run: bool
    icloud_username: Optional[str]
    icloud_app_password: Optional[str]
    icloud_caldav_url: str
    target_calendar_name: str
    discord_webhook_url: Optional[str]
    default_timezone: str
    lookahead_days: int
    ticketmaster_api_key: Optional[str]
    bandsintown_app_id: Optional[str]
    markets: list[str] = field(default_factory=list)
    artists: list[str] = field(default_factory=list)
    public_urls: list[str] = field(default_factory=list)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_config_file() -> dict:
    """Read optional config.yml (see config.example.yml) for markets/artists/public_urls."""
    path = Path(os.environ.get("EVENT_SYNC_CONFIG", "config.yml"))
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_settings() -> Settings:
    """Build Settings from environment variables (see event-sync.yml), layered with config.yml."""
    config = _load_config_file()

    return Settings(
        dry_run=_env_bool("DRY_RUN", True),
        icloud_username=os.environ.get("ICLOUD_USERNAME") or None,
        icloud_app_password=os.environ.get("ICLOUD_APP_PASSWORD") or None,
        icloud_caldav_url=os.environ.get("ICLOUD_CALDAV_URL", "https://caldav.icloud.com"),
        target_calendar_name=config.get(
            "target_calendar_name",
            os.environ.get("TARGET_CALENDAR_NAME", "Concert + Social Alerts"),
        ),
        discord_webhook_url=os.environ.get("DISCORD_WEBHOOK_URL") or None,
        default_timezone=config.get(
            "default_timezone", os.environ.get("DEFAULT_TIMEZONE", "America/Los_Angeles")
        ),
        lookahead_days=int(config.get("lookahead_days", os.environ.get("LOOKAHEAD_DAYS", 365))),
        ticketmaster_api_key=os.environ.get("TICKETMASTER_API_KEY") or None,
        bandsintown_app_id=os.environ.get("BANDSINTOWN_APP_ID") or None,
        markets=list(config.get("markets", []) or []),
        artists=list(config.get("artists", []) or []),
        public_urls=list(config.get("public_urls", []) or []),
    )


def normalize_text(text: str) -> str:
    """Lowercase, strip accents/punctuation/extra whitespace for stable comparisons."""
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def event_uid(event: Event) -> str:
    """Deterministic UID so reruns never create duplicate calendar entries."""
    key = f"{normalize_text(event.title)}|{event.start.isoformat()}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return f"event-calendar-sync-{digest}@icloud"


def has_duplicate(event: Event, existing: list[Event]) -> bool:
    """True if event matches something already collected in this run (title+start)."""
    target = (normalize_text(event.title), event.start)
    return any((normalize_text(e.title), e.start) == target for e in existing)


def send_discord_summary(webhook_url: Optional[str], summary: dict) -> None:
    """Post a short run summary to Discord. No-op if no webhook is configured."""
    if not webhook_url:
        return

    lines = [
        f"**event-calendar-sync** ({'dry run' if summary['dry_run'] else 'live'})",
        f"Found: {summary['found']} | Added: {summary['added']} | "
        f"Duplicates skipped: {summary['skipped_duplicates']}",
    ]
    if summary.get("provider_errors"):
        lines.append("Provider errors: " + "; ".join(summary["provider_errors"]))

    try:
        requests.post(webhook_url, json={"content": "\n".join(lines)}, timeout=10)
    except requests.RequestException:
        pass
